"""JARVIS desktop panel. Double-click (runs with pythonw, no console window),
or use the desktop shortcut made by kisayol_olustur.py."""
import os
import sys

PROJE = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJE)
sys.path.insert(0, PROJE)

# pythonw has no console: keep a log instead of losing errors.
if sys.stdout is None or sys.stderr is None:
    os.makedirs(os.path.join(PROJE, 'veri'), exist_ok=True)
    gunluk = open(os.path.join(PROJE, 'veri', 'panel.log'), 'a', encoding='utf-8', buffering=1)
    sys.stdout = sys.stderr = gunluk

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(PROJE, '.env'))

from jarvis_core.panel.sunucu import calistir  # noqa: E402

calistir()
