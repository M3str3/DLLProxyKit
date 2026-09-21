#!/usr/bin/env python3
"""Generate EXE proxies (C or Rust, chosen from the available compiler)."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Iterable, NamedTuple

try:
    import pefile
except ImportError:
    print("[!] Missing dependency: pefile. Install with: pip install pefile")
    sys.exit(1)

from .. import ui as console
from ..core.common import DEFAULT_PAYLOAD, Result, forward_target, note_proxy, orig_sidecar, print_summary, resolve_io, skip_proxy_target
from ..core.compiler import (
    MACHINE_TO_ARCH,
    Compiler,
    compile_exe,
    detect_compilers,
    require_compiler,
)
from ..langs import for_compiler


class ExeInfo(NamedTuple):
    path: Path
    name: str
    arch: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate EXE proxies that run a payload and forward arguments.",
    )
    parser.add_argument("input", help="EXE file or directory")
    parser.add_argument("output", nargs="?", default=None, help="Output dir or EXE path")
    parser.add_argument("--payload", default=DEFAULT_PAYLOAD)
    parser.add_argument("--skip", default="")
    parser.add_argument("--keep-going", action="store_true")
    return parser.parse_args()


def inspect_exe(path: Path) -> ExeInfo:
    pe = pefile.PE(str(path), fast_load=True)
    try:
        machine = pe.FILE_HEADER.Machine
        arch = MACHINE_TO_ARCH.get(machine)
        if arch is None:
            raise ValueError(f"Unsupported architecture: 0x{machine:X}")
    finally:
        pe.close()
    return ExeInfo(path=path, name=path.name, arch=arch)


def should_skip(path: Path, skips: Iterable[str], out_dir: Path | None = None) -> str | None:
    return skip_proxy_target(path, skips, out_dir)


def process_one(
    exe_path: Path,
    out_dir: Path,
    workroot: Path,
    compilers: list[Compiler],
    dest_name: str | None = None,
) -> ExeInfo:
    info = inspect_exe(exe_path)
    console.info(f"{info.name}  {info.arch}")

    compiler = require_compiler(compilers, info.arch)
    proxy_name = dest_name or info.name
    original_name = orig_sidecar(Path(proxy_name)).name
    launch = forward_target(exe_path, out_dir, proxy_name)

    proj = workroot / Path(proxy_name).stem
    if proj.exists():
        shutil.rmtree(proj)
    proj.mkdir(parents=True)

    lang = for_compiler(compiler)
    src = lang.write_exe(proj, launch)
    built = proj / "proxy.exe"
    compile_exe(compiler, src, built)

    note_proxy(exe_path, out_dir, proxy_name)
    shutil.copy2(built, out_dir / proxy_name)
    if (out_dir / original_name).is_file():
        console.ok(f"{proxy_name}  +  {original_name}  {console.dim(compiler.kind)}")
    else:
        console.ok(f"{proxy_name}  {console.dim(compiler.kind)}")
    return info


def run(
    input: str | Path,
    output: str | Path | None = None,
    payload: str = DEFAULT_PAYLOAD,
    skip: str | None = None,
    keep_going: bool = False,
    compilers: list[Compiler] | None = None,
) -> int:
    if compilers is None:
        compilers = detect_compilers()
    if not compilers:
        console.fail("no compiler found")
        return 1

    try:
        exes, out_dir, dest_name = resolve_io(
            Path(input).resolve(),
            str(output) if output is not None else None,
            ".exe",
        )
    except (FileNotFoundError, ValueError) as exc:
        console.fail(str(exc))
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    skip_str = skip or ""
    skips = tuple(s.strip().lower() for s in skip_str.split(",") if s.strip())

    workroot = Path(tempfile.mkdtemp(prefix="exeproxy_"))

    succeeded: list[str] = []
    skipped: list[Result] = []
    failed: list[Result] = []

    for exe_path in exes:
        reason = should_skip(exe_path, skips, out_dir)
        if reason is not None:
            skipped.append(Result(exe_path.name, reason))
            continue
        try:
            info = process_one(exe_path, out_dir, workroot, compilers, dest_name)
            succeeded.append(info.name)
        except Exception as exc:
            failed.append(Result(exe_path.name, str(exc)))
            console.fail(f"{exe_path.name}  {exc}")
            console.debug_exc()
            if not keep_going:
                console.warn("aborting  (use --keep-going)")
                break

    print_summary("exe", succeeded, skipped, failed, out_dir)
    return 0 if not failed else 2


def main() -> int:
    args = parse_args()
    return run(args.input, args.output, args.payload, args.skip, args.keep_going)


if __name__ == "__main__":
    sys.exit(main())
