"""Provider contracts. Audio is mono int16 numpy arrays with an explicit sample rate."""
from typing import Optional, Protocol, Tuple

import numpy as np


class STTSaglayici(Protocol):
    ad: str
    yerel: bool              # False = audio leaves the computer

    def tanimla(self, ses: np.ndarray, ornek_hizi: int) -> str:
        """Speech to text (Turkish). Empty string when nothing was understood."""


class TTSSaglayici(Protocol):
    ad: str
    yerel: bool
    turkce: bool             # a real Turkish voice (not an English voice reading Turkish)

    def sentezle(self, metin: str) -> Tuple[np.ndarray, int]:
        """Text to audio (int16 samples, sample rate)."""


class UyandirmaSaglayici(Protocol):
    ad: str

    def isle(self, parca: np.ndarray) -> Optional[float]:
        """Feed 16 kHz int16 frames; returns a score when the wake word was heard."""


def int16(ses) -> np.ndarray:
    a = np.asarray(ses)
    if a.dtype == np.int16:
        return a
    if np.issubdtype(a.dtype, np.floating):
        return (np.clip(a, -1.0, 1.0) * 32767).astype(np.int16)
    return a.astype(np.int16)


def yeniden_ornekle(ses: np.ndarray, kaynak_hz: int, hedef_hz: int) -> np.ndarray:
    """Linear resampling (enough for speech recognition input)."""
    if kaynak_hz == hedef_hz or len(ses) == 0:
        return ses
    sure = len(ses) / kaynak_hz
    hedef = np.linspace(0, len(ses) - 1, int(round(sure * hedef_hz)))
    return np.interp(hedef, np.arange(len(ses)), ses.astype(np.float32)).astype(ses.dtype)
