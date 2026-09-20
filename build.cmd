@echo off
setlocal
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
  .venv\Scripts\python.exe -m pip install -e ".[dev]"
  .venv\Scripts\python.exe -m PyInstaller --noconfirm --clean "%~dp0dllproxykit.spec"
) else (
  py -3 -m pip install -e ".[dev]"
  py -3 -m PyInstaller --noconfirm --clean "%~dp0dllproxykit.spec"
)
if exist dist\DLLProxyKit.exe (
  echo [+] Built dist\DLLProxyKit.exe
  exit /b 0
)
echo [!] dist\DLLProxyKit.exe missing
exit /b 1
