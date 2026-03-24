import time
import os
import openpyxl
import base64
from playwright.sync_api import sync_playwright

try:
    from captcha_solver import solve_captcha_from_image
except ImportError:
    # Fallback if the solver is not in the same directory (though it should be)
    from .captcha_solver import solve_captcha_from_image

from extract_gstin_data import extract_gstin_data

# Ensure we use paths relative to the script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_path(relative_path):
    return os.path.join(SCRIPT_DIR, relative_path)

def init_browser(p, headless=True, slow_mo=100, window_pos="960,0", window_size="960,1080"):
    """Launches the browser or connects to a remote browser via CDP."""
    ws_endpoint = os.environ.get("BROWSER_WS_ENDPOINT")
    
    if ws_endpoint:
        print(f"Connecting to remote browser at {ws_endpoint}...")
        browser = p.chromium.connect_over_cdp(ws_endpoint)
    else:
        print(f"Launching local browser (headless={headless})...")
        browser = p.chromium.launch(
            headless=headless, 
            slow_mo=slow_mo,
            args=[
                f"--window-position={window_pos}",
                f"--window-size={window_size}",
                "--no-sandbox",
                "--disable-setuid-sandbox"
            ]
        )
    
    context = browser.new_context(viewport={'width': 960, 'height': 1080})
    page = context.new_page()
    return page, context, browser

def navigate_to_search(page):
    """Navigates to the GST search page and waits for network idle."""
    print("Navigating to GST Search...")
    page.goto("https://services.gst.gov.in/services/searchtp")
    page.wait_for_load_state("networkidle")

def fill_gstin(page, gstin_value):
    """Fills the GSTIN input field."""
    page.locator("#for_gstin").fill("")
    page.locator("#for_gstin").press_sequentially(gstin_value, delay=100)
    time.sleep(1)

def solve_and_submit_captcha(page, max_attempts=3, status_callback=None):
    """Wait for captcha submission if auto-solve is enabled (currently stubbed)."""
    is_solved = False
    
    # Pre-check: if results are already visible
    try:
        if page.locator("#lottable").is_visible(timeout=500):
            return True
    except:
        pass

    # Note: Automated solving is disabled to reduce Vercel bundle size.
    # If a remote browser with a UI is used, the user could solve it manually.
    if status_callback: status_callback("Manual Captcha Solution Required - Waiting...")
    
    try:
        # Long timeout for manual solve if using a remote browser with a live view
        page.wait_for_selector("#lottable", timeout=180000)
        is_solved = True
    except Exception:
        pass
    
    return is_solved

def run_batch_gst_search_excel(excel_path="gst_data.xlsx", status_callback=None):
    """Processes GSTINs from Excel using openpyxl (to save bundle size)."""
    abs_excel_path = get_path(excel_path)
    if not os.path.exists(abs_excel_path):
        return

    wb = openpyxl.load_workbook(abs_excel_path)
    sheet = wb.active
    
    # Get headers and find indices
    headers = [cell.value for cell in sheet[1]]
    total_rows = sheet.max_row - 1
    
    try:
        gstin_col = headers.index("GSTIN") + 1
    except ValueError:
        if status_callback: status_callback("Error: 'GSTIN' column not found in Excel.")
        return

    # Check for Legal Name column
    try:
        legal_name_col = headers.index("Legal Name of Business") + 1
    except ValueError:
        # Create it if it doesn't exist
        legal_name_col = len(headers) + 1
        sheet.cell(row=1, column=legal_name_col).value = "Legal Name of Business"
        headers.append("Legal Name of Business")

    # Map headers to indices for fast access
    col_map = {h: i+1 for i, h in enumerate(headers)}

    with sync_playwright() as p:
        # headless=True is mandatory for Vercel
        page, context, browser = init_browser(p, headless=True)
        try:
            navigate_to_search(page)
            
            processed_count = 0
            # Rows are 1-indexed, starting from row 2 (header is 1)
            for i in range(2, sheet.max_row + 1):
                gstin = str(sheet.cell(row=i, column=gstin_col).value).strip()
                legal_name = str(sheet.cell(row=i, column=legal_name_col).value).strip()
                
                if not gstin or gstin == "None" or gstin == "nan":
                    continue
                    
                if legal_name != "" and legal_name != "None" and legal_name != "nan":
                    continue

                processed_count += 1
                msg = f"Task {processed_count}: Processing {gstin}"
                if status_callback: status_callback(msg)
                
                try:
                    page.locator("#for_gstin").scroll_into_view_if_needed()
                    fill_gstin(page, gstin)
                    
                    if solve_and_submit_captcha(page, max_attempts=2, status_callback=status_callback):
                        table_html = page.content()
                        gst_data = extract_gstin_data(table_html)
                        
                        # Populate data back into sheet
                        for key, value in gst_data.items():
                            if key not in col_map:
                                col_map[key] = len(col_map) + 1
                                sheet.cell(row=1, column=col_map[key]).value = key
                            sheet.cell(row=i, column=col_map[key]).value = value
                        
                        wb.save(abs_excel_path)
                    
                    time.sleep(1)
                except Exception as e:
                    print(f"Error processing {gstin}: {e}")
                    continue
                
            if processed_count == 0:
                if status_callback: status_callback("All rows already filled. Task complete.")
            else:
                if status_callback: status_callback(f"Successfully processed {processed_count} GSTINs.")

        except Exception as e:
            print(f"!!! Browser Error: {e}")
        finally:
            browser.close()
