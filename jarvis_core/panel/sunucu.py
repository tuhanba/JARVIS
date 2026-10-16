"""Desktop panel backend.

Serves the HUD (arayuz.html) on 127.0.0.1 only, guarded by a random token,
streams state with Server-Sent Events and opens the page as a standalone app
window (Edge --app). The page talks to the same task engine as the console.

Security: bound to localhost; every request must carry the token and come
from the panel's own origin, so other local programs or web pages cannot
drive JARVIS through it."""
import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import psutil

from ..ayarlar import PROJE, Ayarlar
from ..motor import DURDUR, Motor

PENCERESIZ = 0x08000000 if sys.platform == 'win32' else 0
HTML = Path(__file__).with_name('arayuz.html')
UYANDIRMA = re.compile(r'\b(jarvis|carvis|cervis|çarvis|jarviş|jervis|jarves)\b[,.!]*\s*', re.IGNORECASE)


def _gorunur(metin: str) -> str:
    """Text for the screen: no emoji or markdown emphasis, file names left intact."""
    metin = re.sub(r'[\U0001F000-\U0001FAFF☀-➿️‍]', '', metin or '')
    return re.sub(r' {2,}', ' ', re.sub(r'\*\*|`|^#+\s*', '', metin, flags=re.M)).strip()


def _seslendirilebilir(metin: str) -> str:
    """Text for TTS: also no symbols the voice would read out ("alt çizgi")."""
    return re.sub(r' {2,}', ' ', re.sub(r'[*#`_]+', ' ', _gorunur(metin))).strip()


