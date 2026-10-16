@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1/3] Python paketleri kuruluyor...
python -m pip install --upgrade -r requirements.txt
if errorlevel 1 (
  echo Python paketleri kurulamadi. Python 3.12 kurulu ve PATH'e ekli mi?
  pause
  exit /b 1
)
if not exist .env copy .env.example .env >nul

echo.
echo [2/3] Ollama (bilgisayarda calisan yapay zeka) kontrol ediliyor...
where ollama >nul 2>nul
if errorlevel 1 (
  winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
)
set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Ollama"
where ollama >nul 2>nul
if errorlevel 1 (
  echo Ollama kurulamadi. https://ollama.com/download adresinden elle kurup bu dosyayi tekrar calistirin.
  pause
  exit /b 1
)

echo.
echo [3/3] Yapay zeka modeli indiriliyor (birkac GB, internet hizina gore 5-30 dakika)...
set MODEL=qwen3.5:9b
for /f "tokens=1,* delims==" %%a in ('findstr /b /c:"OLLAMA_MODEL=" .env') do set "MODEL=%%b"
ollama list >nul 2>nul || (start "" /min ollama serve & timeout /t 5 >nul)
ollama pull %MODEL%

echo.
echo Kurulum bitti. baslat.bat ile JARVIS'i acabilirsiniz.
pause
