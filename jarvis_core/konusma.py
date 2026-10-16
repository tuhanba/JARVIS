"""Text-to-speech with a JARVIS-style voice.

Engines, in order of preference (JARVIS_TTS in .env):
  piper  local, offline Turkish neural voice (default; model downloaded once)
  edge   Microsoft online neural voice (needs internet)
Windows' built-in SAPI voices are only used if a Turkish one is installed:
an English voice reading Turkish text is worse than silence.

The "JARVIS" effect (JARVIS_SES_EFEKT=1) is signal processing on our own
output - lower, fuller tone, presence lift, a faint metallic sheen and a
short room - not an imitation of any real person's voice.

    python -m jarvis_core.konusma --indir           # download the voice model
    python -m jarvis_core.konusma "Merhaba efendim"  # speak / test
"""
import os
import sys
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np

from .ayarlar import Ayarlar

PIPER_SES = os.getenv('JARVIS_PIPER_SES', 'tr_TR-dfki-medium')
PIPER_URL = 'https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/'

_piper = None
_piper_kilit = threading.Lock()


# ------------------------------------------------------------------ voice model

def ses_dizini() -> Path:
    d = Ayarlar().veri_dizini / 'sesler'
    d.mkdir(parents=True, exist_ok=True)
    return d


def piper_hazir() -> bool:
    return (ses_dizini() / f'{PIPER_SES}.onnx').exists() and (ses_dizini() / f'{PIPER_SES}.onnx.json').exists()


def piper_indir(ilerleme=print) -> bool:
    import requests
    for ad in (f'{PIPER_SES}.onnx.json', f'{PIPER_SES}.onnx'):
        hedef = ses_dizini() / ad
        if hedef.exists():
            continue
        gecici = hedef.with_suffix(hedef.suffix + '.indiriliyor')
        try:
            with requests.get(PIPER_URL + ad, stream=True, timeout=30) as r:
                r.raise_for_status()
                toplam, inen = int(r.headers.get('Content-Length') or 0), 0
                with open(gecici, 'wb') as f:
                    for parca in r.iter_content(1 << 20):
                        f.write(parca)
                        inen += len(parca)
                        if toplam:
                            ilerleme(f'Ses modeli indiriliyor: %{100 * inen // toplam}')
            gecici.replace(hedef)
        except Exception as e:
            ilerleme(f'Ses modeli indirilemedi: {e}')
            return False
    return True


def _piper_ses():
    global _piper
    with _piper_kilit:
        if _piper is None:
            from piper import PiperVoice
            _piper = PiperVoice.load(str(ses_dizini() / f'{PIPER_SES}.onnx'))
        return _piper


# ------------------------------------------------------------------ synthesis

def piper_sentezle(metin: str):
    """Returns (samples float32 -1..1, sample_rate)."""
    from piper import SynthesisConfig
    ses = _piper_ses()
    hiz = float(os.getenv('JARVIS_SES_HIZ', '0.95'))      # <1 faster; the effect slows it back down
    parcalar = [p.audio_float_array for p in ses.synthesize(metin, syn_config=SynthesisConfig(length_scale=hiz))]
    if not parcalar:
        return np.zeros(0, dtype=np.float32), ses.config.sample_rate
    return np.concatenate(parcalar).astype(np.float32), ses.config.sample_rate


def jarvis_efekti(x: np.ndarray, sr: int) -> np.ndarray:
    if x.size == 0:
        return x
    # 1) Slightly lower, fuller voice: resample so playback is ~5% lower in pitch.
    perde = float(os.getenv('JARVIS_SES_PERDE', '0.95'))
    n = int(len(x) / perde)
    x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)

    # 2) EQ in the frequency domain: cut rumble, warm low-mids, lift presence/air.
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    kazanc = np.ones_like(f)
    kazanc *= 1 / np.sqrt(1 + (80 / np.maximum(f, 1)) ** 4)               # high-pass 80 Hz
    kazanc *= 1 + 0.25 * np.exp(-((f - 180) / 90) ** 2)                    # chest warmth
    kazanc *= 1 - 0.18 * np.exp(-((f - 500) / 200) ** 2)                    # remove boxiness
    kazanc *= 1 + 0.45 * np.exp(-((f - 3200) / 1200) ** 2)                  # clarity
    kazanc *= 1 + 0.30 * np.exp(-((f - 8000) / 2500) ** 2)                  # air
    x = np.fft.irfft(X * kazanc, n=len(x)).astype(np.float32)

    # 3) Faint metallic sheen: very short comb (flanger-like, static).
    d = int(sr * 0.0045)
    parlak = np.zeros_like(x)
    parlak[d:] = x[:-d]
    x = x + 0.22 * parlak

    # 4) Small, clean room so it sounds like it comes from the space, not a phone.
    oda = np.zeros(len(x) + int(sr * 0.12), dtype=np.float32)
    oda[:len(x)] += x
    for gecikme, g in ((0.019, .16), (0.031, .12), (0.047, .09), (0.071, .06), (0.097, .04)):
        k = int(sr * gecikme)
        oda[k:k + len(x)] += g * x
    x = oda

    # 5) Gentle compression + normalise to -1 dBFS.
    x = np.tanh(1.6 * x) / np.tanh(1.6)
    tepe = np.max(np.abs(x)) or 1.0
    return (x / tepe * 0.89).astype(np.float32)


def wav_yaz(x: np.ndarray, sr: int, yol: str) -> None:
    with wave.open(yol, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype('<i2').tobytes())


def sentezle_dosyaya(metin: str) -> str:
    """Synthesize with Piper (+ effect) into a temp WAV and return its path."""
    x, sr = piper_sentezle(metin)
    if os.getenv('JARVIS_SES_EFEKT', '1') == '1':
        x = jarvis_efekti(x, sr)
    fd, yol = tempfile.mkstemp(suffix='.wav')
    os.close(fd)
    wav_yaz(x, sr, yol)
    return yol


# ------------------------------------------------------------------ playback

def cal(yol: str, sus: threading.Event) -> None:
    """Play a WAV/MP3 file; return early when `sus` is set."""
    import pygame
    if not pygame.mixer.get_init():
        pygame.mixer.init()
    if yol.endswith('.wav'):
        kanal = pygame.mixer.Sound(yol).play()
        while kanal.get_busy():
            if sus.is_set():
                kanal.stop()
                break
            pygame.time.wait(30)
    else:
        pygame.mixer.music.load(yol)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            if sus.is_set():
                pygame.mixer.music.stop()
                break
            pygame.time.wait(30)
        pygame.mixer.music.unload()


if __name__ == '__main__':
    from dotenv import load_dotenv
    from .ayarlar import PROJE
    load_dotenv(PROJE / '.env')
    if '--indir' in sys.argv or not piper_hazir():
        print('Türkçe ses modeli (yaklaşık 63 MB) indiriliyor...')
        print('Tamam.' if piper_indir(lambda m: print('\r' + m, end='', flush=True)) else 'Başarısız.')
        print()
    metinler = [a for a in sys.argv[1:] if not a.startswith('--')]
    if metinler or '--indir' not in sys.argv:
        sys.path.insert(0, str(PROJE))
        import ses
        ses.konus(' '.join(metinler) or 'İyi akşamlar efendim. Tüm sistemler çevrimiçi. Size nasıl yardımcı olabilirim?')
