"""Settings, read from the environment / .env. Everything is overridable."""
import os
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
    # How long Ollama keeps the model in memory after the last request ('5m', '30m', '0').
    model_bekleme: str = field(default_factory=lambda: os.getenv('OLLAMA_MODEL_BEKLEME', '30m'))
    llm_zaman_asimi: int = field(default_factory=lambda: _int('OLLAMA_ZAMAN_ASIMI', 300))
    # Task budgets
    max_adim: int = field(default_factory=lambda: _int('GOREV_MAX_ADIM', 20))
    max_sure: int = field(default_factory=lambda: _int('GOREV_MAX_SURE', 900))
    tekrar_siniri: int = field(default_factory=lambda: _int('GOREV_TEKRAR_SINIRI', 3))
    veri_dizini: Path = field(default_factory=lambda: Path(os.getenv('JARVIS_VERI', PROJE / 'veri')))

    def model(self, is_turu: str = 'genel') -> str:
        return {'kod': self.model_kod, 'gorsel': self.model_gorsel}.get(is_turu) or self.model_genel

    @property
    def veritabani(self) -> Path:
        self.veri_dizini.mkdir(parents=True, exist_ok=True)
        return self.veri_dizini / 'jarvis.db'
