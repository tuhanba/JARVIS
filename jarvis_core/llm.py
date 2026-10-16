"""Ollama client: streaming chat (so a cancel stops generation at once),
health checks and clear Turkish errors. Ollama is the only backend."""
import socket
import threading
import time

import ollama
import requests

from .araclar.temel import Iptal


def ollama_hata_aciklamasi(hata: str) -> str:
    """Turn Ollama runner crashes into something the user can act on."""
    kucuk = (hata or '').lower()
    if 'cuda' in kucuk or 'llama-server process has terminated' in kucuk or 'runner process' in kucuk:
        return ('Ollama modeli ekran kartında çalıştırırken çöktü (sürücü veya CUDA sorunu). NVIDIA sürücüsünü '
                'güncelleyip bilgisayarı yeniden başlatın. Ayrıntı: ' + hata[:200])
    if 'out of memory' in kucuk or 'requires more system memory' in kucuk:
        return ('Model için bellek yetmedi. .env içinde OLLAMA_BAGLAM değerini küçültün (ör. 8192) veya daha '
                'küçük bir model seçin (qwen3.5:4b). Ayrıntı: ' + hata[:200])
    return f'Ollama hatası: {hata}'


class OllamaHatasi(Exception):
    """Message is meant to be shown / spoken to the user as is."""


class OllamaIstemci:
    def __init__(self, ayarlar) -> None:
        self.a = ayarlar
        self.istemci = ollama.Client(host=ayarlar.ollama_adres, timeout=30)  # metadata calls only

    # ------------------------------------------------------------- health
    def surum(self):
        try:
            return requests.get(f'{self.a.ollama_adres}/api/version', timeout=3).json().get('version')
        except (requests.RequestException, ValueError):
            return None

    def modeller(self) -> list:
        return [m.model for m in self.istemci.list().models]

    def yetenekler(self, model: str) -> list:
        return list(self.istemci.show(model).capabilities or [])

    def hazirla(self, is_turu: str = 'genel') -> str:
        """Check server, model and tool support; raise OllamaHatasi with what to do."""
        model = self.a.model(is_turu)
        if not self.surum():
            raise OllamaHatasi(f'Ollama çalışmıyor ({self.a.ollama_adres}). Ollama uygulamasını açın '
                               'veya "ollama serve" komutunu çalıştırın.')
        try:
            yetenek = self.yetenekler(model)
        except ollama.ResponseError:
            raise OllamaHatasi(f'"{model}" modeli yüklü değil. Komut satırında: ollama pull {model}')
        if 'tools' not in yetenek:
            raise OllamaHatasi(f'"{model}" araç çağırmayı desteklemiyor (yetenekleri: {", ".join(yetenek)}). '
                               '.env içinde OLLAMA_MODEL için araç destekli bir model seçin.')
        return model

    # ------------------------------------------------------------- model lifecycle
    # Process-wide: every client instance (task engine, screen tool, benchmark) shares
    # which model is loaded, so OLLAMA_TEK_MODEL really keeps one heavy model in memory.
    _yuklu_model = None
    _dusunme_karari = {}          # model -> value to send as `think`
    _kilit = threading.Lock()

    def _bosalt(self, model: str) -> None:
        """With limited memory keep only one model loaded."""
        with OllamaIstemci._kilit:
            onceki = OllamaIstemci._yuklu_model
            OllamaIstemci._yuklu_model = model
        if self.a.tek_model and onceki and onceki != model:
            try:
                self.istemci.generate(model=onceki, prompt='', keep_alive=0)
            except Exception:
                pass

    def dusunme_ayari(self, model: str):
        """What to send as `think`. With thinking off we normally send False, but some
        thinking-only models ignore it and write their reasoning into the answer text,
        which would be shown and spoken. One short probe per model detects that; such
        models then think in the separate field, which is never shown or spoken."""
        if self.a.dusunme:
            return True
        if model in OllamaIstemci._dusunme_karari:
            return OllamaIstemci._dusunme_karari[model]
        karar = False
        try:
            if 'thinking' in self.yetenekler(model):
                r = self.istemci.chat(model=model, think=False, keep_alive='30m',
                                      messages=[{'role': 'user', 'content': 'Yalnızca "tamam" yaz.'}],
                                      options={'num_ctx': 2048, 'num_predict': 48})
                icerik = dusunceyi_ayikla(r.message.content or '').strip().lower()
                karar = None if (len(icerik) > 24 or not icerik.startswith('tamam')) else False
        except Exception:
            return False          # cannot tell (Ollama down): the real call reports the error
        OllamaIstemci._dusunme_karari[model] = karar
        return karar

    @staticmethod
    def _soketleri_kapat(istemci) -> None:
        """Shut the HTTP socket down from another thread: unblocks a read that is
        waiting for the first token, and Ollama stops generating on disconnect."""
        try:
            for baglanti in list(istemci._client._transport._pool.connections):
                soket = getattr(getattr(getattr(baglanti, '_connection', None), '_network_stream', None), '_sock', None)
                if soket:
                    try:
                        soket.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
        except AttributeError:
            pass

    def sohbet(self, mesajlar: list, araclar: list, iptal, is_turu: str = 'genel', akis=None) -> dict:
        """Returns {'content': str, 'tool_calls': [{'function': {'name', 'arguments'}}], 'olcum': {...}}.

        The request runs in a worker thread so that a cancel takes effect at once,
        even while the model is still loading or reading the prompt. `akis(parca)` gets
        the visible answer text as it is generated (never the model's thinking). Tool
        calls are returned only after the turn ends, so none runs on half arguments."""
        model = self.a.model(is_turu)
        self._bosalt(model)
        dusun = self.dusunme_ayari(model)
        istemci = ollama.Client(host=self.a.ollama_adres, timeout=self.a.llm_zaman_asimi)
        kutu = {'icerik': [], 'cagrilar': [], 'son': None}
        ayiklayici = _DusunceAyiklayici()
        t0 = time.monotonic()

        def akit():
            try:
                for parca in istemci.chat(model=model, messages=mesajlar, tools=araclar or None, stream=True,
                                          think=dusun, options={'num_ctx': self.a.baglam},
                                          keep_alive='30m'):
                    if 'ilk' not in kutu and (parca.message.content or parca.message.tool_calls
                                              or getattr(parca.message, 'thinking', None)):
                        kutu['ilk'] = time.monotonic() - t0
                    gorunur = ayiklayici.besle(parca.message.content or '')
                    if gorunur:
                        kutu['icerik'].append(gorunur)
                        if akis:
                            try:
                                akis(gorunur)
                            except Exception:
                                pass
                    for c in parca.message.tool_calls or []:
                        kutu['cagrilar'].append({'function': {'name': c.function.name,
                                                              'arguments': dict(c.function.arguments or {})}})
                    if getattr(parca, 'done', False):
                        kutu['son'] = parca
                kalan = ayiklayici.bitir()
                if kalan:
                    kutu['icerik'].append(kalan)
                    if akis:
                        akis(kalan)
            except Exception as e:
                kutu['hata'] = e

        is_parcacigi = threading.Thread(target=akit, daemon=True)
        is_parcacigi.start()
        while is_parcacigi.is_alive():
            is_parcacigi.join(0.1)
            if iptal.is_set():
                self._soketleri_kapat(istemci)
                raise Iptal()
        e = kutu.get('hata')
        if e is not None:
            if isinstance(e, ollama.ResponseError):
                if e.status_code == 404:
                    raise OllamaHatasi(f'"{model}" modeli yüklü değil. Komut satırında: ollama pull {model}')
                raise OllamaHatasi(ollama_hata_aciklamasi(e.error))
            ad = e.__class__.__name__
            if 'Timeout' in ad:
                raise OllamaHatasi(f'Ollama {self.a.llm_zaman_asimi} saniyede yanıt vermedi.')
            if 'Connect' in ad or isinstance(e, (ConnectionError, OSError)):
                raise OllamaHatasi('Ollama\'ya bağlanılamadı. Ollama açık mı?')
            raise OllamaHatasi(f'Ollama ile iletişim hatası: {ad}')
        return {'content': ''.join(kutu['icerik']).strip(), 'tool_calls': kutu['cagrilar'],
                'olcum': olcum_cikar(kutu['son'], model, time.monotonic() - t0, kutu.get('ilk'))}


