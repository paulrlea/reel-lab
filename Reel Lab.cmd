@echo off
setlocal
cd /d "%~dp0"
set "PATH=%~dp0.runtime\ffmpeg\bin;%LOCALAPPDATA%\Programs\Ollama;%PATH%"
if not "%~1"=="" (
    ".venv\Scripts\python.exe" -m reel_lab %*
    exit /b
)
".venv\Scripts\python.exe" -m streamlit run dashboard.py --server.address 127.0.0.1 --server.port 8501 --server.headless false --browser.gatherUsageStats false
