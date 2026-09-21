"""Plant a fake DLL with no original: DllMain payload, optional zero stubs."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from .. import ui as console
from ..core.common import (
    DEFAULT_PAYLOAD,
    Result,
    albaran_note,
    albaran_read,
    forwardable_exports,
    orig_sidecar,
    print_summary,
)
from ..core.compiler import Compiler, compile_dll, detect_compilers, require_compiler
from ..core.pathscan import auto_targets
from ..langs import for_compiler


def _dll_name(raw: str) -> str:
    name = Path(raw.strip()).name
    if not name:
        raise ValueError("empty DLL name")
    if not name.lower().endswith(".dll"):
        name += ".dll"
    return name


def _dest_dir(output: str | Path | None, *, unsafe: bool) -> Path | None:
    if output is not None:
        return Path(output).expanduser().resolve()
    ranked = [item for item in auto_targets(unsafe=unsafe) if item.rank is not None]
    if not ranked:
        return None
    return min(ranked, key=lambda item: item.rank).path


def _skip(name: str, out_dir: Path) -> str | None:
    dest = out_dir / name
    if orig_sidecar(dest).exists():
        return "already proxied"
    planted = any(
        action == "plant" and existing.lower() == name.lower()
        for action, existing, _extra in albaran_read(out_dir)
    )
    if dest.exists() and not planted:
        return "already exists"
    return None


def _parse_exports(spec: str | None) -> list[str]:
    if not spec:
        return []
    raw = [part.strip() for part in spec.split(",") if part.strip()]
    kept, reserved = forwardable_exports(raw)
    if reserved:
        console.warn(f"not exporting {', '.join(reserved)}")
    return kept


def run(
    names: list[str],
    output: str | Path | None = None,
    payload: str = DEFAULT_PAYLOAD,
    compilers: list[Compiler] | None = None,
    arch: str = "x64",
    exports: str | None = None,
    keep_going: bool = False,
    unsafe: bool = False,
) -> int:
    if compilers is None:
        compilers = detect_compilers()
    if not compilers:
        console.fail("no compiler found")
        return 1
    if not names:
        console.fail("missing DLL name")
        return 1

    try:
        dlls = [_dll_name(n) for n in names]
    except ValueError as exc:
        console.fail(str(exc))
        return 1

    out_dir = _dest_dir(output, unsafe=unsafe)
    if out_dir is None:
        console.warn("no ranked writable PATH dir outside the user profile")
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        compiler = require_compiler(compilers, arch)
    except RuntimeError as exc:
        console.fail(str(exc))
        return 1

    export_list = _parse_exports(exports)
    console.section(str(out_dir))
    console.info(f"fake  {arch}  {compiler.kind}")

    workroot = Path(tempfile.mkdtemp(prefix="dllproxy_fake_"))
    succeeded: list[str] = []
    skipped: list[Result] = []
    failed: list[Result] = []
    lang = for_compiler(compiler)

    for name in dlls:
        reason = _skip(name, out_dir)
        if reason is not None:
            skipped.append(Result(name, reason))
            console.warn(f"{name}  skip  {reason}")
            continue
        try:
            proj = workroot / Path(name).stem
            if proj.exists():
                shutil.rmtree(proj)
            proj.mkdir(parents=True)
            src, def_path = lang.write_fake(proj, export_list)
            built = proj / "proxy.dll"
            compile_dll(compiler, src, built, def_path)
            shutil.copy2(built, out_dir / name)
            albaran_note(out_dir, "plant", name)
            console.ok(f"{name}  {console.dim(compiler.kind)}")
            succeeded.append(name)
        except Exception as exc:
            failed.append(Result(name, str(exc)))
            console.fail(f"{name}  {exc}")
            console.debug_exc()
            if not keep_going:
                console.warn("aborting  (use --keep-going)")
                break

    print_summary("fake", succeeded, skipped, failed, out_dir)
    return 0 if not failed else 2
