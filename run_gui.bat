@echo off
setlocal
set "APP_DIR=%~dp0"
set "CODEX_PY=C:\Users\Nikita\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"

if exist "%CODEX_PY%" (
  start "" "%CODEX_PY%" "%APP_DIR%windows_marker.pyw"
) else (
  start "" pythonw "%APP_DIR%windows_marker.pyw"
)
