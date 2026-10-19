@echo off
rem Build dist\TDownload\TDownload.exe (portable folder, no Python needed)
cd /d "%~dp0"
python tools\make_icons.py || goto :err
python -m PyInstaller --noconfirm --clean --windowed --name TDownload ^
  --icon assets\tdownload.ico ^
  --add-data "extension;extension" ^
  --exclude-module tkinter --exclude-module pytest --exclude-module numpy --exclude-module PIL ^
  --exclude-module scipy --exclude-module matplotlib --exclude-module pandas ^
  run_tdownload.py || goto :err
rem Software OpenGL fallback is not used by the Qt Widgets UI
del /q "dist\TDownload\_internal\PySide6\opengl32sw.dll" 2>nul
echo.
echo Done: dist\TDownload\TDownload.exe
goto :eof
:err
echo Build failed.
exit /b 1
