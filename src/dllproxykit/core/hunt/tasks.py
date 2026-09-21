"""Scheduled tasks: relative Execute or bare names in Arguments."""

from __future__ import annotations

import json
import subprocess
import sys

from .angle import scope_for_account, winning_dest
from .cmdline import bare_names, image_basename, is_abs, split_image
from .dlls import dll_findings
from .finding import Finding


def _tasks() -> list[dict]:
    if sys.platform != "win32":
        return []
    ps = (
        "Get-ScheduledTask | ForEach-Object { "
        "$p = $_.Principal; "
        "foreach ($a in @($_.Actions)) { "
        "[pscustomobject]@{ "
        "TaskName = $_.TaskName; TaskPath = $_.TaskPath; "
        "Execute = $a.Execute; Arguments = $a.Arguments; "
        "UserId = $p.UserId "
        "} } } | ConvertTo-Json -Compress"
    )
    try:
        raw = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=90,
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
        source="task",
        title=title,
        account=account,
        command=command,
        target=target,
        dest=dest,
        scope=scope,
        why=why,
    )


def hunt_tasks(*, unsafe: bool = False) -> list[Finding]:
    out: list[Finding] = []
    for row in _tasks():
        execute = (row.get("Execute") or "").strip()
        arguments = (row.get("Arguments") or "").strip()
        if not execute:
            continue
        title = (row.get("TaskPath") or "") + (row.get("TaskName") or "")
        account = row.get("UserId") or ""
        scope = scope_for_account(account)
        command = f"{execute} {arguments}".strip()
        exe, extra = split_image(execute)
        args = f"{extra} {arguments}".strip()
        if exe and not is_abs(exe):
            target = image_basename(exe) or exe
            hit = _path_finding(
                title=title,
                account=account,
                command=command,
                target=target,
                scope=scope,
                why="relative Execute",
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
                    source="task",
                    title=title,
                    account=account,
                    command=command,
                    scope=scope,
                    unsafe=unsafe,
                )
            )
    return out
