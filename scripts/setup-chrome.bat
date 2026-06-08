@echo off
echo ========================================
echo   Chrome Debug Mode Setup
echo   chrome-cdp-reader
echo ========================================
echo.

REM Step 1: Kill existing Chrome
echo [1/5] Closing existing Chrome processes...
taskkill /F /IM chrome.exe 2>nul
timeout /t 2 /nobreak >nul

REM Step 2: Create debug profile directory
echo [2/5] Creating debug profile directory...
if not exist "C:\Users\%USERNAME%\chrome-debug-profile\Default" (
    mkdir "C:\Users\%USERNAME%\chrome-debug-profile\Default"
)

REM Step 3: Copy cookies from default profile
echo [3/5] Copying cookies from default profile...
set "SRC=%LOCALAPPDATA%\Google\Chrome\User Data\Default"
set "DST=C:\Users\%USERNAME%\chrome-debug-profile\Default"

if exist "%SRC%\Cookies" (
    copy "%SRC%\Cookies" "%DST%\" >nul
    echo   - Copied Cookies
) else (
    echo   - Cookies not found in default profile
)

if exist "%SRC%\Login Data" (
    copy "%SRC%\Login Data" "%DST%\" >nul
    echo   - Copied Login Data
)

if exist "%SRC%\Preferences" (
    copy "%SRC%\Preferences" "%DST%\" >nul
    echo   - Copied Preferences
)

REM Step 4: Launch Chrome with debug mode
echo [4/5] Launching Chrome with debug mode...
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --remote-allow-origins=* --user-data-dir="C:\Users\%USERNAME%\chrome-debug-profile"

REM Step 5: Wait and verify
echo [5/5] Waiting for Chrome to start...
timeout /t 5 /nobreak >nul

echo.
echo ========================================
echo   Setup Complete!
echo ========================================
echo.
echo Chrome is now running with debug mode.
echo Port: 9222
echo Profile: C:\Users\%USERNAME%\chrome-debug-profile
echo.
echo You can now use chrome-cdp-reader from WSL:
echo   crc read gmail
echo   crc read https://example.com
echo.
echo Press any key to exit...
pause >nul
