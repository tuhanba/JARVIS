"""Tool catalogue. Importing this package registers every built-in tool."""
from .temel import KAYIT, Arac, Baglam, Iptal, Sonuc, arac
from . import dosyalar, uygulamalar, bilgi, program, hafiza_araclari, ekran, belgeler, indirme, tarayici, arayuz_otomasyonu

__all__ = ['KAYIT', 'Arac', 'Baglam', 'Iptal', 'Sonuc', 'arac',
           'dosyalar', 'uygulamalar', 'bilgi', 'program', 'hafiza_araclari', 'ekran', 'belgeler', 'indirme', 'tarayici', 'arayuz_otomasyonu']
