"""Text-to-speech providers and playback."""
import asyncio
import os
import tempfile
import threading
import wave
from pathlib import Path

import numpy as np

PIPER_SES = 'tr_TR-dfki-medium'


def sesler_dizini() -> Path:
    from ..ayarlar import Ayarlar
    return Ayarlar().veri_dizini / 'sesler'


class PiperTTS:
    """Local neural Turkish voice (Piper, tr_TR-dfki-medium by default). The voice files
    are downloaded once by `python -m jarvis_core.audio.kur`."""
    yerel, turkce = True, True

    def __init__(self, model_yolu: Path = None) -> None:
        self.model_yolu = Path(model_yolu or os.getenv('JARVIS_PIPER_SES') or sesler_dizini() / f'{PIPER_SES}.onnx')
        self.ad = f'Piper {self.model_yolu.stem} (yerel)'
        self._ses = None
        self._kilit = threading.Lock()

    def hazir_mi(self) -> bool:
        if not (self.model_yolu.is_file() and self.model_yolu.with_suffix('.onnx.json').is_file()):
            return False
        import importlib.util
        return importlib.util.find_spec('piper') is not None

    def sentezle(self, metin: str):
        from piper import PiperVoice
        with self._kilit:
            if self._ses is None:
                self._ses = PiperVoice.load(str(self.model_yolu))
            parcalar = [p.audio_int16_array for p in self._ses.synthesize(metin)]
            hz = self._ses.config.sample_rate
        return (np.concatenate(parcalar) if parcalar else np.zeros(0, np.int16)), hz


class SapiTTS:
    """Windows SAPI / espeak through pyttsx3. `turkce` is True only if a Turkish voice is installed
    (Windows: Ayarlar > Saat ve dil > Konuşma > Türkçe ses paketi)."""
    yerel = True

    def __init__(self) -> None:
        import pyttsx3
        self._motor = pyttsx3.init()
        self.ses_kimligi = None
        for v in self._motor.getProperty('voices'):
            kimlik = f'{v.id} {v.name} {getattr(v, "languages", "")}'.lower()
            if 'turk' in kimlik or 'tr-tr' in kimlik or 'tr_tr' in kimlik or 'tolga' in kimlik:
                self.ses_kimligi = v.id
                self._motor.setProperty('voice', v.id)
                break
        self.turkce = self.ses_kimligi is not None
        self.ad = 'Windows sesi (yerel)' if self.turkce else 'Türkçe olmayan sistem sesi'

    def konus(self, metin: str, dur: threading.Event = None) -> None:
        self._motor.say(metin)
        self._motor.runAndWait()

    def durdur(self) -> None:
        try:
            self._motor.stop()
        except Exception:
            pass


class EdgeTTS:
    """Online Microsoft voice: the text is sent to Microsoft. Only with JARVIS_SES_CEVRIMICI=1."""
    yerel, turkce = False, True

    def __init__(self, ses: str = None) -> None:
        self.ses = ses or os.getenv('JARVIS_SES', 'tr-TR-AhmetNeural')
        self.ad = f'Edge {self.ses} (çevrimiçi)'

    def mp3(self, metin: str) -> str:
        import edge_tts
        fd, yol = tempfile.mkstemp(suffix='.mp3')
        os.close(fd)
        asyncio.run(edge_tts.Communicate(metin, self.ses).save(yol))
        return yol


def wav_yaz(yol, ses: np.ndarray, hz: int) -> None:
    with wave.open(str(yol), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(hz)
        w.writeframes(np.asarray(ses, np.int16).tobytes())


def dosya_cal(yol: str, dur: threading.Event) -> None:
    """Play a wav/mp3 file; stop as soon as `dur` is set (barge-in, stop button)."""
    import pygame
    if not pygame.mixer.get_init():
        pygame.mixer.init()
    pygame.mixer.music.load(yol)
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        if dur.is_set():
            pygame.mixer.music.stop()
            break
        pygame.time.wait(30)
    pygame.mixer.music.unload()
