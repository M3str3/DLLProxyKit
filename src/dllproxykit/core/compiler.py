#!/usr/bin/env python3
"""Detect C compilers on PATH (and next to the frozen exe) and compile proxies."""

from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import NamedTuple

ARCH_X86 = "x86"
ARCH_X64 = "x64"
ARCH_ARM64 = "arm64"

MACHINE_TO_ARCH: dict[int, str] = {
    0x014C: ARCH_X86,
    0x8664: ARCH_X64,
    0xAA64: ARCH_ARM64,
}


class Compiler(NamedTuple):
    kind: str
    path: str
    arch: str
    extra_args: tuple[str, ...] = ()


def pe_arch(path: Path) -> str | None:
    data = path.read_bytes()[:1024]
    if len(data) < 0x40 or data[:2] != b"MZ":
        return None
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if e_lfanew + 6 > len(data) or data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
        try:
            data = path.read_bytes()[: e_lfanew + 8]
        except OSError:
            return None
        if data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
            return None
    machine = struct.unpack_from("<H", data, e_lfanew + 4)[0]
    return MACHINE_TO_ARCH.get(machine)


def _run(cmd: list[str]) -> str:
    result = subprocess.run(
        cmd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return (result.stdout or "") + (result.stderr or "")


def _which(name: str) -> str | None:
    return shutil.which(name)


def _nearby_tcc() -> list[str]:
    roots = [Path(sys.executable).resolve().parent]
    found: list[str] = []
    for root in roots:
        for cand in (root / "tcc.exe", root / "tcc" / "tcc.exe"):
            if cand.is_file():
                found.append(str(cand))
    found.extend(_bundled_tcc())
    return found


def _tcc_zip() -> Path | None:
    cand = Path(__file__).resolve().parents[1] / "tcc.zip"
    if cand.is_file():
        return cand
    return None


def _is_tcc_exe(path: Path) -> bool:
    name = path.name.lower()
    return name == "tcc.exe" or name.endswith("-tcc.exe")


def _find_tcc_exes(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return [p for p in root.rglob("*.exe") if p.is_file() and _is_tcc_exe(p)]


def _bundled_tcc() -> list[str]:
    dest = Path(tempfile.gettempdir()) / "dllproxykit-tcc"
    found = _find_tcc_exes(dest)
    if found:
        return [str(p) for p in found]
    zpath = _tcc_zip()
    if zpath is None:
        return []
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(dest)
    except (OSError, zipfile.BadZipFile):
        return []
    return [str(p) for p in _find_tcc_exes(dest)]


def _tcc_target_arch(path: Path) -> str:
    name = path.name.lower()
    if "i386" in name or name.startswith("i686"):
        return ARCH_X86
    if "aarch64" in name or "arm64" in name:
        return ARCH_ARM64
    if "x86_64" in name or "amd64" in name:
        return ARCH_X64
    return pe_arch(path) or ARCH_X64


def _arch_from_dumpmachine(text: str) -> str | None:
    t = text.strip().lower()
    if "aarch64" in t or "arm64" in t:
        return ARCH_ARM64
    if "x86_64" in t or "amd64" in t:
        return ARCH_X64
    if "i686" in t or "i386" in t or t.startswith("i586"):
        return ARCH_X86
    return None


def _probe_cl(path: str) -> list[Compiler]:
    banner = _run([path]).lower()
    if "arm64" in banner:
        arch = ARCH_ARM64
    elif "x86" in banner and "x64" not in banner and "x86_64" not in banner:
        arch = ARCH_X86
    elif "x64" in banner or "amd64" in banner:
        arch = ARCH_X64
    else:
        arch = pe_arch(Path(path)) or ARCH_X64
    return [Compiler("cl", path, arch)]


ARCH_TO_RUST: dict[str, str] = {
    ARCH_X86: "i686-pc-windows-msvc",
    ARCH_X64: "x86_64-pc-windows-msvc",
    ARCH_ARM64: "aarch64-pc-windows-msvc",
}


def _probe_gnu(kind: str, path: str) -> list[Compiler]:
    dumped = _arch_from_dumpmachine(_run([path, "-dumpmachine"]))
    arch = dumped or pe_arch(Path(path)) or ARCH_X64
    return [Compiler(kind, path, arch)]


def _probe_rustc(path: str) -> list[Compiler]:
    installed: set[str] = set()
    rustup = _which("rustup")
    if rustup:
        for line in _run([rustup, "target", "list", "--installed"]).splitlines():
            t = line.strip()
            if t:
                installed.add(t)
    verbose = _run([path, "-vV"])
    for line in verbose.splitlines():
        if line.startswith("host:"):
            installed.add(line.split(":", 1)[1].strip())
    out: list[Compiler] = []
    for arch, triple in ARCH_TO_RUST.items():
        if triple in installed:
            out.append(Compiler("rustc", path, arch, (triple,)))
    return out


def _probe_tcc(path: str) -> list[Compiler]:
    arch = _tcc_target_arch(Path(path))
    return [Compiler("tcc", path, arch)]


def detect_compilers() -> list[Compiler]:
    found: list[Compiler] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()

    def add(items: list[Compiler]) -> None:
        for item in items:
            key = (item.kind, item.arch, item.extra_args)
            if key in seen:
                continue
            seen.add(key)
            found.append(item)

    cl = _which("cl")
    if cl:
        add(_probe_cl(cl))

    for name, kind in (
        ("gcc", "gcc"),
        ("clang", "clang"),
        ("i686-w64-mingw32-gcc", "gcc"),
        ("x86_64-w64-mingw32-gcc", "gcc"),
        ("aarch64-w64-mingw32-gcc", "gcc"),
    ):
        path = _which(name)
        if path:
            add(_probe_gnu(kind, path))
            parent = Path(path).parent
            sibling = parent / "i686-w64-mingw32-gcc.exe"
            if sibling.is_file():
                add(_probe_gnu("gcc", str(sibling)))

    tcc_paths = []
    w = _which("tcc")
    if w:
        tcc_paths.append(w)
    tcc_paths.extend(_nearby_tcc())
    for path in tcc_paths:
        add(_probe_tcc(path))

    rustc = _which("rustc")
    if rustc:
        add(_probe_rustc(rustc))

    return found


def _probe_by_path(path: str) -> list[Compiler]:
    name = Path(path).name.lower()
    if name.startswith("cl"):
        return _probe_cl(path)
    if "rustc" in name:
        return _probe_rustc(path)
    if name.startswith("tcc"):
        return _probe_tcc(path)
    if "clang" in name:
        return _probe_gnu("clang", path)
    return _probe_gnu("gcc", path)


def select_compilers(detected: list[Compiler], spec: str | None) -> list[Compiler]:
    if not spec:
        return detected
    path = Path(spec)
    if path.is_file():
        return _probe_by_path(str(path.resolve()))
    kind = spec.lower()
    return [c for c in detected if c.kind == kind]


def pick_compiler(compilers: list[Compiler], arch: str) -> Compiler | None:
    native = [c for c in compilers if c.arch == arch and c.kind != "rustc"]
    rust = [c for c in compilers if c.arch == arch and c.kind == "rustc"]
    if native:
        return native[0]
    if rust:
        return rust[0]
    return None


def require_compiler(compilers: list[Compiler], arch: str) -> Compiler:
    compiler = pick_compiler(compilers, arch)
    if compiler:
        return compiler
    have = ", ".join(
        f"{c.kind} ({c.arch}{' ' + ' '.join(c.extra_args) if c.extra_args else ''})"
        for c in compilers
    ) or "none"
    raise RuntimeError(
        f"This file is {arch}; no matching compiler. Found: {have}. "
        f"Need a {arch} C toolchain, or `rustup target add {ARCH_TO_RUST.get(arch, arch)}`."
    )


def _check(result: subprocess.CompletedProcess[str], label: str) -> None:
    if result.returncode != 0:
        from .. import ui as console
        console.fail(f"{label} failed")
        text = (result.stdout or "") + (result.stderr or "")
        for line in text.splitlines()[:20]:
            console.item(console.dim(line))
        raise RuntimeError(f"{label} failed")


def compile_dll(
    compiler: Compiler,
    src_c: Path,
    out_dll: Path,
    def_file: Path | None = None,
) -> Path:
    src_c = Path(src_c)
    out_dll = Path(out_dll)
    cwd = src_c.parent
    def_name = def_file.name if def_file else None

    if compiler.kind == "rustc":
        cmd = [
            compiler.path, "--edition", "2021", "--crate-type", "cdylib",
            "-C", "opt-level=z", "--target", compiler.extra_args[0],
            "-o", out_dll.name, src_c.name,
        ]
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace"
        )
        _check(result, "compile dll")
        if not out_dll.exists():
            raise RuntimeError(f"Compiled DLL not found: {out_dll}")
        return out_dll

    if compiler.kind == "cl":
        cmd = [
            compiler.path, "/nologo", "/O2", "/LD",
            src_c.name, f"/Fe:{out_dll.name}",
        ]
        if def_name:
            cmd += ["/link", f"/DEF:{def_name}"]
    else:
        cmd = [
            compiler.path, *compiler.extra_args,
            "-shared", "-O2", "-o", out_dll.name, src_c.name,
        ]
        if def_name:
            cmd.append(def_name)
        cmd.append("-lkernel32")

    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace"
    )
    _check(result, "compile dll")
    if not out_dll.exists():
        raise RuntimeError(f"Compiled DLL not found: {out_dll}")
    return out_dll


def compile_exe(compiler: Compiler, src_c: Path, out_exe: Path) -> Path:
    src_c = Path(src_c)
    out_exe = Path(out_exe)
    cwd = src_c.parent

    if compiler.kind == "rustc":
        cmd = [
            compiler.path, "--edition", "2021",
            "-C", "opt-level=z", "--target", compiler.extra_args[0],
            "-o", out_exe.name, src_c.name,
        ]
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace"
        )
        _check(result, "compile exe")
        if not out_exe.exists():
            raise RuntimeError(f"Compiled EXE not found: {out_exe}")
        return out_exe

    if compiler.kind == "cl":
        cmd = [
            compiler.path, "/nologo", "/O2",
            src_c.name, f"/Fe:{out_exe.name}",
        ]
    else:
        cmd = [
            compiler.path, *compiler.extra_args,
            "-O2", "-o", out_exe.name, src_c.name, "-lkernel32",
        ]

    result = subprocess.run(
        cmd, cwd=cwd, capture_output=True, encoding="utf-8", errors="replace"
    )
    _check(result, "compile exe")
    if not out_exe.exists():
        raise RuntimeError(f"Compiled EXE not found: {out_exe}")
    return out_exe
