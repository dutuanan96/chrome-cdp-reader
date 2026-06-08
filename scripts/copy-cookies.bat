@echo off
echo ========================================
echo   Copy Chrome Cookies
echo   chrome-cdp-reader
echo ========================================
echo.

set "SRC=%LOCALAPPDATA%\Google\Chrome\User Data\Default"
set "DST=C:\Users\%USERNAME%\chrome-debug-profile\Default"

REM Create destination if not exists
if not exist "%DST%" (
    mkdir "%DST%"
    echo Created debug profile directory
)

echo.
echo Copying cookies from default profile...
echo Source: %SRC%
echo Destination: %DST%
echo.

REM Copy cookie files
if exist "%SRC%\Cookies" (
    copy "%SRC%\Cookies" "%DST%\" >nul
    echo [OK] Cookies
) else (
    echo [SKIP] Cookies not found
)

if exist "%SRC%\Login Data" (
    copy "%SRC%\Login Data" "%DST%\" >nul
    echo [OK] Login Data
) else (
    echo [SKIP] Login Data not found
)

if exist "%SRC%\Preferences" (
    copy "%SRC%\Preferences" "%DST%\" >nul
    echo [OK] Preferences
) else (
    echo [SKIP] Preferences not found
)

if exist "%SRC%\Web Data" (
    copy "%SRC%\Web Data" "%DST%\" >nul
    echo [OK] Web Data
) else (
    echo [SKIP] Web Data not found
)

echo.
echo ========================================
echo   Cookie copy complete!
echo ========================================
echo.
echo Press any key to exit...
pause >nul
