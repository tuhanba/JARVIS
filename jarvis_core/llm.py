"""Ollama client: streaming chat (so a cancel stops generation at once),
health checks and clear Turkish errors. Ollama is the only backend."""
import http.client
import json
import socket
import threading
from urllib.parse import urlparse

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
        self._yuklu = None
        self._yetenekler = {}

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

    # ------------------------------------------------------------- chat
    def _bosalt(self, model: str) -> None:
        """With limited memory keep only one model loaded."""
        if self.a.tek_model and self._yuklu and self._yuklu != model:
            try:
                self.istemci.generate(model=self._yuklu, prompt='', keep_alive=0)
            except Exception:
                pass
        self._yuklu = model

    def _yetenek_onbellek(self, model: str) -> list:
        if model not in self._yetenekler:
            try:
                self._yetenekler[model] = self.yetenekler(model)
            except Exception:
                return []
        return self._yetenekler[model]

    @staticmethod
    def _kapat(baglanti) -> None:
        """Shut the socket down and close it from another thread. The blocked read
        returns at once and Ollama, seeing the client gone, stops generating -
        otherwise the next request would queue behind the cancelled answer."""
        soket = getattr(baglanti, 'sock', None)
        if soket is not None:
            try:
                soket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                soket.close()
            except OSError:
                pass
        try:
            baglanti.close()
        except Exception:
            pass

    def sohbet(self, mesajlar: list, araclar: list, iptal: threading.Event, is_turu: str = 'genel') -> dict:
        """Returns {'content': str, 'tool_calls': [{'function': {'name', 'arguments'}}]}.

        Streams /api/chat over a connection we own (http.client), read in a worker
        thread, so a cancel can close the socket immediately - even while the
        model is still loading or reading the prompt."""
        model = self.a.model(is_turu)
        self._bosalt(model)
        istek = {'model': model, 'messages': mesajlar, 'stream': True,
                 'options': {'num_ctx': self.a.baglam}, 'keep_alive': self.a.model_bekleme}
        if araclar:
            istek['tools'] = araclar
        if 'thinking' in self._yetenek_onbellek(model):
            istek['think'] = self.a.dusunme      # thinking models default to "on" otherwise
        adres = urlparse(self.a.ollama_adres)
        baglanti = http.client.HTTPConnection(adres.hostname or '127.0.0.1', adres.port or 11434,
                                              timeout=self.a.llm_zaman_asimi)
        kutu = {'icerik': [], 'cagrilar': []}

        def akit():
            try:
                baglanti.request('POST', '/api/chat', body=json.dumps(istek, ensure_ascii=False).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
                yanit = baglanti.getresponse()
                if yanit.status != 200:
                    govde = yanit.read().decode('utf-8', 'replace')
                    try:
                        mesaj = json.loads(govde).get('error', govde)
                    except ValueError:
                        mesaj = govde
                    kutu['hata'] = ('http', yanit.status, mesaj)
                    return
                for satir in yanit:
                    if not satir.strip():
                        continue
                    parca = json.loads(satir)
                    if parca.get('error'):
                        kutu['hata'] = ('http', 500, parca['error'])
                        return
                    m = parca.get('message') or {}
                    if m.get('content'):
                        kutu['icerik'].append(m['content'])
                    for c in m.get('tool_calls') or []:
                        f = c.get('function') or {}
                        kutu['cagrilar'].append({'function': {'name': f.get('name', ''),
                                                              'arguments': f.get('arguments') or {}}})
                    if parca.get('done'):
                        break
            except Exception as e:
                kutu['hata'] = ('baglanti', 0, e)
            finally:
                if not iptal.is_set():
                    baglanti.close()

        is_parcacigi = threading.Thread(target=akit, daemon=True)
        is_parcacigi.start()
        while is_parcacigi.is_alive():
            is_parcacigi.join(0.1)
            if iptal.is_set():
                self._kapat(baglanti)
                raise Iptal()
        if 'hata' in kutu:
            tur, kod, ayrinti = kutu['hata']
            if tur == 'http':
                if kod == 404:
                    raise OllamaHatasi(f'"{model}" modeli yüklü değil. Komut satırında: ollama pull {model}')
                raise OllamaHatasi(ollama_hata_aciklamasi(str(ayrinti)))
            ad = ayrinti.__class__.__name__
            if 'timeout' in ad.lower():
                raise OllamaHatasi(f'Ollama {self.a.llm_zaman_asimi} saniyede yanıt vermedi.')
            raise OllamaHatasi(f'Ollama\'ya bağlanılamadı ({ad}). Ollama açık mı?')
        return {'content': ''.join(kutu['icerik']), 'tool_calls': kutu['cagrilar']}
