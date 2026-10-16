"""Speech-to-text providers."""
import os
import threading

import numpy as np

from .arayuzler import int16, yeniden_ornekle


# Domain words given to whisper as context: folder names, apps and command verbs are
# then spelled the way the command parser expects ("Chrome", not "Cehrum").
SOZLUK = ('JARVIS komutları: Belgeler, Masaüstü, İndirilenler, Resimler, Chrome, Spotify, Not Defteri, Excel, Word, '
          'listele, taşı, kopyala, aç, kapat, sil, oluştur, hatırlat.')


class WhisperSTT:
    """Local faster-whisper. Multilingual model (never a '.en' model) with language 'tr'.
    Model size via JARVIS_STT_MODEL (tiny/base/small/medium/large-v3; default small)."""
    yerel = True

    def __init__(self, model: str = None, cihaz: str = None, indirme_dizini: str = None) -> None:
        self.model_adi = model or os.getenv('JARVIS_STT_MODEL', 'small')
        if self.model_adi.endswith('.en'):
            raise ValueError(f'{self.model_adi} yalnız İngilizce; Türkçe için çok dilli model seçin (ör. small).')
        self.cihaz = cihaz or os.getenv('JARVIS_STT_CIHAZ', 'auto')
        self.indirme_dizini = indirme_dizini
        self.ad = f'whisper-{self.model_adi} (yerel)'
        self._model = None
        self._kilit = threading.Lock()

    def _yukle(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            hesap = 'int8' if self.cihaz in ('cpu', 'auto') else 'float16'
            self._model = WhisperModel(self.model_adi, device=self.cihaz, compute_type=hesap,
                                       download_root=self.indirme_dizini)
        return self._model

    def tanimla(self, ses: np.ndarray, ornek_hizi: int) -> str:
        ses = yeniden_ornekle(int16(ses), ornek_hizi, 16000).astype(np.float32) / 32768.0
        with self._kilit:
            parcalar, _ = self._yukle().transcribe(ses, language='tr', beam_size=1, vad_filter=False,
                                                   condition_on_previous_text=False,
                                                   initial_prompt=os.getenv('JARVIS_STT_SOZLUK', SOZLUK))
            return ' '.join(p.text.strip() for p in parcalar).strip()


class GoogleSTT:
    """Online: the recording is sent to Google. Only with JARVIS_SES_CEVRIMICI=1."""
    yerel = False
    ad = 'Google (çevrimiçi)'

    def tanimla(self, ses: np.ndarray, ornek_hizi: int) -> str:
        import speech_recognition as sr
        veri = sr.AudioData(int16(ses).tobytes(), ornek_hizi, 2)
        try:
            return sr.Recognizer().recognize_google(veri, language='tr-TR')
        except sr.UnknownValueError:
            return ''
