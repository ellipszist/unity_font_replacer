@echo off
chcp 65001 > nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
setlocal

set "VENV_DIR=venv"
set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
set "LOCAL_UNITYPY=%~dp0..\UnityPy"

if not exist "%VENV_PY%" (
  echo [build] Creating virtual environment: %VENV_DIR%
  py -3.12 -m venv "%VENV_DIR%" 2>nul
  if errorlevel 1 (
    python -m venv "%VENV_DIR%" 2>nul
  )
)

if not exist "%VENV_PY%" (
  echo Failed to create or find venv python at "%VENV_PY%".
  echo Ensure Python 3.12 or python is installed and available.
  exit /b 1
)

echo [build] Using venv python: %VENV_PY%

"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 exit /b 1
"%VENV_PY%" -m pip install pyinstaller TypeTreeGeneratorAPI Pillow fmod_toolkit archspec numpy scipy fonttools
if errorlevel 1 exit /b 1
if exist "%LOCAL_UNITYPY%\pyproject.toml" (
  echo [build] Installing local custom UnityPy: %LOCAL_UNITYPY%
  "%VENV_PY%" -m pip install --upgrade --force-reinstall "%LOCAL_UNITYPY%"
) else if exist "%LOCAL_UNITYPY%\setup.py" (
  echo [build] Installing local custom UnityPy: %LOCAL_UNITYPY%
  "%VENV_PY%" -m pip install --upgrade --force-reinstall "%LOCAL_UNITYPY%"
) else (
  echo [build] Local custom UnityPy not found. Falling back to remote repository.
  "%VENV_PY%" -m pip install --upgrade git+https://github.com/snowyegret23/UnityPy.git@4018e7600357e185f9986af536d6f105729f0950
)
if errorlevel 1 exit /b 1
"%VENV_PY%" -c "import UnityPy,sys; from UnityPy.files.BundleFile import BundleFile; from UnityPy.files.ObjectReader import ObjectReader; from UnityPy.files.SerializedFile import SerializedFile; from UnityPy.helpers import CompressionHelper; v=tuple(int(x) for x in UnityPy.__version__.split('.')[:3]); probe=type('Probe',(),{'data':b'modified'})(); print(sys.version); print(UnityPy.__version__); print(UnityPy.__file__); assert v >= (1,25,2) and ObjectReader.get_raw_data(probe)==b'modified' and callable(getattr(BundleFile,'save_to',None)) and callable(getattr(BundleFile,'_write_decompressed_block',None)) and callable(getattr(SerializedFile,'save_to',None)) and callable(getattr(SerializedFile,'get_spill_store',None)) and callable(getattr(CompressionHelper,'chunk_based_compress_iter_to_file',None)) and callable(getattr(CompressionHelper,'create_lzma_decompressor',None)), 'Required custom UnityPy low-memory APIs are missing'"
if errorlevel 1 (
  echo [build] ERROR: Installed UnityPy is not the required low-memory 1.25.2+ build
  exit /b 1
)

if exist tests (
  "%VENV_PY%" -m unittest discover -s tests -v
  if errorlevel 1 exit /b 1
)

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist unity_font_replacer_ko.spec del unity_font_replacer_ko.spec
if exist export_fonts_ko.spec del export_fonts_ko.spec
if exist unity_font_replacer_en.spec del unity_font_replacer_en.spec
if exist export_fonts_en.spec del export_fonts_en.spec
if exist make_sdf.spec del make_sdf.spec

"%VENV_PY%" -m PyInstaller --onefile --name unity_font_replacer_ko ^
  --clean ^
  --noconfirm ^
  --collect-all UnityPy ^
  --collect-all TypeTreeGeneratorAPI ^
  --collect-all fmod_toolkit ^
  --collect-all archspec ^
  --collect-all fontTools ^
  unity_font_replacer_ko.py
if errorlevel 1 exit /b 1

"%VENV_PY%" -m PyInstaller --onefile --name export_fonts_ko ^
  --clean ^
  --noconfirm ^
  --collect-all UnityPy ^
  --collect-all TypeTreeGeneratorAPI ^
  --collect-all fmod_toolkit ^
  --collect-all archspec ^
  export_fonts_ko.py
if errorlevel 1 exit /b 1

"%VENV_PY%" -m PyInstaller --onefile --name unity_font_replacer_en ^
  --clean ^
  --noconfirm ^
  --collect-all UnityPy ^
  --collect-all TypeTreeGeneratorAPI ^
  --collect-all fmod_toolkit ^
  --collect-all archspec ^
  --collect-all fontTools ^
  unity_font_replacer_en.py
if errorlevel 1 exit /b 1

"%VENV_PY%" -m PyInstaller --onefile --name export_fonts_en ^
  --clean ^
  --noconfirm ^
  --collect-all UnityPy ^
  --collect-all TypeTreeGeneratorAPI ^
  --collect-all fmod_toolkit ^
  --collect-all archspec ^
  export_fonts_en.py
if errorlevel 1 exit /b 1

"%VENV_PY%" -m PyInstaller --onefile --name make_sdf ^
  --clean ^
  --noconfirm ^
  --collect-all numpy ^
  --collect-all scipy ^
  --collect-all fontTools ^
  make_sdf.py
if errorlevel 1 exit /b 1

if exist release rmdir /s /q release
if exist release_en rmdir /s /q release_en
if exist release_make_sdf rmdir /s /q release_make_sdf
mkdir release
mkdir release_en
mkdir release_make_sdf
copy dist\unity_font_replacer_ko.exe release\ >nul
copy dist\export_fonts_ko.exe release\ >nul
xcopy KR_ASSETS release\KR_ASSETS\ /E /I >nul
xcopy Il2CppDumper release\Il2CppDumper\ /E /I >nul
copy README.md release\ >nul
if exist CharList_3911.txt copy CharList_3911.txt release\ >nul
copy dist\unity_font_replacer_en.exe release_en\ >nul
copy dist\export_fonts_en.exe release_en\ >nul
xcopy KR_ASSETS release_en\KR_ASSETS\ /E /I >nul
xcopy Il2CppDumper release_en\Il2CppDumper\ /E /I >nul
copy README_EN.md release_en\ >nul
if exist CharList_3911.txt copy CharList_3911.txt release_en\ >nul
copy dist\make_sdf.exe release_make_sdf\ >nul
copy README.md release_make_sdf\ >nul
copy README_EN.md release_make_sdf\ >nul
if exist CharList_3911.txt copy CharList_3911.txt release_make_sdf\ >nul

echo Build complete. Output in release\, release_en\, release_make_sdf\, and dist\
pause
endlocal
