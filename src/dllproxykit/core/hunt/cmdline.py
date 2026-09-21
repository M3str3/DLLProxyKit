"""Parse ImagePath / scheduled-task Execute + Arguments. No PATH logic."""

from __future__ import annotations

import os
from pathlib import Path

_EXTS = (".exe", ".com", ".bat", ".cmd", ".ps1", ".dll")
_SHELLS = {
    "cmd",
    "cmd.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "wscript",
    "wscript.exe",
    "cscript",
    "cscript.exe",
}
_INVOKE = {"/c", "/k", "-c", "-command", "-file", "-f"}


def is_abs(path: str) -> bool:
    p = os.path.expandvars(path.strip().strip('"'))
    return os.path.isabs(p) or p.startswith("\\\\")


def split_image(pathname: str) -> tuple[str, str]:
    s = (pathname or "").strip()
    if not s:
        return "", ""
    if s.startswith('"'):
        end = s.find('"', 1)
        if end < 0:
            return s.strip('"'), ""
        return s[1:end], s[end + 1 :].strip()
    lower = s.lower()
    for ext in (".exe", ".com", ".bat", ".cmd", ".ps1"):
        i = lower.find(ext)
        if i >= 0:
            cut = i + len(ext)
            return s[:cut], s[cut:].strip()
    parts = s.split(None, 1)
    if not parts:
        return "", ""
    return parts[0], parts[1] if len(parts) > 1 else ""


def _tokens(args: str) -> list[str]:
    out: list[str] = []
    cur: list[str] = []
    q = False
    for ch in args:
        if ch == '"':
            q = not q
            continue
        if ch.isspace() and not q:
            if cur:
                out.append("".join(cur))
                cur = []
            continue
        cur.append(ch)
    if cur:
        out.append("".join(cur))
    return out


def bare_names(args: str, exe: str = "") -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    from_shell = image_basename(exe).lower() in _SHELLS
    after_invoke = False
    first_pos = True
    for raw in _tokens(args):
        flag = raw.lower()
        if raw.startswith("-") or raw.startswith("/"):
            after_invoke = flag in _INVOKE
            continue
        if raw in {">", "<", "|", "&"}:
            first_pos = False
            after_invoke = False
            continue
        if "\\" in raw or "/" in raw or (len(raw) >= 2 and raw[1] == ":"):
            first_pos = False
            after_invoke = False
            continue
        name = raw.strip()
        if not name or name.startswith("$"):
            first_pos = False
            after_invoke = False
            continue
        lower = name.lower()
        if any(lower.endswith(ext) for ext in _EXTS):
            key = name.lower()
        elif (
            from_shell
            and "." not in name
            and name.isalnum()
            and (after_invoke or first_pos)
        ):
            name = name + ".exe"
            key = name.lower()
        else:
            first_pos = False
            after_invoke = False
            continue
        first_pos = False
        after_invoke = False
        if key not in seen:
            seen.add(key)
            names.append(name)
    return names


def image_basename(exe: str) -> str:
    return Path(exe.strip().strip('"')).name
