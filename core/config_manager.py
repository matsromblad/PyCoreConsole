import json
import os
from typing import Any, Dict, List
from .models import ScriptItem, ScriptType, Workflow

APP_DIR = os.path.join(os.path.expanduser("~"), ".dwg_batch_processor")
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "accore_path": r"C:\Program Files\Autodesk\AutoCAD 2024\accoreconsole.exe",
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

def ensure_app_dirs():
    os.makedirs(APP_DIR, exist_ok=True)
    os.makedirs(DEFAULT_SETTINGS["last_output_dir"], exist_ok=True)

def load_settings() -> Dict[str, Any]:
    ensure_app_dirs()
    if not os.path.exists(SETTINGS_PATH):
        save_settings(DEFAULT_SETTINGS)
        return DEFAULT_SETTINGS.copy()
    with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    # merge defaults for any new keys
    for k, v in DEFAULT_SETTINGS.items():
        data.setdefault(k, v)
    return data

def save_settings(s: Dict[str, Any]) -> None:
    ensure_app_dirs()
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)

def export_workflow(path: str, items: List[ScriptItem]) -> None:
    payload = [{
        "path": it.path,
        "type": it.type.value,
        "invoke": it.invoke,
        "note": it.note
    } for it in items]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

def import_workflow(path: str) -> List[ScriptItem]:
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
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
    with open(resource_path, "r", encoding="utf-8") as f:
        js = json.load(f)
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