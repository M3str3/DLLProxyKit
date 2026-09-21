"""PE imports that would fall through to PATH (SafeDllSearchMode)."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from ..common import DEFAULT_SKIP_DLL
from ..pathscan import _norm_path, _win_dir
from .angle import path_chain, winning_dest
from .finding import Finding

if sys.platform == "win32":
    import winreg


_IMAGE_FILE_MACHINE_I386 = 0x014C


@lru_cache(maxsize=None)
def _wow64(exe: str) -> bool:
    try:
        import pefile
    except ImportError:
        return False
    try:
        pe = pefile.PE(exe, fast_load=True)
        wow = int(pe.FILE_HEADER.Machine) == _IMAGE_FILE_MACHINE_I386
    except Exception:
        return False
    closer = getattr(pe, "close", None)
    if callable(closer):
        closer()
    return wow


@lru_cache(maxsize=None)
def dll_search_dirs(exe_dir: str, scope: str, wow64: bool) -> tuple[Path, ...]:
    windir = _win_dir(
        "GetWindowsDirectoryW",
        Path(os.environ.get("SystemRoot", r"C:\Windows")),
    )
    if wow64:
        sysdir = windir / "SysWOW64"
    else:
        sysdir = _win_dir("GetSystemDirectoryW", windir / "System32")
    out: list[Path] = []
    seen: set[str] = set()
    for raw in (Path(exe_dir), sysdir, windir / "System", windir):
        key = _norm_path(raw)
        if key in seen:
            continue
        seen.add(key)
        out.append(raw)
    for item in path_chain(scope):
        key = _norm_path(item.path)
        if key in seen:
            continue
        seen.add(key)
        out.append(item.path)
    return tuple(out)


@lru_cache(maxsize=None)
def resolve_dll(name: str, exe_dir: str, scope: str, wow64: bool = False) -> Path | None:
    """First file SafeDllSearchMode would hit (exe dir → system → Windows → PATH)."""
    for folder in dll_search_dirs(exe_dir, scope, wow64):
        hit = folder / name
        try:
            if hit.is_file():
                return hit
        except OSError:
            continue
    return None


def _dir_index(folder: Path, dirs: tuple[Path, ...]) -> int | None:
    key = _norm_path(folder)
    for i, item in enumerate(dirs):
        if _norm_path(item) == key:
            return i
    return None


@lru_cache(maxsize=1)
def _known_dlls() -> set[str]:
    names: set[str] = set()
    if sys.platform != "win32":
        return names
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\Session Manager\KnownDLLs",
        ) as key:
            i = 0
            while True:
                try:
                    _name, value, _typ = winreg.EnumValue(key, i)
                except OSError:
                    break
                i += 1
                if isinstance(value, str) and value:
                    names.add(value.lower())
                    if not value.lower().endswith(".dll"):
                        names.add(value.lower() + ".dll")
    except OSError:
        pass
    return names


def _dll_name(raw: object) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    return str(raw)


@lru_cache(maxsize=None)
def _imported(exe: str) -> list[str]:
    try:
        import pefile
    except ImportError:
        return []
    try:
        pe = pefile.PE(exe, fast_load=True)
    except Exception:
        return []
    names: list[str] = []
    try:
        for kind, attr in (
            ("IMAGE_DIRECTORY_ENTRY_IMPORT", "DIRECTORY_ENTRY_IMPORT"),
            ("IMAGE_DIRECTORY_ENTRY_DELAY_IMPORT", "DIRECTORY_ENTRY_DELAY_IMPORT"),
        ):
            mapping = pefile.DIRECTORY_ENTRY
            idx = mapping[kind] if kind in mapping else None
            if idx is None:
                continue
            try:
                pe.parse_data_directories(directories=[idx])
            except Exception:
                continue
            for entry in getattr(pe, attr, None) or []:
                name = _dll_name(getattr(entry, "dll", None))
                if name:
                    names.append(name)
    except Exception:
        pass
    finally:
        closer = getattr(pe, "close", None)
        if callable(closer):
            closer()
    out: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _skip_dll(name: str, known: set[str]) -> bool:
    lower = name.lower()
    if lower in known:
        return True
    if lower.startswith("api-ms-") or lower.startswith("ext-ms-"):
        return True
    for prefix in DEFAULT_SKIP_DLL:
        if prefix in lower:
            return True
    return False


def dll_findings(
    exe: str,
    *,
    source: str,
    title: str,
    account: str,
    command: str,
    scope: str,
    unsafe: bool,
) -> list[Finding]:
    path = Path(os.path.expandvars(exe.strip().strip('"')))
    try:
        if not path.is_file():
            return []
    except OSError:
        return []
    known = _known_dlls()
    exe_dir = str(path.parent)
    wow64 = _wow64(str(path))
    dirs = dll_search_dirs(exe_dir, scope, wow64)
    out: list[Finding] = []
    for dll in _imported(str(path)):
        if _skip_dll(dll, known):
            continue
        dest = winning_dest(dll, scope, unsafe=unsafe)
        if dest is None:
            continue
        dest_i = _dir_index(dest.path, dirs)
        if dest_i is None:
            continue
        resolved = resolve_dll(dll, exe_dir, scope, wow64)
        if resolved is not None:
            hit_i = _dir_index(resolved.parent, dirs)
            if hit_i is not None and dest_i >= hit_i:
                continue
        out.append(
            Finding(
                kind="dll",
                source=source,
                title=title,
                account=account,
                command=command,
                target=dll,
                dest=dest,
                scope=scope,
                why=str(resolved) if resolved is not None else "not on search path",
            )
        )
    return out
