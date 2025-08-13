Adobe Net Blocker — Build to EXE (Windows)
===========================================

What you have in this folder:
- adobe_net_blocker_gui.py   → Tkinter GUI
- adobe_net_blocker.py       → CLI
- domains.txt                → default domain list (can be edited)
- build_gui_exe.bat          → builds GUI EXE with PyInstaller
- build_cli_exe.bat          → builds CLI EXE with PyInstaller

How to build (simple way)
-------------------------
1) Copy these files to a writeable folder on Windows (e.g., C:\Users\<You>\Desktop\adobe-net-blocker).
2) Right‑click **build_gui_exe.bat** → Run. It will:
   - create a virtualenv,
   - install PyInstaller,
   - produce **dist\AdobeNetBlocker.exe** (requests admin via UAC).
   The GUI EXE embeds your **domains.txt** next to it at runtime. Edit domains.txt before building or keep a copy next to the EXE.

3) (Optional) Run **build_cli_exe.bat** for a console version: **dist\AdobeNetBlockerCLI.exe**.

Notes
-----
- The **--uac-admin** flag embeds a manifest so Windows will ask for elevation when you launch the EXE.
- If you want a custom icon, add `--icon your_icon.ico` to the PyInstaller command.
- SmartScreen may warn on first run (unsigned binary). You can sign the EXE with your code-signing certificate if needed.
- If Adobe apps are installed in non‑standard paths, add them in the GUI via “Ajouter chemin…”.

Troubleshooting
---------------
- If the EXE opens and immediately closes, run it from a Command Prompt to see messages.
- If building fails, ensure Python is in PATH, and you have permissions in the folder.
- For antivirus conflicts with PyInstaller, add an exclusion for the build folder temporarily.

Enjoy!
