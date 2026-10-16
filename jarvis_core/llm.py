"""Ollama client: streaming chat (so a cancel stops generation at once),
health checks and clear Turkish errors. Ollama is the only backend."""
import socket
import threading

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

    def sohbet(self, mesajlar: list, araclar: list, iptal: threading.Event, is_turu: str = 'genel') -> dict:
        """Returns {'content': str, 'tool_calls': [{'function': {'name', 'arguments'}}]}.

        The request runs in a worker thread so that a cancel takes effect at once,
        even while the model is still loading or reading the prompt."""
        model = self.a.model(is_turu)
        self._bosalt(model)
        istemci = ollama.Client(host=self.a.ollama_adres, timeout=self.a.llm_zaman_asimi)
        kutu = {'icerik': [], 'cagrilar': []}

        def akit():
            try:
                for parca in istemci.chat(model=model, messages=mesajlar, tools=araclar or None, stream=True,
                                          think=self.a.dusunme, options={'num_ctx': self.a.baglam},
                                          keep_alive='30m'):
                    if parca.message.content:
                        kutu['icerik'].append(parca.message.content)
                    for c in parca.message.tool_calls or []:
                        kutu['cagrilar'].append({'function': {'name': c.function.name,
                                                              'arguments': dict(c.function.arguments or {})}})
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
        return {'content': ''.join(kutu['icerik']), 'tool_calls': kutu['cagrilar']}
