import os
from typing import List
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QFileDialog, QMessageBox, QSpinBox,
    QLineEdit, QGroupBox, QFormLayout, QSplitter, QTextEdit, QTableWidget,
    QTableWidgetItem, QAbstractItemView, QProgressBar, QCheckBox, QComboBox,
    QDockWidget, QToolBar
)
# QAction must come from QtGui in PySide6 (6.x+)
from PySide6.QtGui import QAction

from core.config_manager import (
    load_settings, save_settings, load_builtin_templates, export_workflow, import_workflow
)
from core.models import ScriptItem, ScriptType
from core.processor import prepare_jobs_for_dwgs
from core.parallel_manager import ParallelManager
from core import trust_manager
from core.config_manager import ensure_app_dirs, APP_DIR
from .templates_dialog import TemplatesDialog


RES_TEMPLATES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "resources", "templates.json")

import re
_ansi_re = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
_ctrl_re = re.compile(r'[\x00-\x08\x0B-\x1F\x7F]')

def _sanitize_line(s: str) -> str:
    if not s:
        return s
    s = _ansi_re.sub('', s)
    s = _ctrl_re.sub('', s)
    return s.strip()


# --- Simple DnD list ---
class DragDropList(QListWidget):
    def __init__(self, extensions: List[str], parent=None):
        super().__init__(parent)
        self.extensions = [ext.lower() for ext in extensions]
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dropEvent(self, e):
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            if any(path.lower().endswith(ext) for ext in self.extensions):
                self.addItem(path)
        e.acceptProposedAction()

    def items_list(self) -> List[str]:
        return [self.item(i).text() for i in range(self.count())]

    def remove_selected(self):
        for it in self.selectedItems():
            self.takeItem(self.row(it))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DWG Batch Processor")
        self.settings = load_settings()
        self.templates = load_builtin_templates(RES_TEMPLATES)

        # --- Central layout ---
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        splitter = QSplitter()
        root.addWidget(splitter, 1)

        # Left: DWG list + controls
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.addWidget(QLabel("DWG files (drag & drop)"))
        self.dwgList = DragDropList([".dwg"])
        lv.addWidget(self.dwgList, 1)
        btns = QHBoxLayout()
        btn_add = QPushButton("Add DWGs…")
        btn_add.clicked.connect(self._add_dwgs)
        btn_rem = QPushButton("Remove Selected")
        btn_rem.clicked.connect(self.dwgList.remove_selected)
        btn_clear = QPushButton("Clear")
        btn_clear.clicked.connect(lambda: self.dwgList.clear())
        btns.addWidget(btn_add)
        btns.addWidget(btn_rem)
        btns.addWidget(btn_clear)
        lv.addLayout(btns)

        # Right: Scripts/LISP list + details
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.addWidget(QLabel("Scripts & LISP (drag & drop + reorder)"))
        self.scriptList = DragDropList([".scr", ".lsp"])
        rv.addWidget(self.scriptList, 1)

        sb = QHBoxLayout()
        b_add = QPushButton("Add…")
        b_add.clicked.connect(self._add_scripts)
        b_rem = QPushButton("Remove Selected")
        b_rem.clicked.connect(self.scriptList.remove_selected)
        b_clear = QPushButton("Clear")
        b_clear.clicked.connect(lambda: self.scriptList.clear())
        sb.addWidget(b_add); sb.addWidget(b_rem); sb.addWidget(b_clear)
        rv.addLayout(sb)

        # Item details panel
        details = QGroupBox("Selected item details")
        form = QFormLayout(details)
        self.sel_path = QLineEdit(); self.sel_path.setReadOnly(True)
        self.sel_type = QLineEdit(); self.sel_type.setReadOnly(True)
        self.sel_invk = QLineEdit()
        self.sel_note = QLineEdit()
        form.addRow("Path:", self.sel_path)
        form.addRow("Type:", self.sel_type)
        form.addRow("Invoke after load (optional):", self.sel_invk)
        form.addRow("Note:", self.sel_note)
        rv.addWidget(details)

        self.scriptList.currentItemChanged.connect(self._on_script_selection_change)
        self.sel_invk.editingFinished.connect(self._update_selected_item_metadata)
        self.sel_note.editingFinished.connect(self._update_selected_item_metadata)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)

        # --- Bottom: Controls + table + progress ---
        bottom = QHBoxLayout()
        root.addLayout(bottom)

        # Controls panel
        controls = QGroupBox("Run settings")
        cf = QFormLayout(controls)
        self.accore_path = QLineEdit(self.settings["accore_path"])
        self.btn_browse_accore = QPushButton("Browse…")
        self.btn_browse_accore.clicked.connect(self._browse_accore)

        acc_row = QHBoxLayout()
        acc_row.addWidget(self.accore_path, 1)
        acc_row.addWidget(self.btn_browse_accore)
        cf.addRow("accoreconsole.exe:", acc_row)

        self.cmb_lang = QComboBox()
        self.cmb_lang.addItems(["en-US", "en-GB", "sv-SE", "de-DE", "fr-FR", "it-IT", "es-ES"])
        self.cmb_lang.setCurrentText(self.settings.get("language", "en-US"))
        cf.addRow("Language (/l):", self.cmb_lang)

        self.product = QLineEdit(self.settings.get("product", ""))  # e.g., C3D
        cf.addRow("Product (/product):", self.product)

        self.spin_parallel = QSpinBox()
        self.spin_parallel.setRange(1, 12)
        self.spin_parallel.setValue(int(self.settings.get("max_parallel", 2)))
        cf.addRow("Parallel instances:", self.spin_parallel)

        self.chk_qsave = QCheckBox("QSAVE at end")
        self.chk_qsave.setChecked(self.settings.get("qsave_at_end", True))
        cf.addRow(self.chk_qsave)

        self.chk_quit = QCheckBox("QUIT at end")
        self.chk_quit.setChecked(self.settings.get("quit_at_end", True))
        cf.addRow(self.chk_quit)

        self.chk_copy = QCheckBox("Copy DWGs to output folder before processing (don't touch originals)")
        self.chk_copy.setChecked(self.settings.get("copy_to_output", False))
        cf.addRow(self.chk_copy)

        self.chk_logging = QCheckBox("Enable logging (write per-job log files and show console output)")
        self.chk_logging.setChecked(self.settings.get("enable_logging", True))
        cf.addRow(self.chk_logging)

        self.output_dir = QLineEdit(self.settings["last_output_dir"])
        self.btn_browse_out = QPushButton("Browse…")
        self.btn_browse_out.clicked.connect(self._browse_output)
        out_row = QHBoxLayout(); out_row.addWidget(self.output_dir, 1); out_row.addWidget(self.btn_browse_out)
        cf.addRow("Output folder:", out_row)

        # Buttons
        run_row = QHBoxLayout()
        self.btn_run = QPushButton("Process All")
        self.btn_run.clicked.connect(self._run_all)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self._stop_all)
        run_row.addWidget(self.btn_run); run_row.addWidget(self.btn_stop)
        cf.addRow(run_row)

        bottom.addWidget(controls, 1)

        # Jobs table
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["DWG", "Status", "Exit", "Log file"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        bottom.addWidget(self.table, 2)

        # Global progress & log dock
        gp_box = QGroupBox("Progress")
        gp_layout = QVBoxLayout(gp_box)
        self.global_progress = QProgressBar()
        self.global_progress.setRange(0, 100)
        self.global_progress.setValue(0)
        self.lbl_summary = QLabel("Idle.")
        gp_layout.addWidget(self.global_progress)
        gp_layout.addWidget(self.lbl_summary)
        bottom.addWidget(gp_box, 1)

        # Log dock
        dock = QDockWidget("Logs", self)
        self.addDockWidget(Qt.BottomDockWidgetArea, dock)
        dockw = QWidget()
        dock.setWidget(dockw)
        dlay = QHBoxLayout(dockw)
        self.txt_log = QTextEdit(); self.txt_log.setReadOnly(True)
        self.txt_err = QTextEdit(); self.txt_err.setReadOnly(True)
        dlay.addWidget(self.txt_log, 3)
        dlay.addWidget(self.txt_err, 2)
        self.txt_err.setStyleSheet("QTextEdit { color: #b00020; }")

        # Toolbar (templates / save-load)
        tb = QToolBar("Main")
        self.addToolBar(tb)
        act_tpl = QAction("Templates…", self); act_tpl.triggered.connect(self._templates)
        act_save = QAction("Save Script List…", self); act_save.triggered.connect(self._save_script_list)
        act_load = QAction("Load Script List…", self); act_load.triggered.connect(self._load_script_list)
        act_trust = QAction("Trust Scripts…", self); act_trust.triggered.connect(self._trust_scripts)
        tb.addAction(act_tpl); tb.addSeparator(); tb.addAction(act_save); tb.addAction(act_load); tb.addSeparator(); tb.addAction(act_trust)

        self._script_metadata = {}  # row_index -> {"invoke": str, "note": str}

        self.manager = None  # ParallelManager instance
        self._jobs_total = 0
        self._jobs_done = 0

        # Helpful banner for LISP in Console
        self._append_info_banner()

    def _append_info_banner(self):
        self.txt_log.append(
            "Tip: Core Console loads LISP from scripts with (load \"C:\\\\path\\\\file.lsp\"). "
            "If a LISP defines a command (defun c:MYCMD ...), add \"MYCMD\" into the 'Invoke' field. "
            "Also ensure the LISP folder is a Trusted Location in AutoCAD if loading fails.\n"
        )

    # --- UI handlers ---
    def _add_dwgs(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add DWG files", self.settings["last_open_dir"], "DWG files (*.dwg)")
        if files:
            self.settings["last_open_dir"] = os.path.dirname(files[0])
            for f in files:
                self.dwgList.addItem(f)

    def _add_scripts(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Add scripts/LISP", self.settings["last_open_dir"], "Scripts or LISP (*.scr *.lsp)")
        if files:
            self.settings["last_open_dir"] = os.path.dirname(files[0])
            for f in files:
                self.scriptList.addItem(f)

    def _browse_output(self):
        d = QFileDialog.getExistingDirectory(self, "Select output folder", self.output_dir.text())
        if d:
            self.output_dir.setText(d)

    def _browse_accore(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select accoreconsole.exe", self.accore_path.text(), "Executable (*.exe)")
        if f:
            self.accore_path.setText(f)

    def _templates(self):
        dlg = TemplatesDialog(self.templates, self)
        if dlg.exec() == dlg.Accepted and dlg.selected_items:
            # Replace current list with template
            self.scriptList.clear()
            self._script_metadata.clear()
            for it in dlg.selected_items:
                self.scriptList.addItem(it.path)
                row = self.scriptList.count() - 1
                self._script_metadata[row] = {"invoke": it.invoke, "note": it.note}
            self.txt_log.append(f"Applied template with {len(dlg.selected_items)} items.\n")

    def _trust_scripts(self):
        # Gather unique script folders
        folders = set()
        for i in range(self.scriptList.count()):
            path = self.scriptList.item(i).text()
            if not path:
                continue
            d = os.path.dirname(path)
            if os.path.isdir(d):
                folders.add(d)
        if not folders:
            QMessageBox.information(self, "Trust Scripts", "No script folders found to check.")
            return

        # Check which folders are not in any profile
        untrusted = [p for p in sorted(folders) if not trust_manager.path_in_any_profile(p)]
        if not untrusted:
            QMessageBox.information(self, "Trusted", "All script folders are already trusted by AutoCAD.")
            return

        msg = "The following folders are not in AutoCAD Trusted Locations:\n\n" + "\n".join(untrusted)
        msg += "\n\nAdd them to Trusted Locations for your AutoCAD profiles? This will backup the current settings first."
        if QMessageBox.question(self, "Add Trusted Locations", msg, QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return

        # Ensure app dirs and perform add (adds to all profiles where missing)
        ensure_app_dirs()
        res = trust_manager.add_paths_to_all_profiles(untrusted)
        summary_lines = []
        added = res.get("added", {})
        failed = res.get("failed", {})
        skipped = res.get("skipped", [])
        if added:
            total_added = sum(len(v) for v in added.values())
            summary_lines.append(f"Added {total_added} entries for {len(added)} path(s).")
        if skipped:
            summary_lines.append(f"{len(skipped)} path(s) were already present and skipped.")
        if failed:
            summary_lines.append(f"Failed to add {len(failed)} path(s).")
            for p, m in failed.items():
                summary_lines.append(f" - {p}: {m}")
        summary_lines.append(f"Backup saved to: {res.get('backup')}")
        QMessageBox.information(self, "Trusted Locations", "\n".join(summary_lines))

    def _save_script_list(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save Script List", self.settings["last_open_dir"], "JSON (*.json)")
        if not path:
            return
        items = self._collect_script_items()
        export_workflow(path, items)
        self.txt_log.append(f"Saved script list to: {path}\n")

    def _load_script_list(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Script List", self.settings["last_open_dir"], "JSON (*.json)")
        if not path:
            return
        items = import_workflow(path)
        self.scriptList.clear()
        self._script_metadata.clear()
        for it in items:
            self.scriptList.addItem(it.path)
            row = self.scriptList.count() - 1
            self._script_metadata[row] = {"invoke": it.invoke, "note": it.note}
        self.txt_log.append(f"Loaded script list from: {path}\n")

    def _on_script_selection_change(self, cur: QListWidgetItem, prev: QListWidgetItem):
        if cur is None:
            self.sel_path.setText(""); self.sel_type.setText(""); self.sel_invk.setText(""); self.sel_note.setText("")
            return
        row = self.scriptList.row(cur)
        path = cur.text()
        self.sel_path.setText(path)
        ext = os.path.splitext(path)[1].lower().lstrip(".")
        self.sel_type.setText(ext)
        meta = self._script_metadata.get(row, {"invoke": "", "note": ""})
        self.sel_invk.setText(meta.get("invoke", ""))
        self.sel_note.setText(meta.get("note", ""))

    def _update_selected_item_metadata(self):
        cur = self.scriptList.currentItem()
        if cur is None:
            return
        row = self.scriptList.row(cur)
        meta = self._script_metadata.get(row, {})
        meta["invoke"] = self.sel_invk.text()
        meta["note"] = self.sel_note.text()
        self._script_metadata[row] = meta

    def _collect_script_items(self) -> List[ScriptItem]:
        items: List[ScriptItem] = []
        for i in range(self.scriptList.count()):
            path = self.scriptList.item(i).text()
            ext = os.path.splitext(path)[1].lower()
            t = ScriptType.SCR if ext == ".scr" else ScriptType.LSP
            meta = self._script_metadata.get(i, {"invoke": "", "note": ""})
            items.append(ScriptItem(path=path, type=t, invoke=meta.get("invoke", ""), note=meta.get("note", "")))
        return items

    def _set_status(self, row: int, status: str, exit_code: str = ""):
        self.table.setItem(row, 1, QTableWidgetItem(status))
        if exit_code != "":
            self.table.setItem(row, 2, QTableWidgetItem(exit_code))

    def _prepare_jobs(self):
        dwgs = self.dwgList.items_list()
        items = self._collect_script_items()
        if not dwgs:
            raise RuntimeError("Add at least one DWG.")
        if not items:
            raise RuntimeError("Add at least one script or LISP.")
        # Build jobs
        jobs = prepare_jobs_for_dwgs(
            dwg_paths=dwgs,
            items=items,
            output_dir=self.output_dir.text(),
            qsave_at_end=self.chk_qsave.isChecked(),
            quit_at_end=self.chk_quit.isChecked(),
            copy_to_output=self.chk_copy.isChecked()
        )
        return jobs

    def _init_table(self, jobs_count: int):
        self.table.setRowCount(0)
        for _ in range(jobs_count):
            r = self.table.rowCount()
            self.table.insertRow(r)
            for c in range(4):
                self.table.setItem(r, c, QTableWidgetItem(""))
        self.table.setHorizontalHeaderLabels(["DWG", "Status", "Exit", "Log file"])
        self.table.resizeColumnsToContents()

    @Slot()
    def _run_all(self):
        try:
            jobs = self._prepare_jobs()
        except Exception as ex:
            QMessageBox.warning(self, "Missing data", str(ex))
            return

        # Save settings
        self.settings["accore_path"] = self.accore_path.text()
        self.settings["language"] = self.cmb_lang.currentText()
        self.settings["product"] = self.product.text().strip()
        self.settings["max_parallel"] = self.spin_parallel.value()
        self.settings["qsave_at_end"] = self.chk_qsave.isChecked()
        self.settings["quit_at_end"] = self.chk_quit.isChecked()
        self.settings["copy_to_output"] = self.chk_copy.isChecked()
        self.settings["enable_logging"] = self.chk_logging.isChecked()
        self.settings["last_output_dir"] = self.output_dir.text()
        save_settings(self.settings)

        # Validate accore path
        if not os.path.isfile(self.settings["accore_path"]):
            QMessageBox.critical(self, "Invalid path", "accoreconsole.exe not found.")
            return

        self._jobs_total = len(jobs)
        self._jobs_done = 0
        self._init_table(self._jobs_total)
        for i, jb in enumerate(jobs):
            self.table.setItem(i, 0, QTableWidgetItem(os.path.basename(jb.dwg_path)))
            self._set_status(i, "Pending")
            # Precompute per-DWG log file path (may be disabled)
            if self.settings.get("enable_logging", True):
                log_path = os.path.join(self.output_dir.text(), f"{jb.display_name}__accore.log")
            else:
                log_path = "Disabled"
            self.table.setItem(i, 3, QTableWidgetItem(log_path))

        self.global_progress.setRange(0, self._jobs_total)
        self.global_progress.setValue(0)
        self.lbl_summary.setText(f"Running {self._jobs_total} job(s)…")

        # Build manager (opt-out of emitting logs if logging disabled)
        self.manager = ParallelManager(
            accore_path=self.settings["accore_path"],
            language=self.settings["language"],
            product=self.settings["product"],
            max_parallel=self.spin_parallel.value(),
            emit_logs=self.settings.get("enable_logging", True),
            parent=self
        )
        self.manager.job_started.connect(self._on_job_started)
        self.manager.job_finished.connect(self._on_job_finished)
        if self.settings.get("enable_logging", True):
            self.manager.log_line.connect(self._on_log_line)
            self.manager.err_line.connect(self._on_err_line)
        self.manager.queue_empty.connect(self._on_all_done)
        self.manager.submit(jobs)

    def _stop_all(self):
        if self.manager:
            self.manager.stop_all()
            self.txt_log.append("== Aborted by user ==\n")
            self.lbl_summary.setText("Aborted.")

    # --- Manager callbacks ---
    def _row_for_display(self, display: str) -> int:
        # display corresponds to DWG basename without extension
        for r in range(self.table.rowCount()):
            log_cell = self.table.item(r, 3)
            if not log_cell:
                continue
            # Derive display name from log filename
            text = log_cell.text()
            if os.path.basename(text).startswith(display + "__"):
                return r
        return -1

    def _on_job_started(self, display: str):
        r = self._row_for_display(display)
        if r >= 0:
            self._set_status(r, "Running")

    def _append_to_file(self, r: int, msg: str, error: bool = False):
        log_path_item = self.table.item(r, 3)
        if log_path_item is None:
            return
        log_path = log_path_item.text()
        # If logging disabled or no path set, skip file writes
        if not log_path or log_path == "Disabled":
            return
        # Sanitize message (remove ANSI/control chars)
        msg = _sanitize_line(msg)
        if not msg:
            return
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        except Exception as ex:
            self.txt_err.append(f"[{os.path.basename(log_path)}] Failed to write log: {ex}")
            return
        if error:
            self.txt_err.append(f"[{os.path.basename(log_path)}] {msg}")
        else:
            self.txt_log.append(f"[{os.path.basename(log_path)}] {msg}")

    def _on_log_line(self, display: str, line: str):
        r = self._row_for_display(display)
        if r >= 0:
            self._append_to_file(r, line)

    def _on_err_line(self, display: str, line: str):
        r = self._row_for_display(display)
        if r >= 0:
            self._append_to_file(r, line, error=True)

    def _on_job_finished(self, display: str, exit_code: int):
        r = self._row_for_display(display)
        if r >= 0:
            self._set_status(r, "Done", str(exit_code))
        self._jobs_done += 1
        self.global_progress.setValue(self._jobs_done)
        self.lbl_summary.setText(f"Completed {self._jobs_done}/{self._jobs_total}.")

    def _on_all_done(self):
        if self._jobs_total == 0:
            self.global_progress.setRange(0, 100)
            self.global_progress.setValue(0)
            self.lbl_summary.setText("Idle.")
            return
        self.lbl_summary.setText(f"All jobs finished. ({self._jobs_done}/{self._jobs_total})")


def run_app():
    import sys
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(1200, 700)
    win.show()
    sys.exit(app.exec())