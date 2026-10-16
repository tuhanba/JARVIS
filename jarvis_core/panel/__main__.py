"""python -m jarvis_core.panel [--pencere-yok] [--port N]"""
import sys

from dotenv import load_dotenv

from ..ayarlar import PROJE
from .sunucu import calistir

load_dotenv(PROJE / '.env')
port = int(sys.argv[sys.argv.index('--port') + 1]) if '--port' in sys.argv else 0
calistir(pencere='--pencere-yok' not in sys.argv, port=port)
