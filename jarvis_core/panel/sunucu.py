"""Desktop panel backend.

Serves the HUD (arayuz.html) on 127.0.0.1 only, guarded by a random token,
streams state with Server-Sent Events and opens the page as a standalone app
window (Edge --app). The page talks to the same task engine as the console.

Security: bound to localhost; every request must carry the token, come from
the panel's own origin and name 127.0.0.1/localhost as Host (DNS rebinding),
so other local programs or web pages cannot drive JARVIS through it. Request
bodies are size-limited and type-checked (the string "false" is not a yes).

Events carry an increasing id; a reconnecting page sends Last-Event-ID and gets
what it missed from a bounded ring buffer, plus /api/durum as a snapshot that
includes a pending approval."""
import collections
import itertools
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
from ..gizlilik import maskele_nesne
from ..motor import Motor
from ..niyet import Niyet, cevap_coz, durdurma_mi

PENCERESIZ = 0x08000000 if sys.platform == 'win32' else 0
HTML = Path(__file__).with_name('arayuz.html')
ONAY_SURESI = 120          # seconds; no answer = no
OLAY_TAMPONU = 500         # events kept for reconnect replay
DINLEYICI_KUYRUGU = 1000   # a stuck page is dropped instead of growing memory forever
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
        self.olay_sayaci = itertools.count(1)
        self.son_olaylar = collections.deque(maxlen=OLAY_TAMPONU)
        self.mesgul = threading.Event()           # a task is running
        self.konusuyor = threading.Event()
        self.onay_kutusu = None                   # pending approval, bound to one action (see _onay_iste)
        self._onay_ayrinti = {}                   # details of the action the engine is about to ask for
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
        with self.kilit:
            kimlik = next(self.olay_sayaci)
            paket = json.dumps({'id': kimlik, 'tur': tur, 'veri': maskele_nesne(veri), 'zaman': time.time()},
                               ensure_ascii=False)
            if tur not in ('telemetri',):
                self.son_olaylar.append((kimlik, paket))
            for q in list(self.dinleyiciler):
                try:
                    q.put_nowait((kimlik, paket))
                except queue.Full:
                    self.dinleyiciler.remove(q)   # that page is not reading; it will reconnect and replay

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
        elif olay == 'onay':
            self._onay_ayrinti = dict(veri)

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
        self.yayinla('jarvis', {'metin': _gorunur(metin), 'durum': durum})
        metin = _seslendirilebilir(metin)
        if self.ses_acik and metin:
            self.konusuyor.set()
            onceki = self.durum
            self.durum_ayarla('konusuyor')
            try:
                self.ses.konus(metin)
            finally:
                self.konusuyor.clear()
                self.durum_ayarla(onceki if onceki != 'konusuyor' else 'hazir')

    # ------------------------------------------------------------- questions from tools
    def _onay_iste(self, soru: str) -> bool:
        """Ask the user about exactly one action. The answer must name this request's id
        (buttons) or arrive while it is the pending one (voice/text); a late, duplicate or
        stale answer cannot approve anything else. No answer within ONAY_SURESI = no."""
        ayrinti, self._onay_ayrinti = self._onay_ayrinti, {}
        kutu = {'id': secrets.token_hex(6), 'olay': threading.Event(), 'cevap': False, 'soru': soru,
                'son': time.time() + ONAY_SURESI, 'arac': ayrinti.get('arac'), 'argumanlar': ayrinti.get('argumanlar'),
                'gorev': ayrinti.get('gorev'), 'eylem_id': ayrinti.get('eylem_id'), 'sebep': ayrinti.get('sebep')}
        self.onay_kutusu = kutu
        onceki_durum = self.durum
        self.durum_ayarla('onay')
        self.yayinla('onay', self._onay_ozeti(kutu))
        if self.ses_acik:
            threading.Thread(target=self.ses.konus, args=(soru,), daemon=True).start()
        kutu['olay'].wait(ONAY_SURESI)
        cevap = kutu['cevap'] is True and time.time() <= kutu['son'] + 1
        with self.kilit:
            if self.onay_kutusu is kutu:
                self.onay_kutusu = None
        self.yayinla('onay_bitti', {'id': kutu['id'], 'cevap': cevap})
        self.durum_ayarla('calisiyor' if onceki_durum != 'onay' else 'hazir')
        return cevap

    @staticmethod
    def _onay_ozeti(kutu) -> dict:
        return {k: kutu[k] for k in ('id', 'soru', 'arac', 'argumanlar', 'gorev', 'eylem_id', 'sebep', 'son')}

    def onay_cevapla(self, cevap: bool, kimlik: str = None) -> bool:
        """Returns False when there is no pending approval or the id does not match it."""
        with self.kilit:
            kutu = self.onay_kutusu
            if not kutu or (kimlik is not None and kimlik != kutu['id']) or kutu['olay'].is_set():
                return False
            kutu['cevap'] = cevap is True
            kutu['olay'].set()
            return True

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
        if self.onay_kutusu:
            karar = cevap_coz(UYANDIRMA.sub('', metin, count=1))
            if karar == 'belirsiz':
                self.yayinla('bilgi', {'metin': 'Anlayamadım. Onay için yalnızca "evet" ya da "hayır" deyin.'})
                return 'onay_belirsiz'
            self.onay_cevapla(karar == 'evet')
            return 'onay'
        if self.girdi_bekleyen:
            self.girdi_bekleyen['metin'] = metin
            self.girdi_bekleyen['olay'].set()
            return 'girdi'
        if self.mesgul.is_set():
            if durdurma_mi(metin):
                self.dur()
                return 'iptal'
            self.yayinla('bilgi', {'metin': 'Bir görev sürüyor. Durdurmak için "dur" deyin veya DURDUR\'a basın.'})
            return 'mesgul'
        self.yayinla('kullanici', {'metin': metin, 'kaynak': kaynak})
        self.mesgul.set()
        threading.Thread(target=self._isle, args=(metin,), daemon=True).start()
        return 'basladi'

    def _isle(self, metin: str) -> None:
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
            if isinstance(cevap, Niyet):
                # Fast path: no model, but the same executor, policy, approval and audit log.
                sonuc = self.motor.hizli_calistir(metin, cevap)
                self.yayinla('gorev_bitti', {'durum': sonuc.durum, 'sure': time.time() - t0, 'gorev': sonuc.gorev_id,
                                             'yerel': True})
                self.soyle(sonuc.cevap, sonuc.durum)
                return
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
            sonuc = self.motor.calistir(metin, kaynak='panel')
            self.yayinla('gorev_bitti', {'durum': sonuc.durum, 'sure': time.time() - t0, 'gorev': sonuc.gorev_id})
            self.soyle(sonuc.cevap, sonuc.durum)
        except Exception as e:
            self.yayinla('gorev_bitti', {'durum': 'hata', 'sure': time.time() - t0})
            self.soyle(f'Beklenmeyen bir hata oluştu: {e}', 'hata')
        finally:
            self.mesgul.clear()
            if self.durum not in ('konusuyor',):
                self.durum_ayarla('dinliyor' if self.surekli_dinleme else 'hazir')

    def dur(self) -> None:
        sayi = self.motor.iptal_et()
        self.ses.sustur()
        if self.onay_kutusu:
            self.onay_cevapla(False)
        # "Stopped" is reported by the task itself once it has really ended (gorev_bitti);
        # here we only acknowledge the request.
        self.yayinla('bilgi', {'metin': 'Durdurma istendi.' if sayi else 'Durduruldu.'})

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
                veri['gorev_sayisi'] = self.motor.depo.gorev_sayisi()
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
            if self.onay_kutusu or self.girdi_bekleyen:
                self.komut(metin, kaynak='ses')
            elif self.mesgul.is_set():
                if durdurma_mi(metin):
                    self.dur()
            elif UYANDIRMA.search(metin):
                istek = UYANDIRMA.sub('', metin, count=1).strip()
                if not istek:
                    self.yayinla('jarvis', {'metin': 'Efendim?'})
                    if self.ses_acik:
                        self.konusuyor.set()
                        self.ses.konus('Efendim?')
                        self.konusuyor.clear()
                    istek = self.ses.dinle()
                if istek:
                    self.komut(istek, kaynak='ses')

    # ------------------------------------------------------------- snapshot
    def ozet(self) -> dict:
        return {'durum': self.durum, 'ai': {'hazir': self.ai_hazir, 'model': self.model, 'hata': self.ai_hata},
                'mikrofon': self.mikrofon, 'surekli': self.surekli_dinleme, 'ses': self.ses_acik,
                'mesgul': self.mesgul.is_set(), 'telemetri': self.son_telemetri,
                'yarim_kalanlar': self.motor.yarim_kalanlar,
                'gecmis': [{'id': g['id'], 'istek': g['istek'], 'durum': g['durum'], 'zaman': g['olusturma'],
                            'kaynak': g.get('kaynak')} for g in self.motor.depo.gorevler(15)],
                'calisan_gorevler': self.motor.calisiyor(),
                'onay': self._onay_ozeti(self.onay_kutusu) if self.onay_kutusu else None,
                'son_olay': self.son_olaylar[-1][0] if self.son_olaylar else 0}

    def baslat_arka_plan(self) -> None:
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
            port = self.server.server_port
            if self.headers.get('Host') not in (f'127.0.0.1:{port}', f'localhost:{port}'):
                return False   # DNS rebinding: a foreign name pointing at 127.0.0.1
            kaynak = self.headers.get('Origin')
            return kaynak in (None, f'http://127.0.0.1:{port}', f'http://localhost:{port}')

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
                q = queue.Queue(maxsize=DINLEYICI_KUYRUGU)
                try:
                    son = int(self.headers.get('Last-Event-ID') or (sorgu.get('son') or ['0'])[0])
                except ValueError:
                    son = 0
                with panel.kilit:
                    kacan = [(k, p) for k, p in panel.son_olaylar if k > son] if son else []
                    panel.dinleyiciler.append(q)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                try:
                    for kimlik, paket in kacan:
                        self.wfile.write(f'id: {kimlik}\ndata: {paket}\n\n'.encode('utf-8'))
                    self.wfile.flush()
                    while True:
                        try:
                            kimlik, paket = q.get(timeout=15)
                            self.wfile.write(f'id: {kimlik}\ndata: {paket}\n\n'.encode('utf-8'))
                        except queue.Empty:
                            self.wfile.write(b': canli\n\n')
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass
                finally:
                    with panel.kilit:
                        if q in panel.dinleyiciler:
                            panel.dinleyiciler.remove(q)
                return
            self._yanit(404, b'{}')

        def do_POST(self):
            url = urlparse(self.path)
            if not self._izinli(parse_qs(url.query)):
                return self._yanit(403, b'{"hata":"yetkisiz"}')
            try:
                uzunluk = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                return self._yanit(400, b'{"hata":"uzunluk"}')
            if uzunluk > 20000:
                return self._yanit(413, b'{"hata":"istek cok buyuk"}')
            try:
                govde = json.loads(self.rfile.read(uzunluk) or b'{}')
            except ValueError:
                return self._yanit(400, b'{"hata":"gecersiz JSON"}')
            if not isinstance(govde, dict):
                return self._yanit(400, b'{"hata":"nesne bekleniyor"}')

            def bool_al(ad):
                deger = govde.get(ad)
                if not isinstance(deger, bool):     # "false" (a string) must not become True
                    raise ValueError(ad)
                return deger

            yol = url.path
            sonuc = 'ok'
            try:
                if yol == '/api/komut':
                    metin = govde.get('metin', '')
                    if not isinstance(metin, str) or len(metin) > 4000:
                        raise ValueError('metin')
                    sonuc = panel.komut(metin)
                elif yol == '/api/dur':
                    panel.dur()
                elif yol == '/api/onay':
                    kimlik = govde.get('id')
                    if kimlik is not None and not isinstance(kimlik, str):
                        raise ValueError('id')
                    if not panel.onay_cevapla(bool_al('cevap'), kimlik):
                        return self._yanit(409, b'{"hata":"bekleyen onay yok veya kimlik eslesmiyor"}')
                elif yol == '/api/dinle':
                    panel.bir_kez_dinle()
                elif yol == '/api/surekli':
                    panel.surekli_ayarla(bool_al('acik'))
                elif yol == '/api/ses':
                    panel.ses_acik = bool_al('acik')
                    if not panel.ses_acik:
                        panel.ses.sustur()
                elif yol == '/api/ollama':
                    threading.Thread(target=panel.ollama_baslat, daemon=True).start()
                elif yol == '/api/kapat':
                    threading.Thread(target=kapat, daemon=True).start()
                else:
                    return self._yanit(404, b'{}')
            except ValueError as e:
                return self._yanit(400, json.dumps({'hata': f'gecersiz alan: {e}'}).encode())
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
