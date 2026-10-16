"""Speech in and out, or plain keyboard input in text mode.

Providers come from jarvis_core/audio: local first (faster-whisper for
recognition, Piper or a Windows Turkish voice for speech). Google
recognition and the Edge voice send audio/text online and are used only
with JARVIS_SES_CEVRIMICI=1. Audio packages are imported lazily so headless
tests and the text mode work without them."""
import os
import tempfile
import threading

_yazi_modu = False
_kilit = threading.Lock()  # reminder threads and the main loop must not talk at once
_sus = threading.Event()   # set by sustur() to cut the current sentence short


def yazi_modunu_ac() -> None:
    global _yazi_modu
    _yazi_modu = True


def _sr():
    import speech_recognition as sr
    return sr


def mikrofon_var() -> bool:
    try:
        with _sr().Microphone():
            return True
    except Exception:
        return False


_saglayicilar = {}


def _tts():
    if 'tts' not in _saglayicilar:
        from jarvis_core.audio.secim import tts_sec
        _saglayicilar['tts'], not_ = tts_sec()
        if not_:
            print(f'(ses çıkışı) {not_}')
    return _saglayicilar['tts']


def _stt():
    if 'stt' not in _saglayicilar:
        from jarvis_core.audio.secim import stt_sec
        _saglayicilar['stt'], not_ = stt_sec()
        if not_:
            print(f'(ses tanıma) {not_}')
    return _saglayicilar['stt']


def ses_durumu() -> dict:
    """What the voice really uses (local / online / none), for the panel and health report."""
    from jarvis_core.audio.secim import durum
    return durum()


def sustur() -> None:
    """Stop speaking now (user pressed stop or started talking)."""
    _sus.set()
    saglayici = _saglayicilar.get('tts')
    if saglayici is not None and hasattr(saglayici, 'durdur'):
        saglayici.durdur()


def konus(metin: str) -> None:
    """Show the text; speak a Turkish-normalised version with the selected voice.
    With no Turkish voice available the answer is only printed (never read by a
    voice of another language)."""
    print(f'JARVIS: {metin}')
    from jarvis_core.audio.metin_hazirla import seslendirme_metni
    okunacak = seslendirme_metni(metin)
    if not okunacak:
        return
    with _kilit:
        _sus.clear()
        saglayici = _tts()
        if saglayici is None:
            return
        try:
            from jarvis_core.audio.tts import dosya_cal, wav_yaz
            if hasattr(saglayici, 'sentezle'):
                ses, hz = saglayici.sentezle(okunacak)
                fd, yol = tempfile.mkstemp(suffix='.wav')
                os.close(fd)
                try:
                    wav_yaz(yol, ses, hz)
                    dosya_cal(yol, _sus)
                finally:
                    os.remove(yol)
            elif hasattr(saglayici, 'mp3'):
                yol = saglayici.mp3(okunacak)
                try:
                    dosya_cal(yol, _sus)
                finally:
                    os.remove(yol)
            else:
                saglayici.konus(okunacak, _sus)
        except Exception as e:
            print(f'(ses çıkışı çalışmadı: {e})')


def dinle() -> str:
    if _yazi_modu:
        try:
            return input('Sen: ').strip()
        except EOFError:
            return 'çıkış'

    sr = _sr()
    saglayici = _stt()
    if saglayici is None:
        return ''
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
        import numpy as np
        ham = np.frombuffer(ses.get_raw_data(convert_rate=16000, convert_width=2), dtype=np.int16)
        metin = saglayici.tanimla(ham, 16000)
    except Exception as e:
        print(f'Ses tanınamadı ({saglayici.ad}): {e}')
        return ''
    if metin:
        print(f'Sen: {metin}')
    return metin


def onayla(soru: str) -> bool:
    """Ask a yes/no question; anything but a clear yes counts as no. Negation and
    doubt win ("yapma", "olur mu bilmiyorum" are not a yes)."""
    from jarvis_core.niyet import cevap_coz
    konus(f'{soru} Evet mi, hayır mı?')
    for deneme in range(2):
        karar = cevap_coz(dinle())
        if karar == 'evet':
            return True
        if karar == 'hayir':
            return False
        if deneme == 0:
            konus('Anlayamadım. Lütfen yalnızca evet ya da hayır deyin.')
    return False
