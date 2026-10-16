"""Text-to-speech with a JARVIS-style voice.

Engines, in order of preference (JARVIS_TTS in .env):
  piper  local, offline Turkish neural voice (default; model downloaded once)
  edge   Microsoft online neural voice (needs internet)
Windows' built-in SAPI voices are only used if a Turkish one is installed:
an English voice reading Turkish text is worse than silence.

The "JARVIS" character (JARVIS_SES_KARAKTER=kibar|hafif|jarvis|belirgin) is signal
processing on our own output - deeper, more measured, presence lift, a subtle
digital double, a faint metallic sheen, a short room and pauses between
sentences. It is not an imitation of any real person's voice.

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

# Voice character presets. Final speaking time = hiz / perde (both < 1 lower the
# pitch or speed things up), so "jarvis" ends up ~8% slower and ~9% deeper.
# netlik/hava: presence (3 kHz) and air (7.5 kHz) lift. ritim: Piper's rhythm/intonation
# randomness - lower is steadier and more self-assured.
_ORTAK = dict(netlik=0.45, hava=0.30, ritim=0.8, tini=0.667)
KARAKTERLER = {
    # Near-natural, warm and polite, steady and confident; the effect is only a touch.
    # Refined gentleman: brisk but unhurried, a little deeper, warm and smooth, almost no metal.
    'kibar':    dict(_ORTAK, perde=0.92, hiz=0.80, sicaklik=0.45, parlaklik=0.04, koro=0.00, oda=0.55, sus=0.18,
                     netlik=0.32, hava=0.18, ritim=0.50, tini=0.58),
    'hafif':    dict(_ORTAK, perde=0.95, hiz=0.97, sicaklik=0.25, parlaklik=0.12, koro=0.00, oda=0.8, sus=0.22),
    'jarvis':   dict(_ORTAK, perde=0.91, hiz=0.98, sicaklik=0.35, parlaklik=0.18, koro=0.16, oda=1.0, sus=0.32),
    'belirgin': dict(_ORTAK, perde=0.88, hiz=1.00, sicaklik=0.45, parlaklik=0.28, koro=0.28, oda=1.3, sus=0.38),
}


def karakter() -> dict:
    k = dict(KARAKTERLER.get(os.getenv('JARVIS_SES_KARAKTER', 'kibar'), KARAKTERLER['kibar']))
    # individual .env overrides still win
    for anahtar, ortam in (('perde', 'JARVIS_SES_PERDE'), ('hiz', 'JARVIS_SES_HIZ')):
        if os.getenv(ortam):
            k[anahtar] = float(os.getenv(ortam))
    return k


def piper_sentezle(metin: str, hiz: float = 1.0, ritim: float = 0.8, tini: float = 0.667):
    """Returns (samples float32 -1..1, sample_rate)."""
    from piper import SynthesisConfig
    ses = _piper_ses()
    ayar = SynthesisConfig(length_scale=hiz, noise_w_scale=ritim, noise_scale=tini)
    parcalar = [p.audio_float_array for p in ses.synthesize(metin, syn_config=ayar)]
    if not parcalar:
        return np.zeros(0, dtype=np.float32), ses.config.sample_rate
    return np.concatenate(parcalar).astype(np.float32), ses.config.sample_rate


def _kaydir(x: np.ndarray, ornek: int) -> np.ndarray:
    y = np.zeros_like(x)
    if ornek < len(x):
        y[ornek:] = x[:len(x) - ornek]
    return y


def _yeniden_ornekle(x: np.ndarray, oran: float) -> np.ndarray:
    n = max(1, int(len(x) / oran))
    return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x).astype(np.float32)


def jarvis_efekti(x: np.ndarray, sr: int, k: dict = None) -> np.ndarray:
    """Calm, deeper, clean 'system' voice. Pure signal processing on our own TTS output."""
    if x.size == 0:
        return x
    k = k or karakter()
    # 1) Deeper and more measured: resample (lowers pitch and slows slightly).
    x = _yeniden_ornekle(x, k['perde'])

    # 2) EQ: cut rumble, chest warmth, less boxiness, clear presence and some air.
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / sr)
    kazanc = 1 / np.sqrt(1 + (75 / np.maximum(f, 1)) ** 4)
    kazanc *= 1 + k['sicaklik'] * np.exp(-((f - 160) / 80) ** 2)
    kazanc *= 1 - 0.20 * np.exp(-((f - 480) / 180) ** 2)
    kazanc *= 1 + k['netlik'] * np.exp(-((f - 3000) / 1100) ** 2)
    kazanc *= 1 + k['hava'] * np.exp(-((f - 7500) / 2300) ** 2)
    x = np.fft.irfft(X * kazanc, n=len(x)).astype(np.float32)

    # 3) Digital layer: a slightly detuned, delayed double (subtle chorus) ...
    if k['koro']:
        cift = _yeniden_ornekle(x, 1.006)[:len(x)]
        cift = np.pad(cift, (0, len(x) - len(cift)))
        x = x + k['koro'] * _kaydir(cift, int(sr * 0.011))
    # ... and a faint metallic comb.
    x = x + k['parlaklik'] * _kaydir(x, int(sr * 0.0045))

    # 4) Short clean room.
    kuyruk = int(sr * 0.14)
    oda = np.zeros(len(x) + kuyruk, dtype=np.float32)
    oda[:len(x)] += x
    for gecikme, g in ((0.017, .15), (0.029, .12), (0.043, .09), (0.067, .06), (0.093, .045), (0.121, .03)):
        d = int(sr * gecikme)
        oda[d:d + len(x)] += g * k['oda'] * x
    x = oda

    # 5) Gentle compression, -1 dBFS, then a measured pause after the sentence.
    x = np.tanh(1.7 * x) / np.tanh(1.7)
    x = x / (np.max(np.abs(x)) or 1.0) * 0.89
    return np.concatenate([x, np.zeros(int(sr * k['sus']), dtype=np.float32)]).astype(np.float32)


def wav_yaz(x: np.ndarray, sr: int, yol: str) -> None:
    with wave.open(yol, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype('<i2').tobytes())


def sentezle_dosyaya(metin: str) -> str:
    """Synthesize with Piper (+ effect) into a temp WAV and return its path."""
    k = karakter()
    efekt = os.getenv('JARVIS_SES_EFEKT', '1') == '1'
    x, sr = piper_sentezle(metin, k['hiz'], k['ritim'], k['tini']) if efekt else piper_sentezle(metin)
    if efekt:
        x = jarvis_efekti(x, sr, k)
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
