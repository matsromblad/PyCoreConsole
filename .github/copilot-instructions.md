# DWG Batch Processor — Copilot instructions

Summary
- Small PySide6 GUI that runs AutoCAD Core Console (`accoreconsole.exe`) in parallel across many DWG files.
- Split into `gui/` (UI + wiring) and `core/` (script assembly, job model, process orchestration).

Quick start ✅
- Install deps: `pip install -r requirements.txt` (uses `PySide6`).
- Run locally: `python main.py` (starts GUI).
- Build EXE: see `Create EXE.txt` or `DWGBatchProcessor.spec` (uses `pyinstaller`).

Architecture & data flow 🔧
- GUI (`gui/main_window.py`) is the entry point and persists user settings via `core/config_manager.py` (settings stored at `~/.dwg_batch_processor/settings.json`).
- `core/processor.py` assembles a per-DWG `.scr` file (named `{display_name}__batch.scr`) that concatenates `.scr` contents and LISP `load` + optional invoke forms.
  - LISP paths are escaped (double backslashes) when written into the assembled script.
  - Resulting log filename: `{display_name}__accore.log` in the output directory.
- `core/parallel_manager.py` runs `accoreconsole.exe` via `QProcess` and emits signals (`log_line`, `err_line`, `job_started`, `job_finished`, `queue_empty`) consumed by the UI.
- `core/models.py` defines `ScriptItem`, `Workflow`, `Job`, and `ScriptType` used across modules.

Project-specific conventions & gotchas ⚠️
- Platform-targeted for Windows + AutoCAD Core Console. Default `accore` path set in `DEFAULT_SETTINGS` but must match local AutoCAD install.
- Max parallel instances enforced (1–12); UI caps values via `QSpinBox`.
- When adding LISP `Invoke` values, you may supply either a raw command name (`MYCMD`) or a Lisp form (`(c:MYCMD)`) — `processor.py` writes these as-is into the assembled script.
- No unit tests present; manual testing is done by running `main.py` and using the GUI.
- Settings and templates:
  - Built-in templates live in `resources/templates.json` and are loaded by `core/config_manager.load_builtin_templates`.
  - Workflows can be exported/imported as JSON via `Save Script List…` / `Load Script List…` in the UI (`export_workflow` / `import_workflow`).

Editing guidelines & where to look ✍️
- To change job creation or script formatting: edit `core/processor.py` (`make_assembled_script_for_dwg`, `read_scr`).
- To adjust parallel execution or process handling: inspect `core/parallel_manager.py` (QProcess lifecycle and signal usage).
- To modify UI behavior: `gui/main_window.py` — look at `_prepare_jobs`, `_run_all`, and signal handlers (`_on_log_line`, `_on_job_finished`).
- For persistent settings / default values: `core/config_manager.py` (`DEFAULT_SETTINGS`, `SETTINGS_PATH`).

Debugging tips 🐞
- UI shows per-job logs in the Logs dock; logs are also appended to files in the output folder (`{display_name}__accore.log`).
- If AutoCAD doesn't start, check `accoreconsole.exe` path in settings; UI validates existence and shows an error if missing.
- QProcess output decoding uses `utf-8` with `errors='ignore'` — non-UTF-8 output is tolerated, but may drop bytes.

Examples to reference in code 🧭
- How scripts & LISP are assembled: `core/processor.py` (lines: assemble, add `QSAVE`/`QUIT`).
- How jobs are created and submitted: `gui/main_window.py::_prepare_jobs` → `ParallelManager.submit`.
- How templates are structured: `resources/templates.json` sample entries.

Notes for AI agents 💡
- Be conservative: follow file naming patterns (`{display}__batch.scr`, `{display}__accore.log`) and do not change log naming without updating both UI and `core` logic.
- Preserve the explicit Windows-oriented behaviors (path escaping for Lisp, use of `accoreconsole.exe`).
- Prefer modifying `core/` logic for behavior changes and `gui/` for UX changes — keep separation of concerns.

If any of this looks incomplete or you want more examples (e.g., suggested tests, CI, or refactors), tell me what to expand and I will iterate. ✅