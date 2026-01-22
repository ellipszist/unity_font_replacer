@echo off
setlocal

set /p VERSION=Enter version (e.g. v1.0.6): 
if "%VERSION%"=="" (
  echo Version is required.
  exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
  echo Python not found in PATH.
  exit /b 1
)

python -c "import UnityPy,sys; print(sys.version); print(UnityPy.__file__)"

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist unity_font_replacer.spec del unity_font_replacer.spec
if exist export_fonts.spec del export_fonts.spec

python -m PyInstaller --onefile --name unity_font_replacer ^
  --clean ^
  --noconfirm ^
  --collect-all UnityPy ^
  --collect-all TypeTreeGeneratorAPI ^
  --collect-all fmod_toolkit ^
  --collect-all archspec ^
  unity_font_replacer.py

python -m PyInstaller --onefile --name export_fonts ^
  --clean ^
  --noconfirm ^
  --collect-all UnityPy ^
  --collect-all TypeTreeGeneratorAPI ^
  --collect-all fmod_toolkit ^
  --collect-all archspec ^
  export_fonts.py

if exist release rmdir /s /q release
mkdir release
copy dist\unity_font_replacer.exe release\ >nul
copy dist\export_fonts.exe release\ >nul
xcopy KR_ASSETS release\KR_ASSETS\ /E /I >nul
xcopy Il2CppDumper release\Il2CppDumper\ /E /I >nul
copy README.md release\ >nul

set ZIP_NAME=Unity_Font_Replacer_%VERSION%.zip
if exist "%ZIP_NAME%" del "%ZIP_NAME%"
powershell -NoProfile -Command "Compress-Archive -Path release\* -DestinationPath '%ZIP_NAME%'"
if errorlevel 1 (
  echo Failed to create zip.
  exit /b 1
)

echo Build complete. Output in release\ and dist\, zip: %ZIP_NAME%
endlocal
