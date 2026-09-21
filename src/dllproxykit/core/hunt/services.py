"""Win32 services: relative ImagePath or bare names in args."""

from __future__ import annotations

import json
import subprocess
import sys

from .angle import scope_for_account, winning_dest
from .cmdline import bare_names, image_basename, is_abs, split_image
from .dlls import dll_findings
from .finding import Finding


def _services() -> list[dict]:
    if sys.platform != "win32":
        return []
    ps = (
        "Get-CimInstance Win32_Service | "
        "Select-Object Name, DisplayName, PathName, StartName, State | "
        "ConvertTo-Json -Compress"
    )
    try:
        raw = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if raw.returncode != 0 or not raw.stdout.strip():
        return []
    try:
        data = json.loads(raw.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        return [data]
    return data if isinstance(data, list) else []


def _path_finding(
    *,
    title: str,
    account: str,
    command: str,
    target: str,
    scope: str,
    why: str,
    unsafe: bool,
) -> Finding | None:
    dest = winning_dest(target, scope, unsafe=unsafe)
    if dest is None:
        return None
    return Finding(
        kind="path",
        source="service",
        title=title,
        account=account,
        command=command,
        target=target,
        dest=dest,
        scope=scope,
        why=why,
    )


def hunt_services(*, unsafe: bool = False) -> list[Finding]:
    out: list[Finding] = []
    for row in _services():
        command = (row.get("PathName") or "").strip()
        if not command:
            continue
        title = row.get("Name") or row.get("DisplayName") or ""
        account = row.get("StartName") or ""
        scope = scope_for_account(account)
        exe, args = split_image(command)
        if exe and not is_abs(exe):
            target = image_basename(exe) or exe
            hit = _path_finding(
                title=title,
                account=account,
                command=command,
                target=target,
                scope=scope,
                why="relative ImagePath",
                unsafe=unsafe,
            )
            if hit:
                out.append(hit)
        for name in bare_names(args, exe):
            hit = _path_finding(
                title=title,
                account=account,
                command=command,
                target=name,
                scope=scope,
                why="bare name in args",
                unsafe=unsafe,
            )
            if hit:
                out.append(hit)
        if exe and is_abs(exe):
            out.extend(
                dll_findings(
                    exe,
                    source="service",
                    title=title,
                    account=account,
                    command=command,
                    scope=scope,
                    unsafe=unsafe,
                )
            )
    return out
