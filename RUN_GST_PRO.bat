@echo off
title GST Desktop Pro - 500 Row Limit
echo Checking dependencies...
pip install -r requirements.txt > NUL
echo Launching GST Desktop Pro...
python gst_desktop_pro.py %1
if %errorlevel% neq 0 (
    echo.
    echo Please drag an Excel file onto this script to process it.
    pause
)
