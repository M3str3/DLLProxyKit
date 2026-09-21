from __future__ import annotations

from pathlib import Path
from typing import Iterable, NamedTuple

DEFAULT_PAYLOAD: str = (
    "net session >nul 2>&1 && start \"DLLProxyKit ADMIN CONSOLE\" cmd /k whoami\n"
    "powershell -NoProfile -ExecutionPolicy Bypass -Command "
    "\"$log='C:\\Windows\\Temp\\DLLProxyKit.log'; "
    "$ps=Get-CimInstance Win32_Process -Filter ('ProcessId='+$PID); "
    "$cmd=Get-CimInstance Win32_Process -Filter ('ProcessId='+$ps.ParentProcessId); "
    "$h=Get-CimInstance Win32_Process -Filter ('ProcessId='+$cmd.ParentProcessId); "
    "if(-not $h){$h=$cmd}; "
    "$g=whoami /groups | Out-String; "
    "$il='unknown'; "
    "if($g -match 'S-1-16-16384'){$il='system'} "
    "elseif($g -match 'S-1-16-12288'){$il='high'} "
    "elseif($g -match 'S-1-16-8192'){$il='medium'} "
    "elseif($g -match 'S-1-16-4096'){$il='low'}; "
    "$elev=if($il -in @('high','system')){'yes'}else{'no'}; "
    "$note='standard user'; "
    "if($g -match 'S-1-5-32-544'){ "
    "if($elev -eq 'yes'){$note='Administrators, elevated'} "
    "else{$note='Administrators, UAC-filtered (not elevated)'} }; "
    "$ts=Get-Date -Format 'yyyy-MM-dd HH:mm:ss'; "
    "Add-Content -LiteralPath $log -Value @("
    "'', "
    "('-------- {0} --------' -f $ts), "
    "('  user        {0}\\{1}' -f $env:USERDOMAIN, $env:USERNAME), "
    "('  elevated    {0}' -f $elev), "
    "('  integrity   {0}' -f $il), "
    "('  note        {0}' -f $note), "
    "('  process     {0}  ({1})' -f $h.Name, $h.ProcessId), "
    "('  command     {0}' -f $h.CommandLine)"
    ")\""
)
DEFAULT_SKIP_DLL: tuple[str, ...] = ("api-ms-win-", "ext-ms-win-")
RESERVED_EXPORTS = frozenset({"dllmain", "dllentrypoint", "_dllmaincrtstartup"})
SKIP_SELF = "dllproxykit.exe"
PAYLOAD_NAME = "payload.txt"
PAYLOAD_FALLBACK = Path(r"C:\Windows\Temp") / PAYLOAD_NAME
ALBARAN_NAME = "dllproxykit.changelog"


def orig_sidecar(path: Path) -> Path:
    return path.with_name(f"{path.stem}.original{path.suffix}")


def is_orig_sidecar(path: Path) -> bool:
    return path.stem.lower().endswith(".original")


def live_from_orig(orig: Path) -> Path:
    stem = orig.stem
    if stem.lower().endswith(".original"):
        stem = stem[: -len(".original")]
    return orig.with_name(stem + orig.suffix)


def ensure_fallback_payload(text: str) -> None:
    if PAYLOAD_FALLBACK.exists():
        return
    PAYLOAD_FALLBACK.parent.mkdir(parents=True, exist_ok=True)
    body = text if text.endswith("\n") else text + "\n"
    PAYLOAD_FALLBACK.write_text(body, encoding="utf-8")


