from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path
from typing import NamedTuple

if sys.platform == "win32":
    import winreg


class PathDir(NamedTuple):
    path: Path
    writable: bool
    exists: bool
    sources: tuple[str, ...]
    rank: int | None


def _split_path(value: str) -> list[str]:
    out: list[str] = []
    for raw in value.split(os.pathsep):
        raw = raw.strip().strip('"')
        if raw:
            out.append(raw)
    return out


def _reg_path(root: int, subkey: str) -> str:
    try:
        with winreg.OpenKey(root, subkey) as key:
            value, typ = winreg.QueryValueEx(key, "Path")
    except OSError:
        return ""
    if not isinstance(value, str):
        return ""
    if typ == winreg.REG_EXPAND_SZ:
        value = os.path.expandvars(value)
    return value


def _path_sources() -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = [("process", os.environ.get("PATH", ""))]
    if sys.platform == "win32":
        chunks.append(
            (
                "user",
                _reg_path(winreg.HKEY_CURRENT_USER, r"Environment"),
            )
        )
        chunks.append(
            (
                "machine",
                _reg_path(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                ),
            )
        )
    return chunks


def is_writable(directory: Path) -> bool:
    if not directory.is_dir():
        return False
    probe = directory / f".phjwrite_{os.getpid()}.tmp"
    try:
        fd = os.open(str(probe), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
        os.unlink(str(probe))
        return True
    except OSError:
        return False


def _norm_key(raw: str) -> tuple[str, Path] | None:
    try:
        path = Path(os.path.expandvars(raw)).expanduser()
        return os.path.normcase(str(path)), path
    except Exception:
        return None


def scan_path_dirs() -> list[PathDir]:
    sources_by_key: dict[str, list[str]] = {}
    order: list[Path] = []
    rank_by_key: dict[str, int] = {}

    for source, blob in _path_sources():
        for raw in _split_path(blob):
            parsed = _norm_key(raw)
            if parsed is None:
                continue
            key, path = parsed
            if key not in sources_by_key:
                sources_by_key[key] = []
                order.append(path)
            if source not in sources_by_key[key]:
                sources_by_key[key].append(source)
            if source == "process" and key not in rank_by_key:
                rank_by_key[key] = len(rank_by_key) + 1

    result: list[PathDir] = []
    for path in order:
        key = os.path.normcase(str(path))
        exists = path.is_dir()
        result.append(
            PathDir(
                path=path,
                exists=exists,
                writable=is_writable(path),
                sources=tuple(sources_by_key[key]),
                rank=rank_by_key.get(key),
            )
        )
    return result


def _win_dir(fn_name: str, fallback: Path) -> Path:
    if sys.platform != "win32":
        return fallback
    try:
        buf = ctypes.create_unicode_buffer(260)
        n = getattr(ctypes.windll.kernel32, fn_name)(buf, len(buf))
        if n:
            return Path(buf.value)
    except Exception:
        pass
    return fallback


def _norm_path(path: Path) -> str:
    try:
        return os.path.normcase(str(path.resolve()))
    except OSError:
        return os.path.normcase(str(path))


def outside_home(path: Path) -> bool:
    home = _norm_path(Path.home())
    p = _norm_path(path)
    return p != home and not p.startswith(home + os.sep)


def is_windows_dir(path: Path) -> bool:
    windir = _win_dir(
        "GetWindowsDirectoryW",
        Path(os.environ.get("SystemRoot", r"C:\Windows")),
    )
    root = _norm_path(windir)
    p = _norm_path(path)
    return p == root or p.startswith(root + os.sep)


def auto_targets() -> list[PathDir]:
    return [
        item
        for item in scan_path_dirs()
        if item.exists
        and item.writable
        and outside_home(item.path)
        and not is_windows_dir(item.path)
    ]


def dll_search_before_path() -> list[tuple[str, str]]:
    """Locations LoadLibrary searches before PATH (SafeDllSearchMode on)."""
    windir = _win_dir("GetWindowsDirectoryW", Path(os.environ.get("SystemRoot", r"C:\Windows")))
    sysdir = _win_dir("GetSystemDirectoryW", windir / "System32")
    return [
        ("1", "application directory  (folder of the target .exe)"),
        ("2", str(sysdir)),
        ("3", str(windir / "System")),
        ("4", str(windir)),
        ("5", f"current directory  ({Path.cwd()})"),
    ]


def path_dirs() -> list[Path]:
    return [item.path for item in scan_path_dirs()]


def writable_path_dirs() -> list[Path]:
    return [item.path for item in scan_path_dirs() if item.writable]
