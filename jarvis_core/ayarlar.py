"""Settings, read from the environment / .env. Everything is overridable."""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

PROJE = Path(__file__).resolve().parent.parent


def _int(ad: str, varsayilan: int) -> int:
    try:
        return int(os.getenv(ad, varsayilan))
    except ValueError:
        return varsayilan


@dataclass
class Ayarlar:
    ollama_adres: str = field(default_factory=lambda: os.getenv('OLLAMA_ADRES', 'http://127.0.0.1:11434'))
    # Model per job. Empty = use the general model.
    model_genel: str = field(default_factory=lambda: os.getenv('OLLAMA_MODEL', 'qwen3.5:9b'))
    model_kod: str = field(default_factory=lambda: os.getenv('OLLAMA_MODEL_KOD', ''))
    model_gorsel: str = field(default_factory=lambda: os.getenv('OLLAMA_MODEL_GORSEL', ''))
    tek_model: bool = field(default_factory=lambda: os.getenv('OLLAMA_TEK_MODEL', '1') == '1')
    baglam: int = field(default_factory=lambda: _int('OLLAMA_BAGLAM', 16384))
    dusunme: bool = field(default_factory=lambda: os.getenv('YZ_DUSUNME', '0') == '1')
    llm_zaman_asimi: int = field(default_factory=lambda: _int('OLLAMA_ZAMAN_ASIMI', 300))
    # Task budgets
    max_adim: int = field(default_factory=lambda: _int('GOREV_MAX_ADIM', 20))
    max_sure: int = field(default_factory=lambda: _int('GOREV_MAX_SURE', 900))
    tekrar_siniri: int = field(default_factory=lambda: _int('GOREV_TEKRAR_SINIRI', 3))
    veri_dizini: Path = field(default_factory=lambda: Path(os.getenv('JARVIS_VERI', PROJE / 'veri')))

    # Share of num_ctx the prompt may use before old tool outputs are shortened.
    baglam_payi: float = field(default_factory=lambda: float(os.getenv('JARVIS_BAGLAM_PAYI', '0.7')))

    def model(self, is_turu: str = 'genel') -> str:
        return {'kod': self.model_kod, 'gorsel': self.model_gorsel}.get(is_turu) or self.model_genel

    @staticmethod
    def is_turu(istek: str) -> str:
        """'kod' for programming requests (routed to OLLAMA_MODEL_KOD when set), else 'genel'."""
        k = (istek or '').replace('İ', 'i').lower()
        if re.search(r'\b(kod|kodu|kodla|program yaz|script|betik|fonksiyon|python|javascript|typescript|html|css|'
                     r'react|hata ayıkla|debug|derle|unit test|birim test|regex|sql|api yaz|site yap|web sitesi)', k):
            return 'kod'
        return 'genel'

    @property
    def veritabani(self) -> Path:
        self.veri_dizini.mkdir(parents=True, exist_ok=True)
        return self.veri_dizini / 'jarvis.db'
