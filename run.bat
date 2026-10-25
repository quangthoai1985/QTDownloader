@echo off
rem Run QT Downloader from source (needs Python 3.11+ and requirements.txt)
cd /d "%~dp0"
start "" pythonw -m qtdownloader %*
