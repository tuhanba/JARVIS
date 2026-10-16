import sys
from pathlib import Path

import pytest

PROJE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJE))


@pytest.fixture
def ev(tmp_path, monkeypatch):
    """Fake home with the usual folders; JARVIS data goes to a temp dir too."""
    ev = tmp_path / 'ev'
    for ad in ('Desktop', 'Documents', 'Downloads', 'Pictures', 'Music', 'Videos'):
        (ev / ad).mkdir(parents=True)
    monkeypatch.setenv('HOME', str(ev))
    monkeypatch.setenv('USERPROFILE', str(ev))
    monkeypatch.setenv('JARVIS_VERI', str(tmp_path / 'veri'))
    monkeypatch.setattr(Path, 'home', classmethod(lambda cls: ev))
    # On Windows the known-folder API would return the real Documents folder.
    from jarvis_core import yollar
    monkeypatch.setattr(yollar, '_windows_bilinen', lambda guid: None)
    return ev


class SahteLLM:
    """Scripted model: each entry is either a list of tool calls or a final text."""

    def __init__(self, senaryo):
        self.senaryo = list(senaryo)
        self.gorulen = []

    def sohbet(self, mesajlar, araclar, iptal, is_turu='genel'):
        self.gorulen.append([dict(m) for m in mesajlar])
        adim = self.senaryo.pop(0) if self.senaryo else 'Bitti.'
        if callable(adim):
            adim = adim(mesajlar)
        if isinstance(adim, str):
            return {'content': adim, 'tool_calls': []}
        return {'content': '', 'tool_calls': [{'function': {'name': ad, 'arguments': arg}} for ad, arg in adim]}


@pytest.fixture
def motor_yap(ev):
    from jarvis_core.motor import Motor
    from jarvis_core.ayarlar import Ayarlar

    def yap(senaryo, onay=lambda soru: False, **ayar):
        a = Ayarlar()
        for k, v in ayar.items():
            setattr(a, k, v)
        sorular = []

        def onay_kaydet(soru):
            sorular.append(soru)
            return onay(soru)
        m = Motor(ayarlar=a, llm=SahteLLM(senaryo), onay=onay_kaydet)
        m.sorular = sorular
        return m
    return yap