class Panel:
    def __init__(self, sesli: bool = True) -> None:
        self.a = Ayarlar()
        self.token = secrets.token_urlsafe(24)
        self.dinleyiciler = []                    # one queue per open SSE stream
        self.kilit = threading.Lock()
        self.mesgul = threading.Event()           # a task is running
        self.gorev_no = 0
        self.konusuyor = threading.Event()
        self.konusma_kuyrugu = queue.Queue()
        self.onay_kutusu = None                   # {'olay': Event, 'cevap': bool}
        self.girdi_bekleyen = None                # follow-up question from a fast command
        self.ses_acik = sesli
        self.surekli_dinleme = False
        self.mikrofon = False
        self.durum = 'baslatiliyor'
        self.son_telemetri = {}

        self.motor = Motor(onay=self._onay_iste, bildir=self._motor_olayi)
        self.ai_hazir, self.ai_hata, self.model = False, '', self.a.model()
        self._komutlar_hazirla()

    # ------------------------------------------------------------- events to the page
    def yayinla(self, tur: str, veri=None) -> None:
        paket = json.dumps({'tur': tur, 'veri': veri, 'zaman': time.time()}, ensure_ascii=False)
        with self.kilit:
            for q in list(self.dinleyiciler):
                q.put(paket)

    def durum_ayarla(self, durum: str, ayrinti: str = '') -> None:
        self.durum = durum
        self.yayinla('durum', {'durum': durum, 'ayrinti': ayrinti})

    def _motor_olayi(self, olay: str, veri: dict) -> None:
        if olay == 'dusunuyor':
            self.durum_ayarla('dusunuyor')
        elif olay == 'arac':
            self.durum_ayarla('calisiyor', veri['arac'])
            self.yayinla('arac', {'arac': veri['arac'], 'argumanlar': veri['argumanlar']})
        elif olay == 'arac_sonuc':
            self.yayinla('arac_sonuc', veri)
        elif olay == 'ilerleme':
            self.yayinla('ilerleme', veri)

    # ------------------------------------------------------------- fast commands
    def _komutlar_hazirla(self) -> None:
        sys.path.insert(0, str(PROJE))
        import komutlar
        import ses
        self.komutlar, self.ses = komutlar, ses
        # Fast commands and power actions ask questions through these; route them to the panel.
        komutlar.konus = self.soyle
        komutlar.dinle = self._girdi_bekle
        ses.onayla = self._onay_iste

    class _AI:
        def __init__(self, panel):
            self.aktif, self.depo = panel.ai_hazir, panel.motor.depo

    # ------------------------------------------------------------- speech out
    def soyle(self, metin: str, durum: str = '') -> None:
        """Show the answer now and queue it for speech. Never blocks the task, so a
        long sentence being spoken cannot keep the next command waiting."""
        self.yayinla('jarvis', {'metin': _gorunur(metin), 'durum': durum})
        metin = _seslendirilebilir(metin)
        if self.ses_acik and metin:
            self.konusma_kuyrugu.put(metin)

    def _konusma_dongusu(self) -> None:
        while True:
            metin = self.konusma_kuyrugu.get()
            self.konusuyor.set()
            if not self.mesgul.is_set():
                self.durum_ayarla('konusuyor')
            try:
                self.ses.konus(metin)
            except Exception as e:
                print(f'konuşma hatası: {e!r}')
            finally:
                self.konusuyor.clear()
                if self.konusma_kuyrugu.empty() and not self.mesgul.is_set():
                    self.durum_ayarla('dinliyor' if self.surekli_dinleme else 'hazir')

    def sesi_kes(self) -> None:
        """Drop queued sentences and stop the one being spoken."""
        try:
            while True:
                self.konusma_kuyrugu.get_nowait()
        except queue.Empty:
            pass
        self.ses.sustur()

    # ------------------------------------------------------------- questions from tools
    def _onay_iste(self, soru: str) -> bool:
        olay = threading.Event()
        self.onay_kutusu = {'olay': olay, 'cevap': False}
        self.durum_ayarla('onay')
        self.yayinla('onay', {'soru': soru})
        if self.ses_acik:
            threading.Thread(target=self.ses.konus, args=(soru,), daemon=True).start()
        olay.wait(120)
        cevap = self.onay_kutusu['cevap']
        self.onay_kutusu = None
        self.yayinla('onay_bitti', {'cevap': cevap})
        self.durum_ayarla('calisiyor')
        return cevap

    def onay_cevapla(self, cevap: bool) -> None:
        if self.onay_kutusu:
            self.onay_kutusu['cevap'] = bool(cevap)
            self.onay_kutusu['olay'].set()

    def _girdi_bekle(self) -> str:
        kutu = {'olay': threading.Event(), 'metin': ''}
        self.girdi_bekleyen = kutu
        self.durum_ayarla('bekliyor')
        kutu['olay'].wait(60)
        self.girdi_bekleyen = None
        return kutu['metin']

    # ------------------------------------------------------------- commands in
    def komut(self, metin: str, kaynak: str = 'yazı') -> str:
        """Entry point for typed and spoken input. Returns what happened."""
        metin = (metin or '').strip()
        if not metin:
            return 'bos'
        k = self.komutlar.kucuk(metin)
        if self.onay_kutusu:
            evet = any(w in k for w in ('evet', 'tamam', 'onay', 'olur', 'yap'))
            self.onay_cevapla(evet)
            return 'onay'
        if self.girdi_bekleyen:
            self.girdi_bekleyen['metin'] = metin
            self.girdi_bekleyen['olay'].set()
            return 'girdi'
        if self.mesgul.is_set():
            if any(w in k for w in DURDUR):
                self.dur()
                return 'iptal'
            self.yayinla('bilgi', {'metin': 'Bir görev sürüyor. Durdurmak için "dur" deyin veya DURDUR\'a basın.'})
            return 'mesgul'
        self.sesi_kes()
        self.yayinla('kullanici', {'metin': metin, 'kaynak': kaynak})
        self.mesgul.set()
        self.gorev_no += 1
        threading.Thread(target=self._isle, args=(metin, self.gorev_no), daemon=True).start()
        return 'basladi'

    def _isle(self, metin: str, no: int = 0) -> None:
        t0 = time.time()
        try:
            self.durum_ayarla('dusunuyor')
            k = self.komutlar.kucuk(metin)
            if any(c in k for c in self.komutlar.CIKIS):
                self.soyle('Görüşürüz efendim.')
                self.yayinla('kapat')
                return
            yalin = re.sub(r'^(hey )?jarvis[, ]*', '', k) or k
            cevap = self.komutlar._yerel_komut(yalin, metin, self._AI(self))
            if cevap is not None:
                self.yayinla('gorev_bitti', {'durum': 'tamamlandi', 'sure': time.time() - t0, 'yerel': True})
                self.soyle(cevap, 'tamamlandi')
                return
            if not self.ai_hazir:
                self._ai_kontrol()
            if not self.ai_hazir:
                self.yayinla('gorev_bitti', {'durum': 'hata', 'sure': time.time() - t0})
                self.soyle(self.ai_hata or 'Yapay zeka kapalı.', 'hata')
                return
            self.yayinla('gorev_basladi', {'istek': metin})
            sonuc = self.motor.calistir(metin)
            self.yayinla('gorev_bitti', {'durum': sonuc.durum, 'sure': time.time() - t0, 'gorev': sonuc.gorev_id})
            self.soyle(sonuc.cevap, sonuc.durum)
        except Exception as e:
            self.yayinla('gorev_bitti', {'durum': 'hata', 'sure': time.time() - t0})
            self.soyle(f'Beklenmeyen bir hata oluştu: {e}', 'hata')
        finally:
            if no != self.gorev_no:
                return      # released by the stop watchdog; a newer task owns the panel now
            self.mesgul.clear()
            if self.durum not in ('konusuyor',):
                self.durum_ayarla('dinliyor' if self.surekli_dinleme else 'hazir')

    def dur(self) -> None:
        self.motor.iptal_et()
        self.sesi_kes()
        if self.onay_kutusu:
            self.onay_cevapla(False)
        if self.girdi_bekleyen:
            self.girdi_bekleyen['olay'].set()
        self.yayinla('bilgi', {'metin': 'Durduruldu.'})
        threading.Thread(target=self._dur_bekcisi, daemon=True).start()

    def _dur_bekcisi(self) -> None:
        """If the task thread has not let go 4 s after a stop (a stuck tool, a hung
        network call), release the panel anyway so new commands are accepted."""
        bitis = time.time() + 4
        while time.time() < bitis:
            if not self.mesgul.is_set():
                return
            time.sleep(0.1)
        self.gorev_no += 1          # the stuck thread's result is ignored from now on
        self.mesgul.clear()
        self.durum_ayarla('dinliyor' if self.surekli_dinleme else 'hazir')
        self.yayinla('gorev_bitti', {'durum': 'iptal', 'sure': 0})
        self.yayinla('bilgi', {'metin': 'Görev zorla bırakıldı; yeni komut verebilirsiniz.'})

    # ------------------------------------------------------------- AI / health
    def _ai_kontrol(self) -> None:
        try:
            self.model = self.motor.llm.hazirla()
            self.ai_hazir, self.ai_hata = True, ''
        except Exception as e:
            self.ai_hazir, self.ai_hata = False, str(e)
        self.yayinla('ai', {'hazir': self.ai_hazir, 'model': self.model, 'hata': self.ai_hata})
        if self.durum == 'baslatiliyor':
            # Fast commands work without the model, so the panel is usable either way.
            self.durum_ayarla('hazir')

    def ollama_baslat(self) -> None:
        if shutil.which('ollama'):
            subprocess.Popen(['ollama', 'serve'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=PENCERESIZ)
            time.sleep(3)
        self._ai_kontrol()

    def _gpu(self):
        if not shutil.which('nvidia-smi'):
            return None
        try:
            p = subprocess.run(['nvidia-smi', '--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu',
                                '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5,
                               creationflags=PENCERESIZ)
            ad, kullanim, dolu, toplam, isi = [x.strip() for x in p.stdout.splitlines()[0].split(',')]
            return {'ad': ad, 'kullanim': float(kullanim), 'vram_dolu': float(dolu) / 1024,
                    'vram_toplam': float(toplam) / 1024, 'isi': float(isi)}
        except Exception:
            return None

    def _telemetri_dongusu(self) -> None:
        sayac = 0
        psutil.cpu_percent()
        while True:
            vm = psutil.virtual_memory()
            veri = {'cpu': psutil.cpu_percent(), 'ram': vm.percent, 'ram_dolu': vm.used / 2**30,
                    'ram_toplam': vm.total / 2**30, 'gpu': self._gpu(),
                    'disk': psutil.disk_usage(os.path.abspath(os.sep)).percent}
            if sayac % 5 == 0:
                try:
                    from ..llm import OllamaIstemci
                    surum = OllamaIstemci(self.a).surum()
                except Exception:
                    surum = None
                veri['ollama'] = surum
                if surum and not self.ai_hazir:
                    self._ai_kontrol()
                elif not surum and self.ai_hazir:
                    self.ai_hazir = False
                    self.ai_hata = 'Ollama çalışmıyor.'
                    self.yayinla('ai', {'hazir': False, 'model': self.model, 'hata': self.ai_hata})
                veri['hafiza'] = len(self.motor.depo.hafiza())
                veri['gorev_sayisi'] = len(self.motor.depo.gorevler(1000))
            self.son_telemetri.update(veri)
            self.yayinla('telemetri', self.son_telemetri)
            sayac += 1
            time.sleep(2)

    # ------------------------------------------------------------- microphone
    def _mikrofon_kontrol(self) -> None:
        try:
            self.mikrofon = self.ses.mikrofon_var()
        except Exception:
            self.mikrofon = False
        self.yayinla('mikrofon', {'var': self.mikrofon})

    def bir_kez_dinle(self) -> None:
        if not self.mikrofon:
            self.yayinla('bilgi', {'metin': 'Mikrofon bulunamadı.'})
            return
        self.ses.sustur()

        def is_():
            self.durum_ayarla('dinliyor')
            metin = self.ses.dinle()
            if metin:
                self.komut(UYANDIRMA.sub('', metin, count=1) or metin, kaynak='ses')
            elif not self.mesgul.is_set():
                self.durum_ayarla('hazir')
        threading.Thread(target=is_, daemon=True).start()

    def surekli_ayarla(self, acik: bool) -> None:
        if acik and not self.mikrofon:
            self.yayinla('bilgi', {'metin': 'Mikrofon bulunamadı.'})
            acik = False
        onceki, self.surekli_dinleme = self.surekli_dinleme, acik
        self.yayinla('surekli', {'acik': acik})
        if acik and not onceki:
            threading.Thread(target=self._surekli_dongu, daemon=True).start()

    def _surekli_dongu(self) -> None:
        """Wake word loop. Never listens while JARVIS itself is talking (no self-hearing);
        while a task runs it only reacts to stop words."""
        while self.surekli_dinleme:
            if self.konusuyor.is_set():
                time.sleep(0.1)
                continue
            if not self.mesgul.is_set() and not self.onay_kutusu:
                self.durum_ayarla('dinliyor')
            metin = self.ses.dinle()
            if not metin or not self.surekli_dinleme:
                continue
            k = self.komutlar.kucuk(metin)
            if self.onay_kutusu or self.girdi_bekleyen:
                self.komut(metin, kaynak='ses')
            elif self.mesgul.is_set():
                if any(w in k for w in DURDUR):
                    self.dur()
            elif UYANDIRMA.search(metin):
                istek = UYANDIRMA.sub('', metin, count=1).strip()
                if not istek:
                    self.soyle('Efendim?')
                    time.sleep(0.2)
                    while self.konusuyor.is_set() or not self.konusma_kuyrugu.empty():
                        time.sleep(0.05)
                    istek = self.ses.dinle()
                if istek:
                    self.komut(istek, kaynak='ses')

    # ------------------------------------------------------------- snapshot
    def ozet(self) -> dict:
        return {'durum': self.durum, 'ai': {'hazir': self.ai_hazir, 'model': self.model, 'hata': self.ai_hata},
                'mikrofon': self.mikrofon, 'surekli': self.surekli_dinleme, 'ses': self.ses_acik,
                'mesgul': self.mesgul.is_set(), 'telemetri': self.son_telemetri,
                'yarim_kalanlar': self.motor.yarim_kalanlar,
                'gecmis': [{'id': g['id'], 'istek': g['istek'], 'durum': g['durum'], 'zaman': g['olusturma']}
                           for g in self.motor.depo.gorevler(15)],
                'onay': None}

    def _ses_modeli_hazirla(self) -> None:
        from .. import konusma
        if os.getenv('JARVIS_TTS', 'piper').lower() != 'piper':
            return
        if not konusma.piper_hazir():
            self.yayinla('bilgi', {'metin': 'Türkçe ses modeli indiriliyor (yaklaşık 63 MB, bir kez)...'})
            son = {'y': -1}

            def ilerleme(m):
                y = int(re.sub(r'\D', '', m) or 0) // 25
                if y != son['y']:
                    son['y'] = y
                    self.yayinla('bilgi', {'metin': m})
            if not konusma.piper_indir(ilerleme):
                self.yayinla('bilgi', {'metin': 'Ses modeli indirilemedi; çevrimiçi ses kullanılacak.'})
                return
            self.yayinla('bilgi', {'metin': 'Türkçe ses modeli hazır.'})
        try:
            konusma._piper_ses()      # load once now so the first answer is not delayed
        except Exception as e:
            print(f'Piper yüklenemedi: {e!r}')

    def baslat_arka_plan(self) -> None:
        threading.Thread(target=self._konusma_dongusu, daemon=True).start()
        threading.Thread(target=self._ses_modeli_hazirla, daemon=True).start()
        threading.Thread(target=self._telemetri_dongusu, daemon=True).start()
        threading.Thread(target=self._ai_kontrol, daemon=True).start()
        threading.Thread(target=self._mikrofon_kontrol, daemon=True).start()


# ----------------------------------------------------------------- HTTP

def _isleyici(panel: Panel, kapat):
    class Isleyici(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _izinli(self, sorgu) -> bool:
            # Token in the query (page load, SSE) or header (API calls).
            token = self.headers.get('X-Jarvis-Token') or (sorgu.get('t') or [''])[0]
            if not secrets.compare_digest(token, panel.token):
                return False
            kaynak = self.headers.get('Origin')
            return kaynak in (None, f'http://127.0.0.1:{self.server.server_port}')

        def _yanit(self, kod: int, govde: bytes, tur='application/json; charset=utf-8') -> None:
            self.send_response(kod)
            self.send_header('Content-Type', tur)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy',
                             "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                             "connect-src 'self'; img-src 'self' data:")
            self.end_headers()
            self.wfile.write(govde)

        def do_GET(self):
            url = urlparse(self.path)
            sorgu = parse_qs(url.query)
            if not self._izinli(sorgu):
                return self._yanit(403, b'{"hata":"yetkisiz"}')
            if url.path == '/':
                html = HTML.read_text(encoding='utf-8').replace('__TOKEN__', panel.token)
                return self._yanit(200, html.encode('utf-8'), 'text/html; charset=utf-8')
            if url.path == '/api/durum':
                return self._yanit(200, json.dumps(panel.ozet(), ensure_ascii=False).encode('utf-8'))
            if url.path == '/olaylar':
                q = queue.Queue()
                with panel.kilit:
                    panel.dinleyiciler.append(q)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                try:
                    while True:
                        try:
                            paket = q.get(timeout=15)
                            self.wfile.write(f'data: {paket}\n\n'.encode('utf-8'))
                        except queue.Empty:
                            self.wfile.write(b': canli\n\n')
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    with panel.kilit:
                        panel.dinleyiciler.remove(q)
                return
            self._yanit(404, b'{}')

        def do_POST(self):
            url = urlparse(self.path)
            if not self._izinli(parse_qs(url.query)):
                return self._yanit(403, b'{"hata":"yetkisiz"}')
            try:
                uzunluk = min(int(self.headers.get('Content-Length') or 0), 20000)
                govde = json.loads(self.rfile.read(uzunluk) or b'{}')
            except ValueError:
                return self._yanit(400, b'{}')
            yol = url.path
            sonuc = 'ok'
            if yol == '/api/komut':
                sonuc = panel.komut(str(govde.get('metin', ''))[:4000])
            elif yol == '/api/dur':
                panel.dur()
            elif yol == '/api/onay':
                panel.onay_cevapla(bool(govde.get('cevap')))
            elif yol == '/api/dinle':
                panel.bir_kez_dinle()
            elif yol == '/api/surekli':
                panel.surekli_ayarla(bool(govde.get('acik')))
            elif yol == '/api/ses':
                panel.ses_acik = bool(govde.get('acik'))
                if not panel.ses_acik:
                    panel.ses.sustur()
            elif yol == '/api/ollama':
                threading.Thread(target=panel.ollama_baslat, daemon=True).start()
            elif yol == '/api/kapat':
                threading.Thread(target=kapat, daemon=True).start()
            else:
                return self._yanit(404, b'{}')
            self._yanit(200, json.dumps({'sonuc': sonuc}).encode())
    return Isleyici


def edge_bul():
    adaylar = [shutil.which('msedge')]
    for kok in (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles'), os.environ.get('LOCALAPPDATA')):
        if kok:
            adaylar.append(os.path.join(kok, 'Microsoft', 'Edge', 'Application', 'msedge.exe'))
    adaylar += [shutil.which('chromium'), shutil.which('google-chrome'), shutil.which('chrome')]
    return next((a for a in adaylar if a and os.path.exists(a)), None)


def calistir(pencere: bool = True, port: int = 0) -> None:
    panel = Panel()
    sunucu = ThreadingHTTPServer(('127.0.0.1', port), None)
    kapat = sunucu.shutdown
    sunucu.RequestHandlerClass = _isleyici(panel, kapat)
    sunucu.daemon_threads = True
    url = f'http://127.0.0.1:{sunucu.server_port}/?t={panel.token}'
    panel.baslat_arka_plan()
    print(f'JARVIS paneli: http://127.0.0.1:{sunucu.server_port}/ (yalnız bu bilgisayardan)')

    if pencere:
        tarayici = edge_bul()
        if tarayici:
            profil = Ayarlar().veri_dizini / 'panel_profili'
            surec = subprocess.Popen([tarayici, f'--app={url}', '--window-size=1440,900',
                                      f'--user-data-dir={profil}', '--no-first-run', '--disable-features=Translate'],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            def pencere_kapaninca():
                t0 = time.time()
                surec.wait()
                # If an earlier panel window was still open the launcher hands off and
                # exits at once; only a window that really lived means "closed by user".
                if time.time() - t0 > 5:
                    time.sleep(1)
                    kapat()
            threading.Thread(target=pencere_kapaninca, daemon=True).start()
        else:
            import webbrowser
            webbrowser.open(url)
    try:
        sunucu.serve_forever(poll_interval=0.3)
    finally:
        panel.motor.iptal_et()
        panel.surekli_dinleme = False
