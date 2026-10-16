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
