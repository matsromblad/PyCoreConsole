PyCoreConsole — DWG Batch Processor

Small GUI for running AutoCAD Core Console (`accoreconsole.exe`) across multiple DWG files in parallel.

Features
- Assemble `.scr` scripts and optional LISP invocation
- Run many jobs in parallel and collect per-job logs
- Option to add script folders to AutoCAD Trusted Locations (Windows)
- Enable/disable logging, and sanitize console output

Quick start
1. Create and activate a virtual environment:
   python -m venv .venv
   . .\.venv\Scripts\Activate.ps1
2. Install deps:
   pip install -r requirements.txt
3. Run the GUI:
   python main.py

License
MIT — see `LICENSE` file.
