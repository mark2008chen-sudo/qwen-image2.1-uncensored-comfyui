@echo off
REM ============================================================
REM Qwen-Image-2.1 Uncensored - weights downloader (one click)
REM
REM Usage:
REM   1) double click this file, then paste your ComfyUI models dir
REM   2) or drag the models folder onto this .bat
REM   3) or run from cmd:  download_models.bat "D:\ComfyUI\models"
REM
REM Uses hf-mirror.com so it works from mainland China.
REM ============================================================
setlocal
cd /d "%~dp0"

set "MODELS=%~1"
if not "%MODELS%"=="" goto run

echo.
echo ============================================================
echo  Qwen-Image-2.1 Uncensored - weights downloader
echo ============================================================
echo.
echo Paste your ComfyUI models directory, then press Enter.
echo Example: D:\ComfyUI\models
echo.
set /p MODELS=
if "%MODELS%"=="" goto abort

:run
echo.
echo Target directory: %MODELS%
echo.

set "PY=python"
if exist "%~dp0..\..\..\python_embeded\python.exe" set "PY=%~dp0..\..\..\python_embeded\python.exe"
if exist "%~dp0..\..\python_embeded\python.exe"     set "PY=%~dp0..\..\python_embeded\python.exe"
if exist "%~dp0..\python_embeded\python.exe"        set "PY=%~dp0..\python_embeded\python.exe"
if exist "D:\Software\WorkBuddy\comfyui\ComfyUI_windows_portable\python_embeded\python.exe" set "PY=D:\Software\WorkBuddy\comfyui\ComfyUI_windows_portable\python_embeded\python.exe"

echo Using python: %PY%
echo.
"%PY%" "%~dp0download_models.py" --dir "%MODELS%" --mirror
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" echo All files downloaded.
if not "%RC%"=="0" echo Finished with errors, check the output above.
echo.
echo For the 16 GB bf16 text encoder add:  --with-bf16
echo.
pause
exit /b %RC%

:abort
echo No directory given, aborted.
pause
exit /b 1
