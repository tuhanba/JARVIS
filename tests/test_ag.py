"""T27: web fetching limits (size, type, redirects, local-network targets)."""
import http.server
import threading

import pytest

from jarvis_core.ag import AgHatasi, getir


@pytest.fixture
def sunucu():
    class Isleyici(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path == '/buyuk':                      # endless body, no Content-Length
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                try:
                    for _ in range(10000):
                        self.wfile.write(b'a' * 65536)
                except OSError:
                    pass
                return
            if self.path == '/yonlen':
                self.send_response(302)
                self.send_header('Location', 'http://169.254.169.254/latest/meta-data')
                self.end_headers()
                return
            if self.path == '/ikili':
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.end_headers()
                self.wfile.write(b'\x00' * 10)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write('<p>Merhaba dünya</p>'.encode())
    s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Isleyici)
    s.daemon_threads = True
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{s.server_port}'
    s.shutdown()


def test_yerel_ag_izinsiz_okunmaz(sunucu):
    with pytest.raises(AgHatasi, match='yerel ağ'):
        getir(sunucu + '/')
    metin, _, _ = getir(sunucu + '/', izinli_hostlar=('127.0.0.1',))
    assert 'Merhaba dünya' in metin


def test_sonsuz_yanit_sinirda_kesilir(sunucu):
    metin, _, _ = getir(sunucu + '/buyuk', izinli_hostlar=('127.0.0.1',), azami_bayt=200_000)
    assert len(metin) < 210_000 and 'sınırında kesildi' in metin


def test_yonlendirme_her_adimda_denetlenir(sunucu):
    with pytest.raises(AgHatasi, match='169.254.169.254'):
        getir(sunucu + '/yonlen', izinli_hostlar=('127.0.0.1',))


def test_metin_olmayan_icerik_reddedilir(sunucu):
    with pytest.raises(AgHatasi, match='metin değil'):
        getir(sunucu + '/ikili', izinli_hostlar=('127.0.0.1',))


def test_web_araci_politikayi_kullanir(motor_yap, ev, sunucu):
    m = motor_yap([[('web_sayfasi_oku', {'adres': sunucu + '/'})], 'Okudum.'])
    s = m.calistir('şu sayfayı oku')
    assert 'yerel ağ' in m.depo.adimlar(s.gorev_id)[0]['cikti'] and s.durum != 'tamamlandi'
    m.izinler.ag_izni_ekle('127.0.0.1')
    m.llm.senaryo = [[('web_sayfasi_oku', {'adres': sunucu + '/'})], 'Okudum.']
    assert m.calistir('şu sayfayı tekrar oku').durum == 'tamamlandi'
