"""Tool definition, registry and the execution context handed to tools."""
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import jsonschema


# No console window flashing up for child processes when running windowless (pythonw).
PENCERESIZ = 0x08000000 if sys.platform == 'win32' else 0


class Iptal(Exception):
    """Raised inside tools when the user cancels the task."""


class IptalJetonu:
    """Per task / per call cancellation. A child is cancelled when its parent is,
    so a global stop reaches every running call, while starting a new task never
    clears another task's token (the old engine shared one Event and cleared it)."""

    def __init__(self, ebeveyn: 'IptalJetonu' = None, sebep: str = '') -> None:
        self._olay = threading.Event()
        self.ebeveyn = ebeveyn
        self.sebep = sebep

    def set(self, sebep: str = 'iptal') -> None:
        self.sebep = self.sebep or sebep
        self._olay.set()

    def is_set(self) -> bool:
        return self._olay.is_set() or bool(self.ebeveyn and self.ebeveyn.is_set())

    def cocuk(self) -> 'IptalJetonu':
        return IptalJetonu(self)

    def wait(self, sure: float) -> bool:
        bitis = time.monotonic() + sure
        while time.monotonic() < bitis:
            if self.is_set():
                return True
            time.sleep(min(0.05, max(0.0, bitis - time.monotonic())))
        return self.is_set()


# ToolResult states. "succeeded" = the operation reported success; "verified" = the
# intended end state was observed independently (file hash, window, process...).
DOGRULANDI, BASARILI, KISMI, BASARISIZ, IPTAL_EDILDI, BELIRSIZ = (
    'verified', 'succeeded', 'partial', 'failed', 'cancelled', 'unknown_effect')


@dataclass
class Sonuc:
    basarili: bool
    cikti: str
    # True: the effect was observed (file exists, window open...). False: it was not.
    # None: nothing verified (read-only tool, or nothing observable).
    dogrulandi: Optional[bool] = None
    veri: dict = field(default_factory=dict)
    # How to reverse this action: {'tur': ..., ...}
    geri_al: Optional[dict] = None
    # Explicit state; derived from basarili/dogrulandi when not given.
    durum: str = ''
    # Error category for the record and the UI: 'bulunamadi', 'izin', 'disk', 'zaman_asimi', ...
    hata_turu: str = ''

    def __post_init__(self):
        if not self.durum:
            if not self.basarili:
                self.durum = BASARISIZ
            else:
                self.durum = DOGRULANDI if self.dogrulandi is True else BASARILI


class _SurecSahibi:
    """Owns every child process a tool starts, so cancel/timeout can end the whole
    tree (children and grandchildren) and nothing else.

    POSIX: each child leads its own process group; the group is killed.
    Windows: each child is put in a Job Object with KILL_ON_JOB_CLOSE; closing the
    job ends the tree. A Job Object is process-lifetime control, not a file or
    network sandbox."""

    def __init__(self) -> None:
        self.surecler = []
        self.isler = []
        self._kilit = threading.Lock()

    def baslat(self, argv, **k) -> subprocess.Popen:
        if sys.platform == 'win32':
            k['creationflags'] = k.get('creationflags', 0) | PENCERESIZ | 0x00000200  # NEW_PROCESS_GROUP
        else:
            k['start_new_session'] = True
        p = subprocess.Popen(argv, **k)
        with self._kilit:
            self.surecler.append(p)
            if sys.platform == 'win32':
                is_ = _windows_is_nesnesi(p)
                if is_:
                    self.isler.append(is_)
        return p

    def hepsini_sonlandir(self) -> None:
        with self._kilit:
            surecler, isler = list(self.surecler), list(self.isler)
        for is_ in isler:
            _windows_is_kapat(is_)
        for p in surecler:
            if p.poll() is None or sys.platform != 'win32':
                _agaci_oldur(p)


def _agaci_oldur(p: subprocess.Popen) -> None:
    try:
        import psutil
        try:
            cocuklar = psutil.Process(p.pid).children(recursive=True)
        except psutil.Error:
            cocuklar = []
    except ImportError:
        psutil, cocuklar = None, []
    if sys.platform != 'win32':
        import signal
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    for c in cocuklar:
        try:
            c.kill()
        except Exception:
            pass
    try:
        p.kill()
    except OSError:
        pass


