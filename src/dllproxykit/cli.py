#!/usr/bin/env python3
"""DLLProxyKit CLI."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import ui as console
from .makers.auto import run_auto, run_revert
from .core.common import DEFAULT_PAYLOAD, PAYLOAD_FALLBACK, ensure_fallback_payload
from .core.compiler import detect_compilers, select_compilers
from .makers.kinds import parse_kinds
from .core.pathscan import dll_search_before_path, outside_home, scan_path_dirs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate DLL/EXE proxies (C or Rust).",
    )
    parser.add_argument(
        "input",
        nargs="?",
        default=None,
        help="DLL/EXE file or directory",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Output directory or file (default: same folder as input)",
    )
    parser.add_argument(
        "--payload",
        "--command",
        dest="payload",
        default=DEFAULT_PAYLOAD,
        help="Command executed by the proxy (written to C:\\Windows\\Temp\\payload.txt)",
    )
    parser.add_argument(
        "--skip",
        default=None,
        help="Comma-separated substrings to skip",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue if one file or maker fails",
    )
    parser.add_argument(
        "--scan-path",
        action="store_true",
        help="Only list PATH directories that are writable, then exit",
    )
    parser.add_argument(
        "-i",
        "--include",
        default=None,
        help="Comma-separated kinds: dll,exe,bat,cmd,ps1,pl,py (default: all)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Select writable PATH dirs outside the user profile",
    )
    parser.add_argument(
        "--revert",
        action="store_true",
        help="Restore .original.* instead of generating proxies",
    )
    parser.add_argument(
        "--compiler",
        default=None,
        help="Force a compiler: cl / gcc / clang / tcc / rustc, or a path to an exe",
    )
    return parser.parse_args()


def show_compilers(compilers) -> None:
    console.section("compilers")
    if not compilers:
        console.fail("none found  (cl / gcc / clang / tcc / rustc)")
        return
    for c in compilers:
        extra = f" {' '.join(c.extra_args)}" if c.extra_args else ""
        console.ok(f"{c.kind}{extra}  {console.dim(c.arch)}  {c.path}")


def _path_line(item) -> str:
    rank = f"#{item.rank:<3}" if item.rank is not None else " -  "
    path = str(item.path)
    if item.writable and outside_home(item.path):
        path = console.hot(path)
    src = console.dim("  [" + ",".join(item.sources) + "]")
    return f"{rank} {path}{src}"


def _emit_path(item) -> None:
    line = _path_line(item)
    if item.writable:
        console.ok(line)
    elif item.exists:
        console.fail(line)
    else:
        console.warn(line)


def show_path_scan(*, full: bool) -> None:
    entries = scan_path_dirs()
    writable = [e for e in entries if e.writable]
    ranked = sorted(
        [e for e in entries if e.rank is not None],
        key=lambda e: e.rank,
    )
    registry_only = [e for e in entries if e.rank is None]

    console.section(f"writable PATH  {len(writable)}/{len(entries)}")
    if writable:
        for item in writable:
            _emit_path(item)
    else:
        console.warn("none")
    console.info("lower # loads first; exe dir, System32, Windows and cwd beat PATH")

    if not full:
        return

    console.section("DLL search order  (first match wins)")
    console.info("before PATH")
    for num, label in dll_search_before_path():
        console.item(f"{num}  {label}")
    console.info("PATH")
    if ranked:
        for item in ranked:
            _emit_path(item)
    else:
        console.warn("empty")
    if registry_only:
        console.info("in registry, not in this process PATH")
        for item in registry_only:
            _emit_path(item)


def _payload_hint() -> None:
    print()
    print(
        f"  {console.green('✎')}  {console.green(str(PAYLOAD_FALLBACK))}"
        f"  <--  {console.under('You can write command here!!')}"
    )
    print()


def main() -> int:
    args = parse_args()
    console.setup()
    console.banner()

    show_path_scan(full=args.scan_path)
    if args.scan_path and args.input is None and not args.auto and not args.revert:
        print()
        return 0

    try:
        kinds = parse_kinds(args.include)
    except ValueError as exc:
        console.fail(str(exc))
        print()
        return 1

    if args.revert:
        target = None if args.auto or args.input is None else args.input
        if target is None and not args.auto:
            console.warn(
                console.yell(
                    "--revert with no target restores every writable PATH dir used by --auto"
                )
            )
            console.info("Ctrl+C to cancel")
            for n in range(5, 0, -1):
                console.info(f"{n}...")
                time.sleep(1)
        rc = run_revert(target, kinds=kinds)
        print()
        return rc

    compilers = []
    if any(k.compile for k in kinds):
        compilers = detect_compilers()
        if args.compiler:
            chosen = select_compilers(compilers, args.compiler)
            if not chosen:
                show_compilers(compilers)
                console.fail(f"compiler not found  {args.compiler}")
                print()
                return 1
            compilers = chosen
        show_compilers(compilers)
        if not compilers:
            print()
            return 1

    if args.auto:
        ensure_fallback_payload(args.payload)
        rc = run_auto(args.payload, args.skip, compilers, kinds=kinds)
        _payload_hint()
        return rc

    if args.input is None:
        console.fail("missing input (file or directory)")
        print()
        return 1

    src = Path(args.input)
    kwargs = dict(
        input=args.input,
        output=args.output,
        payload=args.payload,
        skip=args.skip,
        keep_going=args.keep_going,
        compilers=compilers,
    )

    if src.is_file():
        ext = src.suffix.lower()
        kind = next((k for k in kinds if k.ext == ext), None)
        if kind is None:
            exts = " / ".join(k.ext for k in kinds)
            console.fail(f"input must be {exts}  {src}")
            print()
            return 1
        jobs = [(ext[1:].upper(), kind.proxy)]
    elif src.is_dir():
        jobs = [(k.ext[1:].upper(), k.proxy) for k in kinds]
    else:
        console.fail(f"input does not exist  {src}")
        print()
        return 1

    rc = 0
    ensure_fallback_payload(args.payload)
    for label, fn in jobs:
        console.section(f"{label} proxies")
        result = fn(**kwargs)
        if result != 0:
            rc = result
            if not args.keep_going:
                _payload_hint()
                return rc
    _payload_hint()
    return rc


if __name__ == "__main__":
    sys.exit(main())
