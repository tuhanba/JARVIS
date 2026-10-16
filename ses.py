"""Speech in and out. TTS: local Piper Turkish voice with the JARVIS effect
(default), Microsoft edge-tts, or a Turkish Windows voice. STT: Google speech
recognition, or plain keyboard input in text mode."""
import asyncio
import os
import queue
import re
import sys
import tempfile
import threading

import speech_recognition as sr

SES = os.getenv('JARVIS_SES', 'tr-TR-AhmetNeural')

_yazi_modu = False
_kilit = threading.Lock()  # reminder threads and the main loop must not talk at once
_sus = threading.Event()   # set by sustur() to cut the current sentence short
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
    from jarvis_core.konusma import cal

    fd, yol = tempfile.mkstemp(suffix='.mp3')
    os.close(fd)
    try:
        asyncio.run(edge_tts.Communicate(metin, SES).save(yol))
        if os.path.getsize(yol) == 0:
            raise RuntimeError('edge-tts boş ses döndürdü')
        cal(yol, _sus)
    finally:
        os.remove(yol)


def _piper_konus(metin: str) -> None:
    """Local Turkish voice, sentence by sentence: the next sentence is synthesized
    while the current one plays, so the first words come out quickly."""
    from jarvis_core import konusma
    if not konusma.piper_hazir():
        raise RuntimeError('Piper ses modeli indirilmemiş (python -m jarvis_core.konusma --indir)')
    cumleler = [c for c in re.split(r'(?<=[.!?…])\s+', metin.strip()) if c.strip()] or [metin]
    kuyruk = queue.Queue(maxsize=2)

    def uret():
        for cumle in cumleler:
            if _sus.is_set():
                break
            try:
                kuyruk.put(konusma.sentezle_dosyaya(cumle))
            except Exception as e:
                kuyruk.put(e)
                return
        kuyruk.put(None)

    threading.Thread(target=uret, daemon=True).start()
    while True:
        parca = kuyruk.get()
        if parca is None:
            return
        if isinstance(parca, Exception):
            raise parca
        try:
            if not _sus.is_set():
                konusma.cal(parca, _sus)
        finally:
            os.remove(parca)


def _yerel_konus(metin: str) -> None:
    """Windows SAPI - only with a Turkish voice. An English voice reading Turkish
    is what made JARVIS sound mixed and unclear, so that is never used."""
    global _pyttsx
    if sys.platform != 'win32':
        raise RuntimeError('Windows sesi yalnız Windows\'ta')
    if _pyttsx is False:
        raise RuntimeError('Windows\'ta Türkçe ses yok')
    if _pyttsx is None:
        import pyttsx3
        motor = pyttsx3.init()
        for v in motor.getProperty('voices'):
            kimlik = f'{v.id} {v.name}'.lower()
            if 'turk' in kimlik or 'tr-tr' in kimlik or 'tolga' in kimlik:
                motor.setProperty('voice', v.id)
                _pyttsx = motor
                break
        else:
            _pyttsx = False      # checked once; never keep an English engine around
            motor.stop()
            del motor
            raise RuntimeError('Windows\'ta Türkçe ses yok')
    _pyttsx.say(metin)
    _pyttsx.runAndWait()


def sustur() -> None:
    """Stop speaking now (user pressed stop or started talking)."""
    _sus.set()
    if _pyttsx:
        try:
            _pyttsx.stop()
        except Exception:
            pass


MOTORLAR = {'piper': _piper_konus, 'edge': _edge_konus, 'windows': _yerel_konus}


def konus(metin: str) -> None:
    print(f'JARVIS: {metin}')
    tercih = os.getenv('JARVIS_TTS', 'piper').lower()
    sira = [tercih] + [m for m in ('piper', 'edge', 'windows') if m != tercih]
    with _kilit:
        _sus.clear()
        for ad in sira:
            if ad not in MOTORLAR:
                continue
            try:
                MOTORLAR[ad](metin)
                return
            except Exception as e:
                print(f'(ses motoru "{ad}" kullanılamadı: {e})')
        print('(ses çıkışı yok)')


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
