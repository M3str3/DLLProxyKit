#!/usr/bin/env python3
"""Generate DLL proxies (C or Rust, chosen from the available compiler)."""

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
from ..core.common import (
    DEFAULT_PAYLOAD,
    DEFAULT_SKIP_DLL,
    Result,
    forwardable_exports,
    print_summary,
    orig_sidecar,
    resolve_io,
    skip_proxy_target,
)
from ..core.compiler import (
    MACHINE_TO_ARCH,
    Compiler,
    compile_dll,
    detect_compilers,
    require_compiler,
)
from ..langs import for_compiler


class DllInfo(NamedTuple):
    path: Path
    name: str
    exports: list[str]
    ordinal_only: int
    arch: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate DLL proxies that forward exports and run a payload.",
    )
    parser.add_argument("input", help="DLL file or directory")
    parser.add_argument("output", nargs="?", default=None, help="Output dir or DLL path")
    parser.add_argument("--payload", default=DEFAULT_PAYLOAD)
    parser.add_argument("--skip", default=",".join(DEFAULT_SKIP_DLL))
    parser.add_argument("--keep-going", action="store_true")
    return parser.parse_args()


def inspect_dll(path: Path) -> DllInfo:
    pe = pefile.PE(str(path), fast_load=True)
    try:
        machine = pe.FILE_HEADER.Machine
        arch = MACHINE_TO_ARCH.get(machine)
        if arch is None:
            raise ValueError(f"Unsupported architecture: 0x{machine:X}")
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]]
        )
        named: list[str] = []
        ordinal_only = 0
        if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
            for exp in pe.DIRECTORY_ENTRY_EXPORT.symbols:
                if exp.name:
                    named.append(exp.name.decode("utf-8", "replace"))
                else:
                    ordinal_only += 1
    finally:
        pe.close()
    return DllInfo(path=path, name=path.name, exports=named, ordinal_only=ordinal_only, arch=arch)


def should_skip(path: Path, skips: Iterable[str]) -> str | None:
    return skip_proxy_target(path, skips)


def process_one(
    dll_path: Path,
    out_dir: Path,
    workroot: Path,
    compilers: list[Compiler],
    dest_name: str | None = None,
) -> DllInfo:
    info = inspect_dll(dll_path)
    console.info(f"{info.name}  {info.arch}  {len(info.exports)} exports")
    if info.ordinal_only:
        console.warn(f"{info.ordinal_only} ordinal-only exports not forwarded")

    compiler = require_compiler(compilers, info.arch)
    exports, reserved = forwardable_exports(info.exports)
    if reserved:
        console.warn(f"not forwarding {', '.join(reserved)}")

    proxy_name = dest_name or info.name
    original_name = orig_sidecar(Path(proxy_name)).name

    proj = workroot / Path(proxy_name).stem
    if proj.exists():
        shutil.rmtree(proj)
    proj.mkdir(parents=True)

    lang = for_compiler(compiler)
    src, def_path = lang.write_dll(proj, original_name, exports)
    built = proj / "proxy.dll"
    compile_dll(compiler, src, built, def_path)

    (out_dir / original_name).write_bytes(dll_path.read_bytes())
    shutil.copy2(built, out_dir / proxy_name)
    console.ok(f"{proxy_name}  +  {original_name}  {console.dim(compiler.kind)}")
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
        dlls, out_dir, dest_name = resolve_io(
            Path(input).resolve(),
            str(output) if output is not None else None,
            ".dll",
        )
    except (FileNotFoundError, ValueError) as exc:
        console.fail(str(exc))
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)
    skip_str = skip if skip is not None else ",".join(DEFAULT_SKIP_DLL)
    skips = tuple(s.strip().lower() for s in skip_str.split(",") if s.strip())

    workroot = Path(tempfile.mkdtemp(prefix="dllproxy_"))

    succeeded: list[str] = []
    skipped: list[Result] = []
    failed: list[Result] = []

    for dll_path in dlls:
        reason = should_skip(dll_path, skips)
        if reason is not None:
            skipped.append(Result(dll_path.name, reason))
            continue
        try:
            info = process_one(dll_path, out_dir, workroot, compilers, dest_name)
            succeeded.append(info.name)
        except Exception as exc:
            failed.append(Result(dll_path.name, str(exc)))
            console.fail(f"{dll_path.name}  {exc}")
            if not keep_going:
                console.warn("aborting  (use --keep-going)")
                break

    print_summary("dll", succeeded, skipped, failed, out_dir)
    return 0 if not failed else 2


def main() -> int:
    args = parse_args()
    return run(args.input, args.output, args.payload, args.skip, args.keep_going)


if __name__ == "__main__":
    sys.exit(main())
