"""Download the local voice models.

    python -m jarvis_core.audio.kur              # Piper Turkish voice + whisper 'small'
    python -m jarvis_core.audio.kur --stt base   # smaller/faster recognition model

Shows what is downloaded, how big it is and where it goes. Nothing is
installed silently; re-running skips files already present."""
import argparse
import sys
from pathlib import Path

import requests

PIPER_TABAN = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/'
WHISPER_BOYUT_MB = {'tiny': 75, 'base': 145, 'small': 484, 'medium': 1530, 'large-v3': 3100}


def indir(url: str, hedef: Path) -> None:
    if hedef.exists() and hedef.stat().st_size > 0:
        print(f'  zaten var: {hedef}')
        return
    hedef.parent.mkdir(parents=True, exist_ok=True)
    gecici = hedef.with_name(hedef.name + '.part')
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        toplam = int(r.headers.get('Content-Length') or 0)
        print(f'  indiriliyor: {hedef.name} ({toplam / 2**20:.1f} MB) -> {hedef.parent}')
        alinan = 0
        with open(gecici, 'wb') as f:
            for parca in r.iter_content(1 << 20):
                f.write(parca)
                alinan += len(parca)
    if toplam and alinan != toplam:
        gecici.unlink()
        raise IOError(f'{hedef.name} eksik indi ({alinan}/{toplam} bayt)')
    gecici.replace(hedef)


def main(argv=None) -> int:
    from dotenv import load_dotenv
    from ..ayarlar import PROJE
    load_dotenv(PROJE / '.env')
    from .tts import PIPER_SES, sesler_dizini
    ap = argparse.ArgumentParser()
    ap.add_argument('--stt', default=None, help='whisper modeli: ' + ', '.join(WHISPER_BOYUT_MB))
    ap.add_argument('--yalniz-tts', action='store_true')
    args = ap.parse_args(argv)
    print('Yerel Türkçe ses (Piper tr_TR-dfki-medium, ~63 MB):')
    for uzanti in ('.onnx', '.onnx.json'):
        indir(PIPER_TABAN + PIPER_SES + uzanti, sesler_dizini() / f'{PIPER_SES}{uzanti}')
    if not args.yalniz_tts:
        import os
        model = args.stt or os.getenv('JARVIS_STT_MODEL', 'small')
        print(f'Yerel ses tanıma (faster-whisper {model}, ~{WHISPER_BOYUT_MB.get(model, "?")} MB, '
              'Hugging Face önbelleğine):')
        try:
            from faster_whisper import download_model
        except ImportError:
            print('  faster-whisper kurulu değil: python -m pip install faster-whisper')
            return 1
        print(f'  hazır: {download_model(model)}')
    from .secim import durum
    d = durum()
    print(f"\nSes tanıma: {d['stt'] or 'YOK'}   Ses çıkışı: {d['tts'] or 'YOK'}")
    for u in d['uyarilar']:
        print(f'  - {u}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
