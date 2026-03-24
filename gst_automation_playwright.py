import time
import os
import pandas as pd
import base64
from playwright.sync_api import sync_playwright
try:
    from captcha_solver import solve_captcha_from_image
except ImportError:
    # Fallback if the solver is not in the same directory (though it should be)
    from .captcha_solver import solve_captcha_from_image
import cv2
import numpy as np
from extract_gstin_data import extract_gstin_data

# Ensure we use paths relative to the script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_path(relative_path):
    return os.path.join(SCRIPT_DIR, relative_path)

def init_browser(p, headless=True, slow_mo=100, window_pos="960,0", window_size="960,1080"):
    """Launches the browser with specific position and size."""
    # Note: headless=True by default for server deployment
    print(f"Launching browser...")
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
    """Captures, solves, and submits the captcha with retry logic."""
    is_solved = False
    
    # Pre-check: if results are already visible
    try:
        if page.locator("#lottable").is_visible(timeout=500):
            return True
    except:
        pass

    for attempt in range(1, max_attempts + 1):
        captcha_img_selector = "#imgCaptcha"
        try:
            captcha_element = page.wait_for_selector(captcha_img_selector, timeout=10000)
        except:
            captcha_element = None
        
        if not captcha_element:
            if attempt < max_attempts:
                page.click("button[ng-click='refreshCaptcha()']")
                time.sleep(1)
                continue
            break

        captcha_bytes = captcha_element.screenshot()
        nparr = np.frombuffer(captcha_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        solved_text = solve_captcha_from_image(img)

        if len(solved_text) == 6:
            page.locator("#fo-captcha").fill(solved_text)
            page.locator("#lotsearch").click()

            try:
                error_selector = "span[data-ng-bind='trans.ERR_CAPTCHA']"
                page.wait_for_selector(error_selector, timeout=3000)
                if page.locator(error_selector).is_visible():
                    continue 
            except Exception:
                pass
            
            try:
                page.wait_for_selector("#lottable", timeout=5000)
                is_solved = True
                break
            except Exception:
                continue
        else:
            if attempt < max_attempts:
                page.click("button[ng-click='refreshCaptcha()']")
                time.sleep(1)

    if not is_solved:
        if status_callback: status_callback("Manual Input Required - Please solve captcha")
        try:
            page.wait_for_selector("#lottable", timeout=180000)
            is_solved = True
            if status_callback: status_callback("Resuming search...")
        except Exception:
            pass
    
    return is_solved

def run_batch_gst_search_excel(excel_path="gst_data.xlsx", status_callback=None):
    """Processes GSTINs from Excel with on-the-fly row identification."""
    abs_excel_path = get_path(excel_path)
    if not os.path.exists(abs_excel_path):
        return

    df = pd.read_excel(abs_excel_path)
    total_rows = len(df)
    
    # Note: For deployment like Vercel, use headless=True
    # To see the window for demo on your PC, change to headless=False
    with sync_playwright() as p:
        page, context, browser = init_browser(p, headless=False) # Keep False for demo
        try:
            navigate_to_search(page)
            
            processed_count = 0
            for i, (index, row) in enumerate(df.iterrows(), 1):
                legal_name = str(row.get("Legal Name of Business", "")).strip()
                if legal_name != "" and legal_name != "nan":
                    continue
                
                gstin = str(row.get("GSTIN", "")).strip()
                if not gstin or gstin == "nan":
                    continue

                processed_count += 1
                msg = f"Task {processed_count}: Processing {gstin} ({i}/{total_rows})"
                if status_callback: status_callback(msg)
                
                page.locator("#for_gstin").scroll_into_view_if_needed()
                fill_gstin(page, gstin)
                
                if solve_and_submit_captcha(page, max_attempts=2, status_callback=status_callback):
                    table_html = page.content()
                    gst_data = extract_gstin_data(table_html)
                    
                    for key, value in gst_data.items():
                        if key not in df.columns:
                            df[key] = None
                        df.at[index, key] = value
                    
                    df.to_excel(abs_excel_path, index=False)
                
                time.sleep(1)
                
            if processed_count == 0:
                if status_callback: status_callback("All rows already filled. Task complete.")
            else:
                if status_callback: status_callback(f"Successfully processed {processed_count} GSTINs.")

        except Exception as e:
            print(f"!!! Error: {e}")
        finally:
            browser.close()
