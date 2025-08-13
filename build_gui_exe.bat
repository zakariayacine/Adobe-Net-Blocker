@echo off
REM === Build GUI EXE for Adobe Net Blocker ===
REM Requirements: Python 3.9+ on Windows, pip, and internet access to install pyinstaller

SETLOCAL ENABLEDELAYEDEXPANSION

REM Create and activate a venv (optional but recommended)
python -m venv .venv
CALL .venv\Scripts\activate

python -m pip install --upgrade pip
pip install pyinstaller

REM Build (requests admin at runtime via --uac-admin). Remove --icon if you don't have an .ico.
pyinstaller --noconsole --onefile ^
  --name "AdobeNetBlocker" ^
  --add-data "domains.txt;." ^
  --uac-admin ^
  adobe_net_blocker_gui.py

echo.
echo Done. Your EXE is in the "dist" folder: dist\AdobeNetBlocker.exe
pause
