import time
import os
import openpyxl
import base64
from playwright.sync_api import sync_playwright
import cv2
import numpy as np

try:
    from captcha_solver import solve_captcha_from_image
except ImportError:
    from .captcha_solver import solve_captcha_from_image

from extract_gstin_data import extract_gstin_data

# Ensure we use paths relative to the script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_path(relative_path):
    return os.path.join(SCRIPT_DIR, relative_path)

def init_browser(p, headless=True):
    """Launches the browser."""
    # Note: On Render, we can launch local Chromium if installed via build.sh
    print(f"Launching browser (headless={headless})...")
    browser = p.chromium.launch(
        headless=headless, 
        args=["--no-sandbox", "--disable-setuid-sandbox"]
    )
    context = browser.new_context()
    page = context.new_page()
    return page, context, browser

def run_batch_gst_search_excel(excel_path="gst_data.xlsx", status_callback=None):
    """Processes GSTINs from Excel."""
    abs_excel_path = os.path.abspath(excel_path)
    if not os.path.exists(abs_excel_path):
        return

    wb = openpyxl.load_workbook(abs_excel_path)
    sheet = wb.active
    headers = [cell.value for cell in sheet[1]]
    
    try:
        gstin_col = headers.index("GSTIN") + 1
    except ValueError:
        if status_callback: status_callback("Error: 'GSTIN' column missing.")
        return

    col_map = {h: i+1 for i, h in enumerate(headers)}

    with sync_playwright() as p:
        page, context, browser = init_browser(p, headless=True)
        
        for i in range(2, sheet.max_row + 1):
            gstin = str(sheet.cell(row=i, column=gstin_col).value).strip()
            if not gstin or gstin == "None": continue

            if status_callback: status_callback(f"Processing {gstin}...")

            page.goto("https://services.gst.gov.in/services/searchtp")
            page.fill("#for_gstin", gstin)
            
            # Captcha loop
            is_solved = False
            for attempt in range(3):
                try:
                    captcha_img = page.wait_for_selector("#imgCaptcha", timeout=5000)
                    img_bytes = captcha_img.screenshot()
                    nparr = np.frombuffer(img_bytes, np.uint8)
                    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    
                    captcha_text = solve_captcha_from_image(img)
                    if len(captcha_text) == 6:
                        page.fill("#fo-captcha", captcha_text)
                        page.click("#lotsearch")
                        
                        try:
                            page.wait_for_selector("#lottable", timeout=5000)
                            is_solved = True
                            break
                        except:
                            page.click("button[ng-click='refreshCaptcha()']")
                            time.sleep(1)
                except:
                    break
            
            if is_solved:
                html = page.content()
                gst_data = extract_gstin_data(html)
                for key, value in gst_data.items():
                    if key not in col_map:
                        col_map[key] = len(col_map) + 1
                        sheet.cell(row=1, column=col_map[key]).value = key
                    sheet.cell(row=i, column=col_map[key]).value = value
                
                wb.save(abs_excel_path)
            
            time.sleep(1)

        browser.close()
        if status_callback: status_callback("Complete.")
