@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Ollama"
ollama list >nul 2>nul || (start "" /min ollama serve & timeout /t 3 >nul)
python -m jarvis_core.saglik
pause
