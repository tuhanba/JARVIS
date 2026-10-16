"""Voice-side adapter over the task engine (jarvis_core). The AI runs only on
the local Ollama server; there is no cloud fallback."""
import json
import os
import re

import ses
from jarvis_core.llm import OllamaHatasi
from jarvis_core.motor import Motor

ESKI_HAFIZA = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hafiza.json')


def _seslendirilebilir(metin: str) -> str:
    """Strip markdown symbols and emoji, which TTS would read aloud."""
    metin = re.sub(r'[\U0001F000-\U0001FAFF☀-➿️‍]', '', metin)
    return re.sub(r' {2,}', ' ', re.sub(r'[*#`_]+', '', metin)).strip()


class Beyin:
    def __init__(self) -> None:
        self.motor = Motor(onay=ses.onayla, bildir=self._bildir)
        self.depo = self.motor.depo
        self._eski_hafizayi_tasi()
        try:
            self.model = self.motor.llm.hazirla()
            self.aktif = True
        except OllamaHatasi as e:
            self.model, self.aktif = None, False
            print(f'Yapay zeka kapalı: {e}')

    @property
    def ad(self) -> str:
        return f'Ollama ({self.model})' if self.aktif else 'yok'

    def _eski_hafizayi_tasi(self) -> None:
        """One-time move of the old hafiza.json into the SQLite memory."""
        if not os.path.exists(ESKI_HAFIZA):
            return
        try:
            with open(ESKI_HAFIZA, encoding='utf-8') as f:
                for metin in json.load(f):
                    self.depo.hafiza_ekle(metin, kaynak='eski hafiza.json')
            os.replace(ESKI_HAFIZA, ESKI_HAFIZA + '.tasindi')
        except (OSError, ValueError):
            pass

    @staticmethod
    def _bildir(olay: str, veri: dict) -> None:
        if olay == 'arac':
            print(f'  [araç] {veri["arac"]}({json.dumps(veri["argumanlar"], ensure_ascii=False)[:120]})')
        elif olay == 'arac_sonuc' and not veri['basarili']:
            print(f'  [araç hatası] {veri["cikti"][:160]}')

    def sor(self, metin: str) -> str:
        if not self.aktif:
            return 'Yapay zeka kapalı efendim. Ollama uygulamasını açıp beni yeniden başlatın.'
        return _seslendirilebilir(self.motor.calistir(metin).cevap)

    def hizli(self, metin: str, niyet) -> str:
        """A fast command, run by the same executor (policy, approval, audit) as the model."""
        return _seslendirilebilir(self.motor.hizli_calistir(metin, niyet).cevap)

    def iptal(self) -> None:
        self.motor.iptal_et()
