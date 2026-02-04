"""Helpers to check/add AutoCAD Trusted Locations (HKCU).

This module is Windows-only. It enumerates AutoCAD profiles under
HKEY_CURRENT_USER\SOFTWARE\Autodesk\AutoCAD and inspects the
Profiles\<profile>\Folders subkeys. Paths may be added to the
Folders keys for the current user (no admin required).

Functions return rich dicts with results and include a backup file
that contains the prior state so the change can be reverted manually.
"""
from typing import List, Dict, Any, Tuple
import os
import json
import time
import sys

# Lazy import winreg to allow importing the module on non-Windows platforms
try:
    import winreg as _winreg
except Exception:
    _winreg = None

from .config_manager import APP_DIR, ensure_app_dirs


def _is_windows() -> bool:
    return _winreg is not None and sys.platform.startswith("win")


def _open_key(root, path, access=_winreg.KEY_READ):
    try:
        return _winreg.OpenKey(root, path, 0, access)
    except Exception:
        raise


def find_profiles() -> List[Dict[str, str]]:
    """Enumerate AutoCAD versions -> products -> profiles and return
    a list of dicts with 'version', 'product', 'profile', 'folders_path'."""
    if not _is_windows():
        return []
    base = r"SOFTWARE\Autodesk\AutoCAD"
    profiles = []
    hkcu = _winreg.HKEY_CURRENT_USER
    try:
        with _open_key(hkcu, base) as base_key:
            for i in range(_winreg.QueryInfoKey(base_key)[0]):
                ver = _winreg.EnumKey(base_key, i)
                with _open_key(hkcu, base + "\\" + ver) as ver_key:
                    for j in range(_winreg.QueryInfoKey(ver_key)[0]):
                        prod = _winreg.EnumKey(ver_key, j)
                        profiles_path = base + "\\" + ver + "\\" + prod + "\\Profiles"
                        try:
                            with _open_key(hkcu, profiles_path) as profiles_key:
                                for k in range(_winreg.QueryInfoKey(profiles_key)[0]):
                                    prof = _winreg.EnumKey(profiles_key, k)
                                    folders_path = profiles_path + "\\" + prof + "\\Folders"
                                    profiles.append({
                                        "version": ver,
                                        "product": prod,
                                        "profile": prof,
                                        "folders_path": folders_path,
                                    })
                        except FileNotFoundError:
                            continue
    except FileNotFoundError:
        pass
    return profiles


def path_in_any_profile(path: str) -> bool:
    """Return True if the given folder path is present in any profile's Folders."""
    if not _is_windows():
        return False
    path_norm = os.path.normcase(os.path.normpath(path))
    hkcu = _winreg.HKEY_CURRENT_USER
    for prof in find_profiles():
        try:
            with _open_key(hkcu, prof["folders_path"]) as folders_key:
                for i in range(_winreg.QueryInfoKey(folders_key)[0]):
                    sub = _winreg.EnumKey(folders_key, i)
                    try:
                        with _open_key(hkcu, prof["folders_path"] + "\\" + sub) as sk:
                            val, _ = _winreg.QueryValueEx(sk, "")
                            if val and os.path.normcase(os.path.normpath(val)) == path_norm:
                                return True
                    except Exception:
                        continue
        except Exception:
            continue
    return False


def _read_folders_for_profile(folders_path: str) -> Dict[str, str]:
    """Return dict subkey -> value for a given Folders key."""
    hkcu = _winreg.HKEY_CURRENT_USER
    out = {}
    try:
        with _open_key(hkcu, folders_path) as folders_key:
            for i in range(_winreg.QueryInfoKey(folders_key)[0]):
                sub = _winreg.EnumKey(folders_key, i)
                try:
                    with _open_key(hkcu, folders_path + "\\" + sub) as sk:
                        val, _ = _winreg.QueryValueEx(sk, "")
                        out[sub] = val
                except Exception:
                    out[sub] = None
    except Exception:
        pass
    return out


def backup_profiles(folders_paths: List[str]) -> str:
    """Create a JSON backup of the provided folders_paths and return path to backup file."""
    ensure_app_dirs()
    hkcu = _winreg.HKEY_CURRENT_USER
    payload: Dict[str, Any] = { }
    for p in folders_paths:
        payload[p] = _read_folders_for_profile(p)
    fn = os.path.join(APP_DIR, f"trusted_folders_backup_{int(time.time())}.json")
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return fn


def add_paths_to_all_profiles(paths: List[str]) -> Dict[str, Any]:
    """Add each path to every profile's Folders if it isn't already present.
    Returns a dict with added/skipped/failed and backup path.
    """
    result = {"added": {}, "skipped": [], "failed": {}, "backup": None}
    if not _is_windows():
        result["failed"] = {p: "Platform not supported" for p in paths}
        return result
    profiles = find_profiles()
    if not profiles:
        result["failed"] = {p: "No AutoCAD profiles found" for p in paths}
        return result

    # Determine which Folders keys we'll modify (those where a path is not present)
    folders_to_check = list({prof["folders_path"] for prof in profiles})
    result["backup"] = backup_profiles(folders_to_check)

    hkcu = _winreg.HKEY_CURRENT_USER
    for p in paths:
        added_profiles = []
        p_norm = os.path.normcase(os.path.normpath(p))
        try:
            for prof in profiles:
                folders_path = prof["folders_path"]
                # skip if already present
                present = False
                try:
                    with _open_key(hkcu, folders_path) as folders_key:
                        for i in range(_winreg.QueryInfoKey(folders_key)[0]):
                            sub = _winreg.EnumKey(folders_key, i)
                            try:
                                with _open_key(hkcu, folders_path + "\\" + sub) as sk:
                                    val, _ = _winreg.QueryValueEx(sk, "")
                                    if val and os.path.normcase(os.path.normpath(val)) == p_norm:
                                        present = True
                                        break
                            except Exception:
                                continue
                except Exception:
                    # Can't read this folders path, skip
                    continue
                if present:
                    continue
                # Create a new subkey with unique name
                try:
                    with _open_key(hkcu, folders_path, access=_winreg.KEY_WRITE) as folders_key:
                        unique = f"DWGBATCH_{int(time.time())}"
                        # Ensure unique among siblings
                        i = 0
                        name = unique
                        while True:
                            try:
                                _winreg.OpenKey(folders_key, name)
                                i += 1
                                name = f"{unique}_{i}"
                            except FileNotFoundError:
                                break
                        sk = _winreg.CreateKey(folders_key, name)
                        _winreg.SetValueEx(sk, "", 0, _winreg.REG_SZ, p)
                        _winreg.CloseKey(sk)
                    added_profiles.append(f"{prof['version']} | {prof['product']} | {prof['profile']}")
                except Exception as ex:
                    result["failed"][p] = str(ex)
                    continue
        except Exception as ex:
            result["failed"][p] = str(ex)
            continue
        if added_profiles:
            result["added"][p] = added_profiles
        else:
            if p not in result["failed"]:
                result["skipped"].append(p)
    return result