def _same_dir(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return False


def forward_target(src: Path, out_dir: Path, proxy_name: str) -> str:
    if _same_dir(src.parent, out_dir):
        return orig_sidecar(Path(proxy_name)).name
    try:
        return str(src.resolve())
    except OSError:
        return str(src)


def albaran_path(folder: Path) -> Path:
    return folder / ALBARAN_NAME


def albaran_note(folder: Path, action: str, name: str, extra: str = "") -> None:
    line = f"{action}\t{name}"
    if extra:
        line += f"\t{extra}"
    path = albaran_path(folder)
    if path.exists():
        prev = path.read_text(encoding="utf-8")
        if line in prev.splitlines():
            return
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")


def albaran_read(folder: Path) -> list[tuple[str, str, str]]:
    path = albaran_path(folder)
    if not path.is_file():
        return []
    out: list[tuple[str, str, str]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        extra = parts[2] if len(parts) > 2 else ""
        out.append((parts[0], parts[1], extra))
    return out


def albaran_write(folder: Path, entries: list[tuple[str, str, str]]) -> None:
    path = albaran_path(folder)
    if not entries:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return
    body = "".join(
        f"{action}\t{name}\t{extra}\n" if extra else f"{action}\t{name}\n"
        for action, name, extra in entries
    )
    path.write_text(body, encoding="utf-8", newline="\n")


def note_proxy(src: Path, out_dir: Path, proxy_name: str) -> None:
    sidecar = orig_sidecar(Path(proxy_name)).name
    if _same_dir(src.parent, out_dir):
        (out_dir / sidecar).write_bytes(src.read_bytes())
        albaran_note(out_dir, "orig", proxy_name, sidecar)
        return
    try:
        extra = str(src.resolve())
    except OSError:
        extra = str(src)
    albaran_note(out_dir, "plant", proxy_name, extra)


def skip_proxy_target(
    path: Path,
    skips: Iterable[str],
    out_dir: Path | None = None,
) -> str | None:
    lower = path.name.lower()
    if is_orig_sidecar(path):
        return "already a .original sidecar"
    if lower == SKIP_SELF:
        return SKIP_SELF
    if lower == ALBARAN_NAME.lower():
        return ALBARAN_NAME
    if orig_sidecar(path).exists():
        return "already proxied"
    if out_dir is not None and not _same_dir(path.parent, Path(out_dir)):
        dest = Path(out_dir) / path.name
        planted = any(
            action == "plant" and name.lower() == path.name.lower()
            for action, name, _extra in albaran_read(Path(out_dir))
        )
        if not planted and (dest.exists() or orig_sidecar(dest).exists()):
            return "already in output"
    for needle in skips:
        if needle and needle in lower:
            return f"matches skip pattern ({needle})"
    return None


class Result(NamedTuple):
    name: str
    reason: str


def escape_c_string(value: str) -> str:
    out: list[str] = []
    for ch in value:
        code = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif 0x20 <= code < 0x7F:
            out.append(ch)
        else:
            out.append(f"\\x{code:02x}")
    return "".join(out)


def forwardable_exports(exports: Iterable[str]) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    reserved: list[str] = []
    seen: set[str] = set()
    for name in exports:
        key = name.lower()
        if key in RESERVED_EXPORTS:
            reserved.append(name)
            continue
        if key in seen:
            continue
        seen.add(key)
        kept.append(name)
    return kept, reserved


def resolve_io(input_path: Path, output: str | None, ext: str):
    if input_path.is_file():
        if input_path.suffix.lower() != ext:
            raise ValueError(f"Input file must be a {ext}: {input_path}")
        files = [input_path]
        default_dir = input_path.parent
    elif input_path.is_dir():
        files = []
        try:
            items = list(input_path.iterdir())
        except OSError:
            items = []
        for item in items:
            try:
                if item.is_file() and item.suffix.lower() == ext:
                    files.append(item)
            except OSError:
                continue
        files.sort()
        default_dir = input_path
    else:
        raise FileNotFoundError(f"Input does not exist: {input_path}")

    if not output:
        return files, default_dir, None

    dest = Path(output)
    if dest.exists() and dest.is_dir():
        return files, dest.resolve(), None
    if dest.suffix.lower() == ext:
        if len(files) != 1:
            raise ValueError("Output file is only valid when processing a single input file")
        dest = dest.resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        return files, dest.parent, dest.name
    return files, dest.resolve(), None


def print_summary(
    kind: str,
    ok_list: list[str],
    skipped: list[Result],
    failed: list[Result],
    out_dir: Path,
) -> None:
    from ..ui import console

    if not skipped:
        return
    if console.is_verbose():
        for item in skipped:
            console.warn(f"{item.name}  skip  {console.dim(item.reason)}")
        return
    console.info(f"{len(skipped)} skipped  (-v)")
