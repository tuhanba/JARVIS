"""Tool definition, registry and the execution context handed to tools."""
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Callable, Optional

import jsonschema


class Iptal(Exception):
    """Raised inside tools when the user cancels the task."""


@dataclass
class Sonuc:
    basarili: bool
    cikti: str
    # True: the effect was observed (file exists, window open...). False: it was not.
    # None: nothing to verify (read-only tool).
    dogrulandi: Optional[bool] = None
    veri: dict = field(default_factory=dict)
    # How to reverse this action: {'arac': name, 'argumanlar': {...}}
    geri_al: Optional[dict] = None


class Baglam:
    """Passed to every tool: cancellation and cancellable subprocesses."""

    def __init__(self, iptal: threading.Event, depo=None, izinler=None) -> None:
        self.iptal = iptal
        self.depo = depo
        self.izinler = izinler

    def kontrol(self) -> None:
        if self.iptal.is_set():
            raise Iptal()

    def surec(self, argv: list, zaman_asimi: float = 120, cwd=None) -> subprocess.CompletedProcess:
        """Run a program (never through a shell); kill it on cancel or timeout."""
        p = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd,
                             text=True, encoding='utf-8', errors='replace')
        bekleme = 0.0
        while True:
            try:
                cikti, hata = p.communicate(timeout=0.2)
                return subprocess.CompletedProcess(argv, p.returncode, cikti, hata)
            except subprocess.TimeoutExpired:
                bekleme += 0.2
                if self.iptal.is_set() or bekleme >= zaman_asimi:
                    p.kill()
                    p.communicate()
                    if self.iptal.is_set():
                        raise Iptal()
                    raise TimeoutError(f'{argv[0]} {zaman_asimi:.0f} saniyede bitmedi')


@dataclass
class Arac:
    ad: str
    aciklama: str
    parametreler: dict
    calistir: Callable[..., Sonuc]
    risk: str
    yan_etki: bool
    yol_argumanlari: tuple = ()
    zaman_asimi: float = 60
    # For crash recovery: has this exact call already taken effect?
    zaten_yapildi: Optional[Callable[[dict], bool]] = None
    # Output comes from outside (web pages, files): it is data, never instructions.
    guvenilmez_cikti: bool = False

    def sema(self) -> dict:
        return {'type': 'function', 'function': {
            'name': self.ad, 'description': self.aciklama, 'parameters': self.parametreler}}

    def dogrula(self, argumanlar: dict) -> None:
        jsonschema.validate(argumanlar, self.parametreler)


KAYIT: dict = {}


def arac(ad: str, aciklama: str, ozellikler: dict, gerekli: list, risk: str, yan_etki: bool, **ek):
    """Decorator that registers a tool with a strict JSON schema."""
    def sar(fonksiyon):
        KAYIT[ad] = Arac(ad=ad, aciklama=aciklama, calistir=fonksiyon, risk=risk, yan_etki=yan_etki,
                         parametreler={'type': 'object', 'properties': ozellikler, 'required': gerekli,
                                       'additionalProperties': False}, **ek)
        return fonksiyon
    return sar


def yollar_yardim(klasor: str):
    if not klasor:
        return None
    from .. import yollar
    return str(yollar.coz(klasor))


def metin(aciklama: str, **ek) -> dict:
    return {'type': 'string', 'description': aciklama, **ek}
