import os
import shutil
import tempfile
from typing import List, Tuple
from .models import ScriptItem, ScriptType, Job
from .utils import BATCH_SCRIPT_SUFFIX, ACCORE_LOG_SUFFIX


def normalize_newlines(text: str) -> str:
    """Normalize line endings to LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_scr(path: str) -> str:
    """
    Read a .scr script file with proper encoding handling.
    
    Args:
        path: Path to the .scr file
        
    Returns:
        Script contents with normalized line endings and trailing newline
        
    Raises:
        FileNotFoundError: If script file does not exist
        IOError: If file cannot be read
    """
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return normalize_newlines(f.read()).rstrip() + "\n"

def make_assembled_script_for_dwg(
    dwg_path: str,
    items: List[ScriptItem],
    output_dir: str,
    qsave_at_end: bool,
    quit_at_end: bool
) -> Tuple[str, str]:
    """
    Assemble a unified .scr script for a single DWG file.
    
    Concatenates all .scr files and generates (load ...) directives for .lsp files,
    optionally adding QSAVE and QUIT commands.
    
    Args:
        dwg_path: Path to the DWG file being processed
        items: List of ScriptItem (scripts and LISP files) to include
        output_dir: Directory where assembled script will be written
        qsave_at_end: Whether to append QSAVE command
        quit_at_end: Whether to append QUIT command
        
    Returns:
        Tuple of (assembled_script_path, display_name) where display_name is
        the DWG basename without extension
    """
    os.makedirs(output_dir, exist_ok=True)
    base = os.path.basename(dwg_path)
    display_name = os.path.splitext(base)[0]
    temp_scr_name = f"{display_name}{BATCH_SCRIPT_SUFFIX}"
    temp_scr_path = os.path.join(output_dir, temp_scr_name)

    lines = ["; --- Assembled by DWG Batch Processor ---\n"]
    # Safety: Ensure dialog boxes are off (Core Console already does not show dialogs)
    # but it doesn't hurt.
    lines.append("FILEDIA 0\n")

    for it in items:
        if it.type == ScriptType.SCR:
            lines.append(f"; ---- INCLUDE SCRIPT: {os.path.basename(it.path)} ----\n")
            try:
                lines.append(read_scr(it.path))
            except Exception as ex:
                lines.append(f"; ERROR: failed to read script: {it.path} ; {ex}\n")
        elif it.type == ScriptType.LSP:
            lines.append(f"; ---- LOAD LISP: {os.path.basename(it.path)} ----\n")
            # Use double backslashes in Windows paths inside Lisp strings
            lisp_path = it.path.replace("\\", "\\\\")
            lines.append(f'(load "{lisp_path}")\n')
            if it.invoke.strip():
                # Allow either raw symbol (MYCMD) or a Lisp form ((c:MYCMD))
                inv = it.invoke.strip()
                if inv.startswith("(") and inv.endswith(")"):
                    lines.append(f"{inv}\n")
                else:
                    lines.append(f"{inv}\n")
        else:
            lines.append(f"; WARN: Unknown item type for {it.path}\n")

    if qsave_at_end:
        lines.append("\nQSAVE\n")
    if quit_at_end:
        lines.append("QUIT\n")

    with open(temp_scr_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return temp_scr_path, display_name

def prepare_jobs_for_dwgs(
    dwg_paths: List[str],
    items: List[ScriptItem],
    output_dir: str,
    qsave_at_end: bool,
    quit_at_end: bool,
    copy_to_output: bool
) -> List[Job]:
    """
    Create one Job per DWG file with an assembled script.
    
    Args:
        dwg_paths: List of DWG file paths to process
        items: List of ScriptItem (scripts/LISP) to include in each job
        output_dir: Directory for assembled scripts and logs
        qsave_at_end: Whether to append QSAVE command
        quit_at_end: Whether to append QUIT command
        copy_to_output: If True, copy DWGs to output_dir before processing
        
    Returns:
        List of Job objects ready for submission to ParallelManager
    """
    jobs: List[Job] = []
    for dwg in dwg_paths:
        working_dwg = dwg
        if copy_to_output:
            os.makedirs(output_dir, exist_ok=True)
            target = os.path.join(output_dir, os.path.basename(dwg))
            shutil.copy2(dwg, target)
            working_dwg = target

        scr, display = make_assembled_script_for_dwg(
            working_dwg, items, output_dir, qsave_at_end, quit_at_end
        )
        jobs.append(Job(dwg_path=working_dwg, assembled_scr=scr, display_name=display))
    return jobs