def _windows_is_nesnesi(p: subprocess.Popen):
    """Create a kill-on-close Job Object and put the process in it (best effort)."""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(n, ctypes.c_ulonglong) for n in ('ReadOperationCount', 'WriteOperationCount',
                                                          'OtherOperationCount', 'ReadTransferCount',
                                                          'WriteTransferCount', 'OtherTransferCount')]

        class BASIC(ctypes.Structure):
            _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64),
                        ('LimitFlags', wintypes.DWORD), ('MinimumWorkingSetSize', ctypes.c_size_t),
                        ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', wintypes.DWORD),
                        ('Affinity', ctypes.c_size_t), ('PriorityClass', wintypes.DWORD),
                        ('SchedulingClass', wintypes.DWORD)]

        class EXTENDED(ctypes.Structure):
            _fields_ = [('BasicLimitInformation', BASIC), ('IoInfo', IO_COUNTERS),
                        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]

        k32.CreateJobObjectW.restype = wintypes.HANDLE
        is_ = k32.CreateJobObjectW(None, None)
        if not is_:
            return None
        bilgi = EXTENDED()
        bilgi.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        k32.SetInformationJobObject(is_, 9, ctypes.byref(bilgi), ctypes.sizeof(bilgi))
        if not k32.AssignProcessToJobObject(is_, wintypes.HANDLE(int(p._handle))):
            k32.CloseHandle(is_)
            return None
        return is_
    except Exception:
        return None


def _windows_is_kapat(is_) -> None:
    try:
        import ctypes
        k32 = ctypes.WinDLL('kernel32')
        k32.TerminateJobObject(is_, 1)
        k32.CloseHandle(is_)
    except Exception:
        pass


class Baglam:
    """Passed to every tool: cancellation, owned subprocesses, store and policy."""

    def __init__(self, iptal, depo=None, izinler=None, kaynak: str = 'model', son_tarih: float = None) -> None:
        self.iptal = iptal               # anything with is_set(): IptalJetonu or threading.Event
        self.depo = depo
        self.izinler = izinler
        self.kaynak = kaynak             # who asked: 'model' (LLM tool call) or 'hizli' (user's fast command)
        self.son_tarih = son_tarih       # time.monotonic() deadline for this call
        self.surecler = _SurecSahibi()

    def kontrol(self) -> None:
        if self.iptal.is_set():
            raise Iptal()

    def kalan_sure(self, varsayilan: float) -> float:
        if self.son_tarih is None:
            return varsayilan
        return max(0.0, min(varsayilan, self.son_tarih - time.monotonic()))

    def surec(self, argv: list, zaman_asimi: float = 120, cwd=None, env=None) -> subprocess.CompletedProcess:
        """Run a program (never through a shell); kill its whole tree on cancel or timeout."""
        zaman_asimi = self.kalan_sure(zaman_asimi)
        p = self.surecler.baslat(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, env=env,
                                 text=True, encoding='utf-8', errors='replace')
        bitis = time.monotonic() + zaman_asimi
        while True:
            try:
                cikti, hata = p.communicate(timeout=0.2)
                return subprocess.CompletedProcess(argv, p.returncode, cikti, hata)
            except subprocess.TimeoutExpired:
                if self.iptal.is_set() or time.monotonic() >= bitis:
                    self.surecler.hepsini_sonlandir()
                    try:
                        p.communicate(timeout=5)
                    except (subprocess.TimeoutExpired, ValueError, OSError):
                        pass
                    if self.iptal.is_set():
                        raise Iptal()
                    raise TimeoutError(f'{argv[0]} {zaman_asimi:.0f} saniyede bitmedi')

    def sonlandir(self) -> None:
        """Called by the executor on cancel / timeout: end every owned process tree."""
        self.surecler.hepsini_sonlandir()


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
    # Arguments that identify the goal ("write file X"); a later success with the same
    # goal resolves an earlier failure. Empty = every argument.
    amac_argumanlari: tuple = ()
    # Repeating the same call is a new, legitimate action (volume up twice, type twice).
    tekrarlanabilir: bool = False
    # Shown to the model. Fast-command-only tools (power, hotkeys) are not.
    modele_acik: bool = True
    surum: str = '1'

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
