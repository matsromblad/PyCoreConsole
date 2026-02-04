from PySide6.QtCore import QObject, Signal, QProcess, QTimer
from typing import List, Optional
from .models import Job
import os
import time
import re

_ansi_re = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
_ctrl_re = re.compile(r'[\x00-\x08\x0B-\x1F\x7F]')

def _sanitize_line(s: str) -> str:
    if not s:
        return s
    # Strip ANSI escape sequences and common control chars, then trim
    s = _ansi_re.sub('', s)
    s = _ctrl_re.sub('', s)
    return s.strip()

class ParallelManager(QObject):
    log_line = Signal(str, str)       # (job_display_name, line)
    err_line = Signal(str, str)       # (job_display_name, line)
    job_started = Signal(str)         # display_name
    job_finished = Signal(str, int)   # display_name, exit_code
    queue_empty = Signal()

    def __init__(self, accore_path: str, language: str, product: str, max_parallel: int, emit_logs: bool = True, parent=None):
        super().__init__(parent)
        self.accore_path = accore_path
        self.language = language
        self.product = product
        self.max_parallel = max_parallel
        self.emit_logs = bool(emit_logs)
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
        proc = QProcess(self)
        proc.setProgram(self.accore_path)
        proc.setArguments(self._proc_args(job))
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
            clean = _sanitize_line(line)
            if clean:
                self.log_line.emit(job.display_name, clean)

    def _on_stderr(self, job: Job, proc: QProcess):
        if not self.emit_logs:
            return
        data = bytes(proc.readAllStandardError()).decode("utf-8", errors="ignore")
        for line in data.splitlines():
            clean = _sanitize_line(line)
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