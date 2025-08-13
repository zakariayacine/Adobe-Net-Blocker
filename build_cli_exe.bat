@echo off
REM === Build CLI EXE for Adobe Net Blocker ===

SETLOCAL ENABLEDELAYEDEXPANSION
python -m venv .venv
CALL .venv\Scripts\activate

python -m pip install --upgrade pip
pip install pyinstaller

pyinstaller --onefile --name "AdobeNetBlockerCLI" --uac-admin adobe_net_blocker.py

echo.
echo Done. Your EXE is in the "dist" folder: dist\AdobeNetBlockerCLI.exe
pause
