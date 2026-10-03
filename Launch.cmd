@echo off
setlocal
cd /d "%~dp0"
if defined PIPELINE_PYTHON (
  "%PIPELINE_PYTHON%" run.py %*
) else (
  where py >nul 2>nul
  if errorlevel 1 (
    if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
      "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" run.py %*
    ) else (
      python run.py %*
    )
  ) else (
    py -3 run.py %*
  )
)
if errorlevel 1 pause
