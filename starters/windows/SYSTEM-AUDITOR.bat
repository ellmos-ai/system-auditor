@echo off
chcp 65001 >nul
setlocal
set "PYTHONIOENCODING=utf-8"
REM Optional: SA_LANG=de|en, TASKPLAN_WORKDIR, TASKPLAN_TRUSTED_AUTOMATION.
REM No account, machine, model or permissions are selected by this file.
python -c "import taskplan" >nul 2>&1
if errorlevel 1 (
  echo [FEHLER] TASKPLAN fehlt. Installation: python -m pip install taskplan
  exit /b 2
)
if not defined SA_LANG set "SA_LANG=de"
set "SA_PROMPT=%~dp0..\..\prompts\AUDITOR.%SA_LANG%.md"
if not exist "%SA_PROMPT%" (
  echo [FEHLER] Rollen-Prompt fehlt. SA_LANG muss de oder en sein.
  exit /b 2
)
python -m taskplan launch --label system-auditor --prompt-file "%SA_PROMPT%" --request "Start as SYSTEM-AUDITOR. Complete preflight steps (a0) and (a) from the role prompt, and confirm the audit scope with the user before the sweep." --interactive %*
exit /b %ERRORLEVEL%
