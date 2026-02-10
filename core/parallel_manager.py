from PySide6.QtCore import QObject, Signal, QProcess, QTimer
from typing import List, Optional
from .models import Job
from .utils import sanitize_line
import os
import time
import subprocess
import sys

class ParallelManager(QObject):
    log_line = Signal(str, str)       # (job_display_name, line)
    err_line = Signal(str, str)       # (job_display_name, line)
    job_started = Signal(str)         # display_name
    job_finished = Signal(str, int)   # display_name, exit_code
    queue_empty = Signal()

    def __init__(self, accore_path: str, autocad_path: str, use_accore: bool, language: str, product: str, max_parallel: int, emit_logs: bool = True, show_console: bool = False, parent=None):
        super().__init__(parent)
        self.accore_path = accore_path
        self.autocad_path = autocad_path
        self.use_accore = use_accore
        self.language = language
        self.product = product
        self.max_parallel = max_parallel
        self.emit_logs = bool(emit_logs)
        self.show_console = bool(show_console)
        self.pending: List[Job] = []
        self.active: List[QProcess] = []
        self.proc_to_job = {}

    def set_max_parallel(self, n: int):
        self.max_parallel = max(1, min(12, n))
        self._spin_up()

    def submit(self, jobs: List[Job]):
        self.pending.extend(jobs)
        self._spin_up()

    def _spin_up(self):
        while self.pending and len(self.active) < self.max_parallel:
            job = self.pending.pop(0)
            self._start_job(job)
        if not self.pending and not self.active:
            self.queue_empty.emit()

    def _proc_args(self, job: Job) -> list:
        args = []
        if self.product:
            args.extend(["/product", self.product])
        if self.language:
            args.extend(["/l", self.language])
        args.extend(["/i", job.dwg_path, "/s", job.assembled_scr])
        return args

    def _start_job(self, job: Job):
        if self.show_console:
            # Use subprocess to create a new console window for this job
            self._start_job_with_console(job)
        else:
            # Use QProcess to capture output (existing behavior)
            self._start_job_with_qprocess(job)

    def _start_job_with_console(self, job: Job):
        """Start job with a visible console window (Windows only)."""
        if self.use_accore:
            exe = self.accore_path
            args = self._proc_args(job)
        else:
            exe = self.autocad_path
            args = []
            if self.product:
                args.extend(["/product", self.product])
            if self.language:
                args.extend(["/l", self.language])
            args.extend([job.dwg_path, "/s", job.assembled_scr])

        # Verify files exist before launching
        if not os.path.isfile(exe):
            self.err_line.emit(job.display_name, f"ERROR: Executable not found: {exe}")
            self.job_finished.emit(job.display_name, -1)
            return
        
        if not os.path.isfile(job.assembled_scr):
            self.err_line.emit(job.display_name, f"ERROR: Assembled script not found: {job.assembled_scr}")
            self.job_finished.emit(job.display_name, -1)
            return
            
        if not os.path.isfile(job.dwg_path):
            self.err_line.emit(job.display_name, f"ERROR: DWG file not found: {job.dwg_path}")
            self.job_finished.emit(job.display_name, -1)
            return

        # Build command with proper quoting for paths with spaces
        cmd = [exe] + args
        
        # Log the command being executed
        print(f"\n[{job.display_name}] Starting: {' '.join(cmd)}\n")
        self.log_line.emit(job.display_name, f"Command: {' '.join(cmd)}")

        # Start process with visible console window (Windows-specific)
        try:
            creationflags = subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0
            # When showing a console window, we do NOT pipe stdout/stderr, so the user can see it.
            # This means the GUI logs won't receive the output, but the user requested visible terminals.
            proc = subprocess.Popen(
                cmd,
                creationflags=creationflags
            )
            # Store process info for tracking
            self.proc_to_job[proc.pid] = job
            self.active.append(proc)
            self.job_started.emit(job.display_name)
            
            # Start a thread to wait for process completion
            import threading
            thread = threading.Thread(target=self._wait_for_console_process, args=(proc, job))
            thread.daemon = True
            thread.start()
        except Exception as e:
            self.err_line.emit(job.display_name, f"Failed to start process: {e}")
            self.job_finished.emit(job.display_name, -1)

    def _wait_for_console_process(self, proc, job):
        """Wait for subprocess to complete and emit finish signal."""
        exit_code = proc.wait()
        if proc in self.active:
            self.active.remove(proc)
        if proc.pid in self.proc_to_job:
            del self.proc_to_job[proc.pid]
        self.job_finished.emit(job.display_name, exit_code)
        self._spin_up()

    def _start_job_with_qprocess(self, job: Job):
        """Start job with QProcess (output captured in GUI)."""
        proc = QProcess(self)
        if self.use_accore:
            proc.setProgram(self.accore_path)
            proc.setArguments(self._proc_args(job))
        else:
            # Regular AutoCAD: use /s for script execution
            proc.setProgram(self.autocad_path)
            args = []
            if self.product:
                args.extend(["/product", self.product])
            if self.language:
                args.extend(["/l", self.language])
            args.extend([job.dwg_path, "/s", job.assembled_scr])
            proc.setArguments(args)
        # Process environment inherits user's PATH (for DBX, etc.)
        proc.setProcessChannelMode(QProcess.SeparateChannels)
        proc.readyReadStandardOutput.connect(lambda j=job, p=proc: self._on_stdout(j, p))
        proc.readyReadStandardError.connect(lambda j=job, p=proc: self._on_stderr(j, p))
        proc.finished.connect(lambda code, status, j=job, p=proc: self._on_finish(j, p, code))
        self.active.append(proc)
        self.proc_to_job[proc] = job
        self.job_started.emit(job.display_name)
        proc.start()

    def _on_stdout(self, job: Job, proc: QProcess):
        if not self.emit_logs:
            return
        data = bytes(proc.readAllStandardOutput()).decode("utf-8", errors="ignore")
        for line in data.splitlines():
            clean = sanitize_line(line)
            if clean:
                self.log_line.emit(job.display_name, clean)

    def _on_stderr(self, job: Job, proc: QProcess):
        if not self.emit_logs:
            return
        data = bytes(proc.readAllStandardError()).decode("utf-8", errors="ignore")
        for line in data.splitlines():
            clean = sanitize_line(line)
            if clean:
                self.err_line.emit(job.display_name, clean)

    def _on_finish(self, job: Job, proc: QProcess, exit_code: int):
        self.job_finished.emit(job.display_name, exit_code)
        if proc in self.active:
            self.active.remove(proc)
        if proc in self.proc_to_job:
            del self.proc_to_job[proc]
        proc.deleteLater()
        self._spin_up()

    def stop_all(self):
        for p in list(self.active):
            p.kill()
        self.pending.clear()