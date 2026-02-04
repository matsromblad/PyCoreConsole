from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ScriptType(str, Enum):
    SCR = "scr"
    LSP = "lsp"


@dataclass
class ScriptItem:
    path: str
    type: ScriptType
    # For LSP, optional command to invoke after (load ...).
    invoke: str = ""  # e.g., "MYCMD" or "(c:MYCMD)"
    # Optional comment for clarity in the assembled script
    note: str = ""


@dataclass
class Workflow:
    name: str
    items: List[ScriptItem] = field(default_factory=list)


@dataclass
class Job:
    dwg_path: str
    assembled_scr: str  # path to temp unified .scr
    display_name: str