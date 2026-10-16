"""Stage C: local-first voice. Hardware-free parts (text preparation, turn
detection, provider policy) always run; the offline TTS->STT round trip runs
when the models are present (JARVIS_SES_MODEL_VERI=<data dir with sesler/>)."""
import os

import numpy as np
import pytest

from jarvis_core.audio.metin_hazirla import sayi_oku, seslendirme_metni
from jarvis_core.audio.vad import SiraAlgilayici


@pytest.mark.parametrize('n,beklenen', [(0, 'sıfır'), (11, 'on bir'), (100, 'yüz'), (1000, 'bin'), (1001, 'bin bir'),
                                        (2026, 'iki bin yirmi altı'), (1_000_000, 'bir milyon'),
                                        (1_250_000, 'bir milyon iki yüz elli bin')])
def test_sayi_oku(n, beklenen):
    assert sayi_oku(n) == beklenen


@pytest.mark.parametrize('metin,beklenen', [
    ('Saat 14:05.', 'Saat on dört sıfır beş.'),
    ('Pil %40, disk 85% dolu.', 'Pil yüzde kırk, disk yüzde seksen beş dolu.'),
    ('Kur 34,25 TL.', 'Kur otuz dört virgül yirmi beş lira.'),
    ('**Hava** 23°C 🌞', 'Hava yirmi üç derece'),
    ('Nüfus 1.250.000.', 'Nüfus bir milyon iki yüz elli bin.'),
    (r'C:\Users\Batu\Documents\rapor_2026.pdf kaydedildi.', 'rapor iki bin yirmi altı pdf dosyası kaydedildi.'),
    ('https://www.ornek.com.tr/sayfa adresine bak.', 'ornek nokta com nokta tr sitesi adresine bak.'),
    ('Ayrıca vb. işler.', 'Ayrıca ve benzeri işler.')])
def test_seslendirme_metni(metin, beklenen):
    assert seslendirme_metni(metin) == beklenen


def _cerceveler(ses, boy=480):
    return [ses[i:i + boy] for i in range(0, len(ses) - boy + 1, boy)]


def _konusma(sn, hz=16000, genlik=8000):
    t = np.arange(int(sn * hz)) / hz
    return (genlik * np.sin(2 * np.pi * 220 * t) * (1 + 0.3 * np.sin(2 * np.pi * 3 * t))).astype(np.int16)


def _gurultu(sn, hz=16000, genlik=60, tohum=0):
    return np.random.default_rng(tohum).normal(0, genlik, int(sn * hz)).astype(np.int16)


def test_konusma_sonu_ve_on_kayit():
    s = SiraAlgilayici()
    akis = np.concatenate([_gurultu(1.0), _konusma(1.2), _gurultu(1.5, tohum=1)])
    parcalar = [p for c in _cerceveler(akis) if (p := s.isle(c)) is not None]
    assert len(parcalar) == 1
    sure = len(parcalar[0]) / 16000
    # speech (1.2 s) + pre-roll (<=0.3 s) + trailing silence until end-of-turn (0.7 s)
    assert 1.8 <= sure <= 2.4, sure


def test_kisa_ses_konusma_sayilmaz():
    s = SiraAlgilayici()
    akis = np.concatenate([_gurultu(1.0), _konusma(0.09), _gurultu(1.5, tohum=2)])
    assert all(s.isle(c) is None for c in _cerceveler(akis))


def test_azami_sure_ve_sinirli_tampon():
    s = SiraAlgilayici(azami_sure_s=2.0)
    akis = np.concatenate([_gurultu(0.5), _konusma(10.0)])
    parcalar = [p for c in _cerceveler(akis) if (p := s.isle(c)) is not None]
    assert parcalar and all(len(p) / 16000 <= 2.05 for p in parcalar)
    assert len(s._on) <= s._on.maxlen


def test_cevrimici_ses_yalniz_acik_izinle(monkeypatch):
    from jarvis_core.audio import secim
    monkeypatch.delenv('JARVIS_SES_CEVRIMICI', raising=False)
    monkeypatch.setenv('JARVIS_STT', 'google')
    stt, not_ = secim.stt_sec()
    assert stt is None and 'JARVIS_SES_CEVRIMICI=1' in not_
    monkeypatch.setenv('JARVIS_SES_CEVRIMICI', '1')
    stt, not_ = secim.stt_sec()
    assert stt is not None and not stt.yerel and 'Google' in not_


def test_turkce_olmayan_ses_turkce_diye_sunulmaz(monkeypatch, ev):
    from jarvis_core.audio import secim, tts

    class Ingilizce:
        turkce, yerel, ad = False, True, 'Microsoft David'
    monkeypatch.setattr(tts, 'SapiTTS', Ingilizce)
    monkeypatch.setattr(tts.PiperTTS, 'hazir_mi', lambda self: False)
    monkeypatch.delenv('JARVIS_SES_CEVRIMICI', raising=False)
    monkeypatch.delenv('JARVIS_TTS', raising=False)
    saglayici, not_ = secim.tts_sec()
    assert saglayici is None and 'Türkçe ses yok' in not_


def test_ingilizce_whisper_modeli_reddedilir():
    from jarvis_core.audio.stt import WhisperSTT
    with pytest.raises(ValueError):
        WhisperSTT('small.en')