def dusunceyi_ayikla(metin: str) -> str:
    """Remove <think>...</think> blocks some models put into the answer text."""
    import re
    return re.sub(r'<think>.*?(</think>|$)', '', metin or '', flags=re.S)


class _DusunceAyiklayici:
    """Streaming version: hides text between <think> and </think> across chunk borders."""

    def __init__(self) -> None:
        self.icinde = False
        self.tampon = ''

    def besle(self, parca: str) -> str:
        self.tampon += parca
        cikti = []
        while self.tampon:
            if self.icinde:
                i = self.tampon.find('</think>')
                if i < 0:
                    self.tampon = self.tampon[-len('</think>'):]
                    break
                self.tampon = self.tampon[i + len('</think>'):]
                self.icinde = False
            else:
                i = self.tampon.find('<think>')
                if i < 0:
                    # keep a possible partial tag at the end for the next chunk
                    kes = max(0, len(self.tampon) - len('<think>') + 1)
                    if '<' not in self.tampon[kes:]:
                        kes = len(self.tampon)
                    cikti.append(self.tampon[:kes])
                    self.tampon = self.tampon[kes:]
                    break
                cikti.append(self.tampon[:i])
                self.tampon = self.tampon[i + len('<think>'):]
                self.icinde = True
        return ''.join(cikti)

    def bitir(self) -> str:
        kalan, self.tampon = ('' if self.icinde else self.tampon), ''
        return kalan


def olcum_cikar(son, model: str, toplam: float, ilk) -> dict:
    """Ollama's own timings (ns) from the final chunk, in seconds, plus what we measured."""
    def sn(ad):
        deger = getattr(son, ad, None) if son is not None else None
        return round(deger / 1e9, 3) if deger else None
    olcum = {'model': model, 'toplam_sn': round(toplam, 3), 'ilk_parca_sn': round(ilk, 3) if ilk else None,
             'yukleme_sn': sn('load_duration'), 'prompt_sn': sn('prompt_eval_duration'),
             'uretim_sn': sn('eval_duration'),
             'prompt_token': getattr(son, 'prompt_eval_count', None) if son is not None else None,
             'uretim_token': getattr(son, 'eval_count', None) if son is not None else None}
    if olcum['uretim_token'] and olcum['uretim_sn']:
        olcum['token_hizi'] = round(olcum['uretim_token'] / olcum['uretim_sn'], 1)
    if olcum['prompt_token'] and olcum['prompt_sn']:
        olcum['prompt_hizi'] = round(olcum['prompt_token'] / olcum['prompt_sn'], 1)
    # A load of more than a second means the model was not in memory (cold start).
    olcum['soguk'] = bool(olcum['yukleme_sn'] and olcum['yukleme_sn'] > 1.0)
    return olcum
