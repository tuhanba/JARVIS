"""Voice activity and end-of-turn detection on a frame stream.

Energy-based with an adaptive noise floor: robust enough for push-to-talk and
wake-word follow-up, no extra dependency. Keeps a short pre-roll so the first
syllable is not cut, ends a turn after `sessizlik_ms` of quiet, and bounds
every buffer (pre-roll and maximum utterance length) so a noisy room cannot
grow memory without limit."""
from collections import deque
from dataclasses import dataclass, field

import numpy as np


def enerji_db(cerceve: np.ndarray) -> float:
    if len(cerceve) == 0:
        return -120.0
    rms = np.sqrt(np.mean(np.square(cerceve.astype(np.float64)))) / 32768.0
    return 20 * np.log10(max(rms, 1e-6))


@dataclass
class SiraAlgilayici:
    ornek_hizi: int = 16000
    cerceve_ms: int = 30
    esik_db: float = 12.0          # speech = this many dB above the noise floor
    min_konusma_ms: int = 240      # shorter bursts (a click, a cough) are ignored
    sessizlik_ms: int = 700        # quiet this long ends the turn
    on_kayit_ms: int = 300         # audio kept from before speech started
    azami_sure_s: float = 20.0     # hard cap on one utterance
    gurultu_db: float = -60.0
    _on: deque = field(default=None, repr=False)
    _konusma: list = field(default_factory=list, repr=False)
    _konusma_ms: int = 0
    _sessiz_ms: int = 0
    _aktif: bool = False

    def __post_init__(self):
        self._on = deque(maxlen=max(1, self.on_kayit_ms // self.cerceve_ms))

    @property
    def cerceve_boyu(self) -> int:
        return self.ornek_hizi * self.cerceve_ms // 1000

    def sifirla(self) -> None:
        self._on.clear()
        self._konusma, self._konusma_ms, self._sessiz_ms, self._aktif = [], 0, 0, False

    @property
    def konusuyor(self) -> bool:
        return self._aktif and self._konusma_ms >= self.min_konusma_ms

    def isle(self, cerceve: np.ndarray):
        """Feed one frame. Returns the finished utterance (int16 array) or None."""
        db = enerji_db(cerceve)
        ses_var = db > self.gurultu_db + self.esik_db
        if not self._aktif:
            # adapt the noise floor only while nobody speaks
            self.gurultu_db = 0.95 * self.gurultu_db + 0.05 * db if not ses_var else self.gurultu_db
            self._on.append(cerceve)
            if ses_var:
                self._aktif = True
                self._konusma = list(self._on)
                self._konusma_ms = self.cerceve_ms
                self._sessiz_ms = 0
            return None
        self._konusma.append(cerceve)
        if ses_var:
            self._konusma_ms += self.cerceve_ms
            self._sessiz_ms = 0
        else:
            self._sessiz_ms += self.cerceve_ms
        toplam_ms = len(self._konusma) * self.cerceve_ms
        if self._sessiz_ms >= self.sessizlik_ms or toplam_ms >= self.azami_sure_s * 1000:
            bitti = self._konusma_ms >= self.min_konusma_ms
            parca = np.concatenate(self._konusma) if bitti else None
            self.sifirla()
            return parca
        return None
