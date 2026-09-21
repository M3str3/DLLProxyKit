"""Writable dest vs machine/user PATH. Finding only if dest would win."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from ..pathscan import PathDir, _norm_path, _reg_path, _split_path, auto_targets, scan_path_dirs

if sys.platform == "win32":
    import winreg


def scope_for_account(account: str) -> str:
    a = (account or "").upper()
    if not a or a.startswith("NT AUTHORITY") or a.startswith("S-1-5-18") or a.startswith("S-1-5-19") or a.startswith("S-1-5-20"):
        return "machine"
    compact = a.replace(" ", "")
    for marker in (
        "LOCALSYSTEM",
        "LOCALSERVICE",
        "NETWORKSERVICE",
        "SERVICIOLOCAL",
        "SERVICIODERED",
        "SISTEMA",
        "SYSTEM",
    ):
        if marker in compact:
            return "machine"
    return "user"


def _chain_from_blob(blob: str, by_key: dict[str, PathDir]) -> list[PathDir]:
    out: list[PathDir] = []
    seen: set[str] = set()
    for raw in _split_path(blob):
        try:
            path = Path(os.path.expandvars(raw)).expanduser()
        except Exception:
            continue
        key = _norm_path(path)
        if key in seen:
            continue
        seen.add(key)
        item = by_key.get(key)
        if item is not None:
            out.append(item)
    return out


@lru_cache(maxsize=None)
def path_chain(scope: str) -> list[PathDir]:
    entries = scan_path_dirs()
    by_key = {_norm_path(e.path): e for e in entries}
    if scope == "machine":
        blob = ""
        if sys.platform == "win32":
            blob = _reg_path(
                winreg.HKEY_LOCAL_MACHINE,
                r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
            )
        return _chain_from_blob(blob, by_key)
    ranked = [e for e in entries if e.rank is not None]
    ranked.sort(key=lambda e: e.rank or 0)
    return ranked


@lru_cache(maxsize=None)
def _targets(unsafe: bool) -> tuple[PathDir, ...]:
    return tuple(auto_targets(unsafe=unsafe))


def _index(chain: list[PathDir], folder: PathDir) -> int | None:
    key = _norm_path(folder.path)
    for i, item in enumerate(chain):
        if _norm_path(item.path) == key:
            return i
    return None


def _has_file(folder: Path, name: str) -> bool:
    try:
        return (folder / name).is_file()
    except OSError:
        return False


def first_hit(name: str, chain: list[PathDir]) -> tuple[int, PathDir] | None:
    for i, item in enumerate(chain):
        if item.exists and _has_file(item.path, name):
            return i, item
    return None


@lru_cache(maxsize=None)
def winning_dest(name: str, scope: str, *, unsafe: bool = False) -> PathDir | None:
    chain = path_chain(scope)
    if not chain:
        return None
    dests = _targets(unsafe)
    best: tuple[int, PathDir] | None = None
    for dest in dests:
        idx = _index(chain, dest)
        if idx is None:
            continue
        if best is None or idx < best[0]:
            best = (idx, dest)
    if best is None:
        return None
    dest_i, dest = best
    hit = first_hit(name, chain)
    if hit is None:
        return dest
    hit_i, _ = hit
    if dest_i < hit_i:
        return dest
    return None
