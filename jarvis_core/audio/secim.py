"""Which voice providers run, and an honest description for the UI.

Policy: local first. Online providers (Google STT, Edge TTS) only when the
user set JARVIS_SES_CEVRIMICI=1. No silent online fallback. A provider can be
forced with JARVIS_STT=whisper|google and JARVIS_TTS=piper|sapi|edge."""
import os


def cevrimici_izinli() -> bool:
    return os.getenv('JARVIS_SES_CEVRIMICI') == '1'


def _modul_var(ad: str) -> bool:
    import importlib.util
    return importlib.util.find_spec(ad) is not None


def stt_sec():
    """(provider or None, explanation)."""
    istenen = os.getenv('JARVIS_STT', '').lower()
    if istenen in ('', 'whisper', 'yerel'):
        if _modul_var('faster_whisper'):
            from .stt import WhisperSTT
            return WhisperSTT(), ''
        if istenen:
            return None, 'Yerel ses tanıma kurulu değil: python -m pip install faster-whisper'
    if istenen in ('', 'google'):
        if cevrimici_izinli() and _modul_var('speech_recognition'):
            from .stt import GoogleSTT
            return GoogleSTT(), 'Ses tanıma çevrimiçi (Google): konuşmanız Google\'a gönderiliyor.'
    return None, ('Ses tanıma yok. Yerel için: python -m pip install faster-whisper ve '
                  'python -m jarvis_core.audio.kur. Çevrimiçi Google tanımayı bilerek kullanmak için .env içine '
                  'JARVIS_SES_CEVRIMICI=1 yazın.')


def tts_sec():
    """(provider or None, explanation). Never presents a non-Turkish voice as Turkish."""
    istenen = os.getenv('JARVIS_TTS', '').lower()
    uyari = ''
    if istenen in ('', 'piper', 'yerel'):
        from .tts import PiperTTS
        p = PiperTTS()
        if p.hazir_mi():
            return p, ''
        if istenen == 'piper':
            return None, 'Piper Türkçe sesi kurulu değil: python -m jarvis_core.audio.kur'
    if istenen in ('', 'sapi', 'yerel'):
        try:
            from .tts import SapiTTS
            s = SapiTTS()
            if s.turkce:
                return s, ''
            uyari = 'Sistemde Türkçe ses yok (yalnız başka dilde ses var). '
        except Exception:
            pass
    if istenen in ('', 'edge') and cevrimici_izinli() and _modul_var('edge_tts'):
        from .tts import EdgeTTS
        return EdgeTTS(), uyari + 'Ses çıkışı çevrimiçi (Microsoft Edge): cevap metinleri Microsoft\'a gönderiliyor.'
    return None, (uyari + 'Yerel Türkçe ses yok; cevaplar yalnız yazı olarak gösterilecek. Kurmak için: '
                  'python -m jarvis_core.audio.kur (Piper Türkçe sesi, ~65 MB). Çevrimiçi Edge sesini bilerek '
                  'kullanmak için .env içine JARVIS_SES_CEVRIMICI=1 yazın.')


def durum() -> dict:
    """For the panel and the health report: what runs where."""
    stt, stt_not = stt_sec()
    tts, tts_not = tts_sec()
    return {'stt': stt.ad if stt else None, 'stt_yerel': bool(stt and stt.yerel),
            'tts': tts.ad if tts else None, 'tts_yerel': bool(tts and tts.yerel),
            'cevrimici_izinli': cevrimici_izinli(),
            'uyarilar': [n for n in (stt_not, tts_not) if n]}
