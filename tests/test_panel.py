"""Panel backend: access control, fast command round trip, approval flow."""
import json
import queue
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest


@pytest.fixture
def panel(ev):
    from jarvis_core.panel.sunucu import Panel, _isleyici
    p = Panel(sesli=False)
    srv = ThreadingHTTPServer(('127.0.0.1', 0), None)
    srv.RequestHandlerClass = _isleyici(p, srv.shutdown)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    p.taban = f'http://127.0.0.1:{srv.server_port}'
    p.olaylar = queue.Queue()
    p.dinleyiciler.append(p.olaylar)
    yield p
    srv.shutdown()


def _kod(url, **k):
    try:
        return urllib.request.urlopen(urllib.request.Request(url, **k), timeout=5).status
    except urllib.error.HTTPError as e:
        return e.code


def _post(p, yol, govde, **baslik):
    return _kod(p.taban + yol, data=json.dumps(govde).encode(), method='POST',
                headers={'X-Jarvis-Token': p.token, 'Content-Type': 'application/json', **baslik})


def _bekle(p, tur, sure=10):
    bitis = time.time() + sure
    while time.time() < bitis:
        olay = json.loads(p.olaylar.get(timeout=sure))
        if olay['tur'] == tur:
            return olay['veri']
    raise AssertionError(f'{tur} gelmedi')


def test_erisim_denetimi(panel):
    assert _kod(panel.taban + '/') == 403
    assert _kod(panel.taban + '/?t=yanlis') == 403
    assert _kod(f'{panel.taban}/?t={panel.token}') == 200
    assert _kod(panel.taban + '/api/dur', data=b'{}', method='POST') == 403
    assert _post(panel, '/api/dur', {}, Origin='http://kotu.example') == 403
    assert _post(panel, '/api/dur', {}) == 200


def test_hizli_komut_uctan_uca(panel):
    assert _post(panel, '/api/komut', {'metin': 'Saat kaç'}) == 200
    assert _bekle(panel, 'kullanici')['metin'] == 'Saat kaç'
    assert _bekle(panel, 'jarvis')['metin'].startswith('Saat ')


def test_onay_paneldeki_dugmeyle_verilir(panel):
    sonuc = {}
    t = threading.Thread(target=lambda: sonuc.update(c=panel._onay_iste('Silinsin mi?')))
    t.start()
    assert _bekle(panel, 'onay')['soru'] == 'Silinsin mi?'
    assert _post(panel, '/api/onay', {'cevap': True}) == 200
    t.join(5)
    assert sonuc['c'] is True


def test_onay_sesle_ya_da_yaziyla_reddedilebilir(panel):
    sonuc = {}
    t = threading.Thread(target=lambda: sonuc.update(c=panel._onay_iste('Kapatılsın mı?')))
    t.start()
    _bekle(panel, 'onay')
    panel.komut('hayır')
    t.join(5)
    assert sonuc['c'] is False


class _YavasMotor:
    """Stands in for Motor.calistir: waits for a cancel (or ignores it if inatci)."""

    def __init__(self, motor, inatci=False):
        self.motor, self.inatci = motor, inatci

    def __call__(self, metin):
        from jarvis_core.motor import GorevSonucu
        if metin == 'hızlı':
            return GorevSonucu('x2', 'tamamlandi', 'Bitti.')
        bitis = time.time() + 30
        while time.time() < bitis:
            if self.motor.iptal.is_set() and not self.inatci:
                return GorevSonucu('x1', 'iptal', 'Tamam efendim, durdurdum.')
            time.sleep(0.05)
        return GorevSonucu('x1', 'tamamlandi', 'geç kalan sonuç')


def _gorev_bitene_kadar(p, sure=10):
    bitis = time.time() + sure
    while p.mesgul.is_set() and time.time() < bitis:
        time.sleep(0.05)
    return not p.mesgul.is_set()


def test_durdurdan_sonra_yeni_komut_kabul_edilir(panel, monkeypatch):
    panel.ai_hazir = True
    monkeypatch.setattr(panel.motor, 'calistir', _YavasMotor(panel.motor))
    panel.komut('uzun bir iş yap')
    time.sleep(0.3)
    t0 = time.time()
    panel.komut('dur')
    assert _gorev_bitene_kadar(panel, 3), 'durdurduktan sonra panel serbest kalmadı'
    assert time.time() - t0 < 1.5
    assert panel.komut('hızlı') == 'basladi'
    assert _gorev_bitene_kadar(panel, 3)


def test_takilan_gorev_bekci_ile_birakilir_ve_yeni_gorevi_bozmaz(panel, monkeypatch):
    panel.ai_hazir = True
    yavas = _YavasMotor(panel.motor, inatci=True)
    monkeypatch.setattr(panel.motor, 'calistir', yavas)
    panel.komut('uzun bir iş yap')
    time.sleep(0.3)
    panel.dur()
    assert _gorev_bitene_kadar(panel, 6), 'bekçi paneli serbest bırakmadı'
    assert panel.komut('hızlı') == 'basladi'


def test_konusma_gorevi_bekletmez(panel, monkeypatch):
    panel.ses_acik = True
    konusulan = []
    monkeypatch.setattr(panel.ses, 'konus', lambda m: (konusulan.append(m), time.sleep(3)))
    threading.Thread(target=panel._konusma_dongusu, daemon=True).start()
    t0 = time.time()
    panel.komut('Saat kaç')
    assert _gorev_bitene_kadar(panel, 2) and time.time() - t0 < 1.5   # done while still talking
    time.sleep(0.3)
    assert konusulan and panel.konusuyor.is_set()
    panel.komut('Saat kaç')                                            # new command cuts the speech
    assert panel.konusma_kuyrugu.qsize() <= 1
