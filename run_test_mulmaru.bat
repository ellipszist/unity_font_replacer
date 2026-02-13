@echo off
setlocal
cd /d "%~dp0"
py -3.12 -m pytest -q tests\test_replace_mulmaru.py -s -p no:cacheprovider
set EXIT_CODE=%ERRORLEVEL%
endlocal & exit /b %EXIT_CODE%
