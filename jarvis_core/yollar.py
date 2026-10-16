"""Resolve spoken folder names ('Belgeler', 'masaüstü') to real paths,
including Windows known folders that live under OneDrive."""
import os
import re
import sys
from pathlib import Path

# spoken stem -> (Windows known-folder GUID, fallback folder name)
BILINEN = {
    'masaüst': ('{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}', 'Desktop'),
    'belge': ('{FDD39AD0-238F-46AF-ADB4-6C85480369C7}', 'Documents'),
    'indir': ('{374DE290-123F-4565-9164-39C4925E467B}', 'Downloads'),
    'resim': ('{33E28130-4E1E-4676-835A-98395C3BC3BB}', 'Pictures'),
    'müzik': ('{4BD8D571-6D19-48D3-BE97-422220080E43}', 'Music'),
    'video': ('{18989B1D-99B5-455B-841C-AB7C74E4DDFC}', 'Videos'),
}
INGILIZCE = {'desktop': 'masaüst', 'documents': 'belge', 'downloads': 'indir',
             'pictures': 'resim', 'music': 'müzik', 'videos': 'video'}


def _windows_bilinen(guid: str):
    try:
        import ctypes
        from ctypes import wintypes
        import uuid

        class GUID(ctypes.Structure):
            _fields_ = [('Data1', wintypes.DWORD), ('Data2', wintypes.WORD),
                        ('Data3', wintypes.WORD), ('Data4', wintypes.BYTE * 8)]
        u = uuid.UUID(guid)
        g = GUID(u.time_low, u.time_mid, u.time_hi_version,
                 (wintypes.BYTE * 8).from_buffer_copy(u.bytes[8:]))
        yol = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(yol)) == 0:
            sonuc = yol.value
            ctypes.windll.ole32.CoTaskMemFree(yol)
            return Path(sonuc)
    except Exception:
        return None
    return None


def bilinen_klasor(kok: str) -> Path:
    guid, ad = BILINEN[kok]
    if sys.platform == 'win32':
        yol = _windows_bilinen(guid)
        if yol:
            return yol
    ev = Path.home()
    if not (ev / ad).exists() and (ev / 'OneDrive' / ad).exists():
        return ev / 'OneDrive' / ad
    return ev / ad


def coz(yol: str) -> Path:
    """'Belgeler/rapor.txt' -> C:\\Users\\x\\Documents\\rapor.txt; real paths pass through."""
    yol = (yol or '').strip().strip('"\'')
    parcalar = re.split(r'[\\/]', yol, maxsplit=1)
    ilk = parcalar[0].replace('İ', 'i').lower().rstrip("'’")
    ilk = re.sub(r"['’].*$", '', ilk)
    ilk = INGILIZCE.get(ilk, ilk)
    kalan = parcalar[1] if len(parcalar) > 1 else ''
    for kok in BILINEN:
        if ilk.startswith(kok):
            taban = bilinen_klasor(kok)
            return taban / kalan if kalan else taban
    if ilk in ('ev', 'home', '~'):
        return Path.home() / kalan
    return Path(os.path.expandvars(os.path.expanduser(yol))).resolve()


def guvenli_kokler() -> list:
    """Folders where routine writes are allowed without asking (by default)."""
    kokler = [bilinen_klasor(k) for k in ('masaüst', 'belge', 'indir', 'resim', 'müzik', 'video')]
    from .ayarlar import Ayarlar
    kokler.append(Ayarlar().veri_dizini / 'calisma')
    return [k.resolve() for k in kokler]


def icinde_mi(yol: Path, kok: Path) -> bool:
    try:
        Path(yol).resolve().relative_to(Path(kok).resolve())
        return True
    except ValueError:
        return False
