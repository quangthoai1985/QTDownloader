@echo off
rem Build TDownload.exe (portable folder, no Python needed)
rem Usage: build.bat [distdir]   (default: dist)  ->  <distdir>\TDownload\TDownload.exe
rem Version comes from tdownload\__init__.py (__version__)
setlocal
cd /d "%~dp0"
set "DIST=%~1"
if "%DIST%"=="" set "DIST=dist"
python tools\make_icons.py || goto :err
python tools\make_version_file.py || goto :err
python -m PyInstaller --noconfirm --clean --windowed --name TDownload ^
  --distpath "%DIST%" --workpath build ^
  --icon assets\tdownload.ico ^
  --version-file assets\version_info.txt ^
  --add-data "extension;extension" ^
  --exclude-module tkinter --exclude-module pytest --exclude-module numpy --exclude-module PIL ^
  --exclude-module scipy --exclude-module matplotlib --exclude-module pandas ^
  --exclude-module click --exclude-module rich --exclude-module pygments --exclude-module markdown_it ^
  --exclude-module mdurl --exclude-module colorama --exclude-module zstandard ^
  --exclude-module win32evtlogutil --exclude-module win32evtlog --exclude-module win32con ^
  --exclude-module pywintypes --exclude-module win32api ^
  run_tdownload.py || goto :err
rem Software OpenGL fallback is not used by the Qt Widgets UI
del /q "%DIST%\TDownload\_internal\PySide6\opengl32sw.dll" 2>nul
echo.
echo Done: %DIST%\TDownload\TDownload.exe
goto :eof
:err
echo Build failed.
exit /b 1
