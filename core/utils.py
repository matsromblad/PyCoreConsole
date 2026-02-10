"""Shared utilities for DWG Batch Processor."""

import re
from typing import Optional

# ANSI escape sequences and control characters regex patterns
ANSI_RE = re.compile(r'\x1B\[[0-?]*[ -/]*[@-~]')
CTRL_RE = re.compile(r'[\x00-\x08\x0B-\x1F\x7F]')

# File extensions
EXT_DWG = ".dwg"
EXT_SCR = ".scr"
EXT_LSP = ".lsp"

# Naming patterns
BATCH_SCRIPT_SUFFIX = "__batch.scr"
ACCORE_LOG_SUFFIX = "__accore.log"


def sanitize_line(s: str) -> str:
    """
    Remove ANSI escape sequences and control characters from output line.
    
    Args:
        s: Raw output line potentially containing ANSI codes and control chars
        
    Returns:
        Cleaned line stripped of formatting and control characters
    """
    if not s:
        return s
    # Strip ANSI escape sequences and common control chars, then trim
    s = ANSI_RE.sub('', s)
    s = CTRL_RE.sub('', s)
    return s.strip()
