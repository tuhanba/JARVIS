"""Create the JARVIS desktop shortcut (and optionally start with Windows).

    python kisayol_olustur.py              # desktop shortcut
    python kisayol_olustur.py --baslangic  # also start JARVIS when Windows starts
    python kisayol_olustur.py --kaldir     # remove both

The shortcut runs panel.pyw with pythonw.exe (signed by the Python Software
Foundation), so no console window opens and Smart App Control does not
block it the way it blocks downloaded .bat files."""
import os
import sys
from pathlib import Path

PROJE = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJE))


def ikon_olustur() -> Path:
    """Round JARVIS icon (multi-size .ico) from the project's jarvis.jpg."""
    from PIL import Image, ImageDraw
    hedef = PROJE / 'veri' / 'jarvis.ico'
    hedef.parent.mkdir(parents=True, exist_ok=True)
    resim = Image.open(PROJE / 'jarvis.jpg').convert('RGBA')
    kenar = min(resim.size)
    resim = resim.crop(((resim.width - kenar) // 2, (resim.height - kenar) // 2,
                        (resim.width + kenar) // 2, (resim.height + kenar) // 2)).resize((256, 256), Image.LANCZOS)
    maske = Image.new('L', (256, 256), 0)
    ImageDraw.Draw(maske).ellipse((6, 6, 250, 250), fill=255)
    resim.putalpha(maske)
    resim.save(hedef, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return hedef


def pythonw() -> str:
    aday = Path(sys.executable).with_name('pythonw.exe')
    return str(aday if aday.exists() else sys.executable)


def kisayol(yol: Path, ikon: Path) -> None:
    import win32com.client
    kabuk = win32com.client.Dispatch('WScript.Shell')
    k = kabuk.CreateShortCut(str(yol))
    k.TargetPath = pythonw()
    k.Arguments = f'"{PROJE / "panel.pyw"}"'
    k.WorkingDirectory = str(PROJE)
    k.IconLocation = str(ikon)
    k.Description = 'J.A.R.V.I.S. kişisel asistan'
    k.save()


def main() -> None:
    if sys.platform != 'win32':
        print('Kısayol yalnızca Windows için. Diğer sistemlerde: python panel.pyw')
        return
    from jarvis_core.yollar import bilinen_klasor
    masaustu = bilinen_klasor('masaüst') / 'JARVIS.lnk'
    baslangic = Path(os.environ['APPDATA']) / 'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup' / 'JARVIS.lnk'

    if '--kaldir' in sys.argv:
        for yol in (masaustu, baslangic):
            if yol.exists():
                yol.unlink()
                print(f'Kaldırıldı: {yol}')
        return

    ikon = ikon_olustur()
    kisayol(masaustu, ikon)
    print(f'Masaüstü kısayolu oluşturuldu: {masaustu}')
    if '--baslangic' in sys.argv:
        kisayol(baslangic, ikon)
        print(f'Windows açılışında başlayacak: {baslangic}')
    print('JARVIS\'i açmak için masaüstündeki JARVIS simgesine çift tıklayın.')


if __name__ == '__main__':
    main()
