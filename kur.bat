@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
if not exist .env copy .env.example .env
echo.
echo Kurulum bitti. Simdi .env dosyasini acip GEMINI_API_KEY satirina anahtarinizi yazin.
pause
