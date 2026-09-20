<div align="center">

<img width="736" height="304" alt="banner" src="banner.jpg" />

# DLLProxyKit

**The name is a lie.** It started as DLL proxies. Now it hijacks almost anything on PATH.

[![C](https://img.shields.io/badge/C-MSVC%20%7C%20MinGW%20%7C%20tcc-blue)](#)
[![Platform](https://img.shields.io/badge/platform-Windows-blue)](#)

</div>

Windows searches PATH. If you can write to a folder that comes first, you get to run first. That's the whole trick.

This tool just builds the stand-in: DLL, EXE, `.bat`, `.cmd`, `.ps1`, `.py`, `.pl`. The original is renamed to `<name>.original.<ext>`. On run, the proxy fires `payload.txt` and then calls the real file so nothing looks broken.

Payload lives in `C:\Windows\Temp\payload.txt` (not overwritten if it already exists). Drop one next to the proxy if you want a local override. Edit that file whenever — no rebuild.

<div align="center">
<img width="600" height="607" alt="image" src="https://github.com/user-attachments/assets/8a2f5b12-f882-42b3-b6ac-901fdb2cf0b1" />
</div>

## Usage

Build a one-file exe:

```cmd
build.cmd
```

Spray writable PATH dirs (outside the user profile):

```cmd
dist\DLLProxyKit.exe --auto
```

Undo that:

```cmd
dist\DLLProxyKit.exe --auto --revert
```

Or point it at one folder / file:

```cmd
python -m dllproxykit tests\dlls-test --keep-going
```

```text
vfcompat.dll              ← proxy
vfcompat.original.dll     ← original
appverifUI.dll            ← proxy
appverifUI.original.dll   ← original
```

Default payload is in `src/dllproxykit/core/common.py`. `-i dll,exe,ps1` if you only want some kinds.

## Fine print

DLL exports are forwarded with LoadLibrary + GetProcAddress (up to ten args, named exports only). `api-ms-win-*` / `ext-ms-win-*` are skipped. TCC is bundled; rustc is a fallback.

**Authorised security testing and CTFs only.**
