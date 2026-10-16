"""Speech in and out: Turkish TTS (edge-tts, pyttsx3 fallback) and STT
(Google speech recognition), or plain keyboard input in text mode."""
import asyncio
import os
import tempfile
import threading

import speech_recognition as sr

SES = os.getenv('JARVIS_SES', 'tr-TR-AhmetNeural')

_yazi_modu = False
_kilit = threading.Lock()  # reminder threads and the main loop must not talk at once
_pyttsx = None


def yazi_modunu_ac() -> None:
    global _yazi_modu
    _yazi_modu = True


def mikrofon_var() -> bool:
    try:
        with sr.Microphone():
            return True
    except Exception:
        return False


def _edge_konus(metin: str) -> None:
    import edge_tts
    import pygame

    fd, yol = tempfile.mkstemp(suffix='.mp3')
    os.close(fd)
    try:
        asyncio.run(edge_tts.Communicate(metin, SES).save(yol))
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(yol)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.wait(100)
        pygame.mixer.music.unload()
    finally:
        os.remove(yol)


def _yerel_konus(metin: str) -> None:
    global _pyttsx
    import pyttsx3

    if _pyttsx is None:
        _pyttsx = pyttsx3.init()
        for v in _pyttsx.getProperty('voices'):
            kimlik = f'{v.id} {v.name}'.lower()
            if 'turk' in kimlik or 'tr-tr' in kimlik or 'tolga' in kimlik:
                _pyttsx.setProperty('voice', v.id)
                break
    _pyttsx.say(metin)
    _pyttsx.runAndWait()


def konus(metin: str) -> None:
    print(f'JARVIS: {metin}')
    with _kilit:
        try:
            _edge_konus(metin)
        except Exception:
            # No internet or no audio output for edge-tts: use the offline voice.
            try:
                _yerel_konus(metin)
            except Exception as e:
                print(f'(ses çıkışı yok: {e})')


def dinle() -> str:
    if _yazi_modu:
        try:
            return input('Sen: ').strip()
        except EOFError:
            return 'çıkış'

    r = sr.Recognizer()
    r.pause_threshold = 0.8
    r.dynamic_energy_threshold = True
    with sr.Microphone() as kaynak:
        r.adjust_for_ambient_noise(kaynak, duration=0.5)
        print('Dinliyorum...')
        try:
            ses = r.listen(kaynak, timeout=8, phrase_time_limit=15)
        except sr.WaitTimeoutError:
            return ''
    try:
        metin = r.recognize_google(ses, language='tr-TR')
    except sr.UnknownValueError:
        return ''
    except sr.RequestError:
        print('Ses tanıma servisine ulaşılamadı (internet?).')
        return ''
    print(f'Sen: {metin}')
    return metin


def onayla(soru: str) -> bool:
    """Ask a yes/no question; anything but a clear yes counts as no."""
    konus(f'{soru} Evet mi, hayır mı?')
    for _ in range(2):
        cevap = dinle().lower()
        if any(k in cevap for k in ('evet', 'tamam', 'onaylıyorum', 'olur', 'yap')):
            return True
        if any(k in cevap for k in ('hayır', 'hayir', 'iptal', 'vazgeç', 'yapma')):
            return False
    return False
