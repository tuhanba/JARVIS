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
        _, paket = p.olaylar.get(timeout=sure)
        olay = json.loads(paket)
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


# ----------------------------------------------------------------- Stage A: approvals bound to one action

def _onay_baslat(panel, soru='Silinsin mi?'):
    sonuc = {}
    t = threading.Thread(target=lambda: sonuc.update(c=panel._onay_iste(soru)))
    t.start()
    return t, sonuc, _bekle(panel, 'onay')


def test_yapma_onay_sayilmaz(panel):
    """F01: 'yapma' contains 'yap'; the old substring check approved it."""
    t, sonuc, _ = _onay_baslat(panel)
    assert panel.komut('yapma') == 'onay'
    t.join(5)
    assert sonuc['c'] is False


def test_belirsiz_cevap_onaylamaz_ve_bekler(panel):
    t, sonuc, _ = _onay_baslat(panel)
    assert panel.komut('olur mu bilmiyorum') == 'onay_belirsiz'
    assert panel.onay_kutusu is not None            # still waiting, nothing decided
    assert panel.komut('evet') == 'onay'
    t.join(5)
    assert sonuc['c'] is True


def test_eski_onay_kimligi_yeni_islemi_onaylayamaz(panel):
    t, sonuc, ilk = _onay_baslat(panel, 'Birinci?')
    assert _post(panel, '/api/onay', {'cevap': False, 'id': ilk['id']}) == 200
    t.join(5)
    t2, sonuc2, ikinci = _onay_baslat(panel, 'İkinci?')
    assert ikinci['id'] != ilk['id']
    assert _post(panel, '/api/onay', {'cevap': True, 'id': ilk['id']}) == 409   # stale id
    assert panel.onay_kutusu is not None
    assert _post(panel, '/api/onay', {'cevap': True, 'id': ikinci['id']}) == 200
    t2.join(5)
    assert sonuc['c'] is False and sonuc2['c'] is True


def test_metin_false_onay_degildir(panel):
    """T37: the string "false" was bool()-ed into True."""
    t, sonuc, o = _onay_baslat(panel)
    assert _post(panel, '/api/onay', {'cevap': 'false', 'id': o['id']}) == 400
    assert _post(panel, '/api/surekli', {'acik': 'false'}) == 400
    assert panel.onay_kutusu is not None
    assert _post(panel, '/api/onay', {'cevap': False, 'id': o['id']}) == 200
    t.join(5)
    assert sonuc['c'] is False


def test_yeniden_yuklemede_bekleyen_onay_geri_gelir(panel):
    """T36: /api/durum returns the pending approval; SSE replays missed events once."""
    t, sonuc, o = _onay_baslat(panel)
    durum = json.loads(urllib.request.urlopen(f'{panel.taban}/api/durum?t={panel.token}', timeout=5).read())
    assert durum['onay']['id'] == o['id'] and durum['onay']['soru'] == 'Silinsin mi?'
    # reconnect asking for events after an older id: the 'onay' event is replayed
    istek = urllib.request.Request(f'{panel.taban}/olaylar?t={panel.token}', headers={'Last-Event-ID': '1'})
    akis = urllib.request.urlopen(istek, timeout=5)
    gorulen = []
    while len(gorulen) < 50:
        satir = akis.readline().decode()
        if satir.startswith('data: '):
            gorulen.append(json.loads(satir[6:]))
            if gorulen[-1]['tur'] == 'onay':
                break
    akis.close()
    assert gorulen[-1]['veri']['id'] == o['id'] and all(g['id'] > 1 for g in gorulen)
    panel.onay_cevapla(False, o['id'])
    t.join(5)


def test_yabanci_host_ve_buyuk_istek_reddedilir(panel):
    assert _post(panel, '/api/dur', {}, Host='kotu.example') == 403
    assert _kod(panel.taban + '/api/komut', data=b'{"metin":"' + b'a' * 30000 + b'"}', method='POST',
                headers={'X-Jarvis-Token': panel.token}) == 413
    assert _post(panel, '/api/komut', {'metin': 5}) == 400


def test_durum_sorusu_gorevi_durdurmaz(panel):
    """F19: 'durum' contains 'dur'."""
    panel.mesgul.set()
    iptaller = []
    panel.motor.iptal_et = lambda gid=None: iptaller.append(1) or 0
    assert panel.komut('durum ne') == 'mesgul' and not iptaller
    assert panel.komut('dur') == 'iptal' and iptaller
    panel.mesgul.clear()


def test_hizli_komut_gorev_kaydi_olusturur(panel):
    """F06: a fast command is a recorded task with a step, not an untracked side call."""
    assert _post(panel, '/api/komut', {'metin': 'Saat kaç'}) == 200
    bitti = _bekle(panel, 'gorev_bitti')
    assert bitti['durum'] == 'tamamlandi' and bitti['gorev']
    adimlar = panel.motor.depo.adimlar(bitti['gorev'])
    assert [a['arac'] for a in adimlar] == ['saat_tarih']
