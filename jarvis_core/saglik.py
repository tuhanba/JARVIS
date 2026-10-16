"""Health check / hardware report. Prints 'bilinmiyor' for anything it cannot
measure instead of guessing. Run: python -m jarvis_core.saglik"""
import platform
import shutil
import subprocess
import sys

import psutil
import requests

from .ayarlar import Ayarlar


def _komut(argv, zaman=8):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=zaman, errors='replace')
        return p.stdout.strip() if p.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def _duzelt(ad: str) -> str:
    """PortAudio on Windows hands back UTF-8 names decoded as cp1252 ("EÅŸleÅŸtirici")."""
    for kodlama in ('cp1252', 'latin-1'):
        try:
            return ad.encode(kodlama).decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            continue
    return ad


def gpu_bilgisi() -> list:
    nv = _komut(['nvidia-smi', '--query-gpu=name,memory.total,memory.used', '--format=csv,noheader'])
    if nv:
        return [f'{s.strip()} (NVIDIA)' for s in nv.splitlines()]
    if sys.platform == 'win32':
        ps = _komut(['powershell', '-NoProfile', '-Command',
                     'Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }'])
        if ps:
            return [f'{s.strip()} (VRAM ölçülemedi)' for s in ps.splitlines() if s.strip()]
    return []


def rapor() -> dict:
    a = Ayarlar()
    r = {}
    if sys.platform == 'win32':
        surum, yapi, *_ = platform.win32_ver()
        r['isletim'] = f'Windows {surum} (yapı {yapi}) {platform.machine()}'
    else:
        r['isletim'] = f'{platform.system()} {platform.release()} {platform.machine()}'
    r['python'] = platform.python_version()
    r['islemci'] = f'{platform.processor() or "bilinmiyor"}, {psutil.cpu_count(logical=False)} çekirdek / ' \
                   f'{psutil.cpu_count()} iş parçacığı'
    r['ram'] = f'{psutil.virtual_memory().total / 2**30:.1f} GB (boş {psutil.virtual_memory().available / 2**30:.1f} GB)'
    r['gpu'] = gpu_bilgisi() or ['bilinmiyor / tespit edilemedi']
    disk = shutil.disk_usage(str(a.veri_dizini.parent))
    r['disk_bos'] = f'{disk.free / 2**30:.1f} GB'
    try:
        r['ollama_surum'] = requests.get(f'{a.ollama_adres}/api/version', timeout=3).json()['version']
    except Exception:
        r['ollama_surum'] = None
    r['modeller'] = []
    if r['ollama_surum']:
        import ollama
        c = ollama.Client(host=a.ollama_adres)
        for m in c.list().models:
            try:
                yet = list(c.show(m.model).capabilities or [])
            except Exception:
                yet = []
            r['modeller'].append({'ad': m.model, 'boyut_gb': round((m.size or 0) / 2**30, 1), 'yetenekler': yet})
        r['yuklu'] = [{'ad': m.model, 'vram_gb': round((m.size_vram or 0) / 2**30, 1)} for m in c.ps().models]
    r['secili_model'] = a.model()
    try:
        import speech_recognition as sr
        r['mikrofonlar'] = [_duzelt(ad) for ad in sr.Microphone.list_microphone_names()]
    except Exception as e:
        r['mikrofonlar'] = f'bilinmiyor ({e.__class__.__name__})'
    try:
        requests.head('https://www.google.com', timeout=4)
        r['internet'] = True
    except requests.RequestException:
        r['internet'] = False
    return r


def yazdir(r: dict) -> list:
    sorunlar = []
    print('JARVIS sağlık raporu')
    print(f"  İşletim sistemi : {r['isletim']}")
    print(f"  Python          : {r['python']}")
    print(f"  İşlemci         : {r['islemci']}")
    print(f"  RAM             : {r['ram']}")
    print(f"  Ekran kartı     : {'; '.join(r['gpu'])}")
    print(f"  Boş disk        : {r['disk_bos']}")
    print(f"  İnternet        : {'var' if r['internet'] else 'YOK'}")
    if not r['ollama_surum']:
        print('  Ollama          : ÇALIŞMIYOR')
        sorunlar.append('Ollama çalışmıyor: Ollama uygulamasını açın veya "ollama serve" çalıştırın.')
    else:
        print(f"  Ollama          : {r['ollama_surum']}")
        for m in r['modeller']:
            isaret = '*' if m['ad'] == r['secili_model'] else ' '
            print(f"   {isaret} {m['ad']:<24} {m['boyut_gb']:>5} GB  {', '.join(m['yetenekler'])}")
        adlar = [m['ad'] for m in r['modeller']]
        if r['secili_model'] not in adlar:
            sorunlar.append(f"Seçili model yok: ollama pull {r['secili_model']}")
        elif 'tools' not in next(m for m in r['modeller'] if m['ad'] == r['secili_model'])['yetenekler']:
            sorunlar.append(f"{r['secili_model']} araç çağırmayı desteklemiyor.")
        for y in r.get('yuklu', []):
            print(f"     bellekte: {y['ad']} ({y['vram_gb']} GB ekran kartında)")
    mik = r['mikrofonlar']
    print(f"  Mikrofon        : {', '.join(mik[:3]) if isinstance(mik, list) and mik else mik or 'YOK'}")
    if not mik or not isinstance(mik, list):
        sorunlar.append('Mikrofon bulunamadı: yazı modu kullanılabilir (yazarak_baslat.bat).')
    print('\nSorunlar:' if sorunlar else '\nSorun bulunmadı.')
    for s in sorunlar:
        print(f'  - {s}')
    return sorunlar


if __name__ == '__main__':
    from dotenv import load_dotenv
    from .ayarlar import PROJE
    load_dotenv(PROJE / '.env')
    yazdir(rapor())
