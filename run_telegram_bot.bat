@echo off
setlocal
set "PYTHON=C:\Users\Nikita\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
pushd "%~dp0"
"%PYTHON%" run_telegram_bot.py
popd
endlocal