@pytest.mark.skipif(not os.getenv('JARVIS_SES_MODEL_VERI'), reason='yerel ses modelleri yok (audio.kur)')
def test_cevrimdisi_tts_stt_turu(monkeypatch):
    """T13 (partial): a Turkish sentence goes Piper -> WAV -> faster-whisper with no network."""
    monkeypatch.setenv('JARVIS_VERI', os.environ['JARVIS_SES_MODEL_VERI'])
    monkeypatch.setenv('HF_HUB_OFFLINE', '1')
    from jarvis_core.audio.stt import WhisperSTT
    from jarvis_core.audio.tts import PiperTTS
    tts = PiperTTS()
    assert tts.hazir_mi()
    ses, hz = tts.sentezle(seslendirme_metni('Masaüstündeki dosyaları listele.'))
    metin = WhisperSTT(os.getenv('JARVIS_STT_MODEL', 'small'), cihaz='cpu').tanimla(ses, hz).lower()
    assert 'masaüst' in metin and 'listele' in metin, metin


# ----------------------------------------------------------------- F14 / T34: persistent reminders

def _zamanlayici(ev, teslim=None):
    from jarvis_core.ayarlar import Ayarlar
    from jarvis_core.depo import Depo
    from jarvis_core.zamanlayici import Zamanlayici
    return Zamanlayici(Depo(Ayarlar().veritabani), teslim=teslim)


def test_hatirlatma_yeniden_baslatmadan_sonra_kaybolmaz(ev):
    import time
    z1 = _zamanlayici(ev)
    z1.ekle(time.time() + 3600, 'çay')
    gelen = []
    z2 = _zamanlayici(ev, teslim=gelen.append)                 # "restart": new process, same DB
    assert [k['metin'] for k in z2.bekleyenler()] == ['çay']
    z2.tara(simdi=time.time() + 3601)
    assert [k['metin'] for k in gelen] == ['çay'] and not z2.bekleyenler()


def test_kacirilan_hatirlatma_tek_sefer_ve_iki_kopya_cift_teslim_yok(ev):
    import time
    gelen = []
    a, b = _zamanlayici(ev, teslim=gelen.append), _zamanlayici(ev, teslim=gelen.append)
    a.ekle(time.time() - 3 * 3600, 'ilaç')                      # time passed while JARVIS was closed
    a.ekle(time.time() - 3 * 3600, 'eski haber', kacirilan='atla')
    a.tara()
    b.tara()
    assert [k['metin'] for k in gelen] == ['ilaç'] and gelen[0]['gec'] and 'Kaçırılan' in gelen[0]['metin_soz']
    durumlar = {r['metin']: r['durum'] for r in a.depo.calistir_ham('SELECT * FROM hatirlatmalar')}
    assert durumlar == {'ilaç': 'teslim', 'eski haber': 'kacirildi'}


def test_gunluk_tekrar_duvar_saatini_korur(ev, monkeypatch):
    import datetime as dt
    from jarvis_core.zamanlayici import saat_dilimi
    monkeypatch.setenv('JARVIS_SAAT_DILIMI', 'Europe/Berlin')     # has DST (Istanbul does not)
    tz = saat_dilimi()
    z = _zamanlayici(ev, teslim=lambda k: None)
    ilk = dt.datetime(2026, 10, 24, 8, 0, tzinfo=tz)              # day before the clocks go back
    z.ekle(ilk.timestamp(), 'vitamin', tekrar='gunluk')
    z.tara(simdi=ilk.timestamp() + 1)
    sonraki = [k for k in z.bekleyenler() if k['metin'] == 'vitamin']
    yerel = dt.datetime.fromtimestamp(sonraki[0]['zaman'], tz)
    assert (yerel.hour, yerel.minute) == (8, 0) and yerel.date() > ilk.date()


def test_dogal_dil_zaman_cozumu():
    import datetime as dt
    from jarvis_core.zamanlayici import saat_dilimi, zaman_coz
    simdi = dt.datetime(2026, 10, 16, 10, 0, tzinfo=saat_dilimi())
    assert zaman_coz('10 dakika sonra', simdi) == simdi + dt.timedelta(minutes=10)
    assert zaman_coz('yarın 9da', simdi) == dt.datetime(2026, 10, 17, 9, 0, tzinfo=saat_dilimi())
    assert zaman_coz('saat 9:30', simdi) == dt.datetime(2026, 10, 17, 9, 30, tzinfo=saat_dilimi())   # passed today
    assert zaman_coz('saat 18', simdi) == dt.datetime(2026, 10, 16, 18, 0, tzinfo=saat_dilimi())
    assert zaman_coz('merhaba', simdi) is None


def test_hatirlatma_komutu_kalici_kayit_ve_dogrulama(motor_yap, ev):
    import komutlar
    niyet = komutlar._yerel_komut('yarın 9da toplantıyı hatırlat', 'yarın 9da toplantıyı hatırlat', None)
    m = motor_yap([])
    s = m.hizli_calistir('yarın 9da toplantıyı hatırlat', niyet)
    assert s.durum == 'tamamlandi' and '09:00' in s.cevap and 'toplantıyı' in s.cevap
    assert [k['metin'] for k in _zamanlayici(ev).bekleyenler()] == ['toplantıyı']
