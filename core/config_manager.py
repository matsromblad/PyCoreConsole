import json
import os
from typing import Any, Dict, List
from .models import ScriptItem, ScriptType, Workflow
from .utils import ACCORE_LOG_SUFFIX

APP_DIR = os.path.join(os.path.expanduser("~"), ".dwg_batch_processor")
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")

DEFAULT_SETTINGS: Dict[str, Any] = {
    "accore_path": r"C:\Program Files\Autodesk\AutoCAD 2024\accoreconsole.exe",
    "autocad_path": r"C:\Program Files\Autodesk\AutoCAD 2024\acad.exe",
    "use_accore": True,  # True=Core Console, False=Regular AutoCAD
    "show_console": False,  # Show separate console windows for each job
    "language": "en-US",
    "product": "",  # e.g. C3D
    "max_parallel": 2,
    "qsave_at_end": True,
    "quit_at_end": True,
    "copy_to_output": False,
    "enable_logging": True,
    "last_output_dir": os.path.join(APP_DIR, "output"),
    "last_open_dir": os.path.expanduser("~"),
}


def ensure_app_dirs() -> None:
    """Ensure application directories exist."""
    os.makedirs(APP_DIR, exist_ok=True)
    os.makedirs(DEFAULT_SETTINGS["last_output_dir"], exist_ok=True)


def load_settings() -> Dict[str, Any]:
    """
    Load user settings from disk, merging with defaults for any missing keys.
    
    Returns:
        Dictionary of all settings with defaults for any missing keys
    """
    ensure_app_dirs()
    if not os.path.exists(SETTINGS_PATH):
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load settings: {e}, using defaults")
        return DEFAULT_SETTINGS.copy()
    # merge defaults for any new keys
    for k, v in DEFAULT_SETTINGS.items():
        data.setdefault(k, v)
    return data


def save_settings(s: Dict[str, Any]) -> None:
    """
    Save settings to disk.
    
    Args:
        s: Settings dictionary to persist
    """
    ensure_app_dirs()
    try:
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    except IOError as e:
        print(f"Warning: Could not save settings: {e}")

def export_workflow(path: str, items: List[ScriptItem]) -> None:
    """
    Export script workflow to JSON file.
    
    Args:
        path: Output file path
        items: List of ScriptItem to export
    """
    payload = [{
        "path": it.path,
        "type": it.type.value,
        "invoke": it.invoke,
        "note": it.note
    } for it in items]
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except IOError as e:
        raise IOError(f"Failed to export workflow: {e}")


def import_workflow(path: str) -> List[ScriptItem]:
    """
    Import script workflow from JSON file.
    
    Args:
        path: Input file path
        
    Returns:
        List of ScriptItem loaded from file
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        raise IOError(f"Failed to import workflow: {e}")
    items: List[ScriptItem] = []
    for obj in payload:
        items.append(ScriptItem(
            path=obj["path"],
            type=ScriptType(obj["type"]),
            invoke=obj.get("invoke", ""),
            note=obj.get("note", "")
        ))
    return items


def load_builtin_templates(resource_path: str) -> List[Workflow]:
    """
    Load built-in workflow templates from JSON resource file.
    
    Args:
        resource_path: Path to templates.json resource file
        
    Returns:
        List of Workflow templates
    """
    try:
        with open(resource_path, "r", encoding="utf-8") as f:
            js = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load templates: {e}, returning empty list")
        return []
    templates: List[Workflow] = []
    for tpl in js.get("templates", []):
        items = []
        for it in tpl.get("items", []):
            items.append(ScriptItem(
                path=it["path"],
                type=ScriptType(it["type"]),
                invoke=it.get("invoke", ""),
                note=it.get("note", "")
            ))
        templates.append(Workflow(name=tpl["name"], items=items))
    return templates