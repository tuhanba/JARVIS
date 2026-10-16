"""Download files (with progress, cancel and size/disk checks) and open files.

A download is reported as verified only when the bytes on disk match the
size the server announced (or, without a size, when the file is non-empty)."""
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

from .. import yollar
from ..izinler import SISTEM, YAZMA
from .dosyalar import _disk_hatasi
from .temel import Iptal, Sonuc, arac, metin

# Opening these runs code; they always need an explicit yes.
CALISTIRILABILIR = {'.exe', '.msi', '.msix', '.appx', '.bat', '.cmd', '.ps1', '.psm1', '.vbs', '.vbe', '.js', '.jse',
                    '.wsf', '.wsh', '.scr', '.com', '.pif', '.lnk', '.hta', '.reg', '.jar', '.cpl', '.msc', '.dll', '.sys',
                    '.iso', '.img', '.vhd', '.vhdx', '.application', '.appref-ms', '.url', '.scf', '.inf'}


def _dosya_adi(yanit, adres: str, verilen: str) -> str:
    if verilen:
        ad = verilen
    else:
        cd = yanit.headers.get('Content-Disposition', '')
        m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(r'filename="?([^";]+)"?', cd)
        ad = unquote(m.group(1)) if m else unquote(Path(urlparse(adres).path).name) or 'indirilen_dosya'
    ad = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', ad).strip(' .') or 'indirilen_dosya'
    return ad[:150]


def _bos_ad(klasor: Path, ad: str) -> Path:
    hedef = klasor / ad
    sayi = 1
    while hedef.exists():
        hedef = klasor / f'{Path(ad).stem} ({sayi}){Path(ad).suffix}'
        sayi += 1
    return hedef


@arac('dosya_indir', 'Bir bağlantıdaki dosyayı indirir (ilerlemeyi gösterir, iptal edilebilir) ve indirilen boyutu '
      'sunucunun bildirdiğiyle karşılaştırarak doğrular. Var olan dosyanın üzerine yazmaz.',
      {'adres': metin('İndirme bağlantısı (http/https)', pattern='^https?://'),
       'klasor': metin('Kaydedilecek klasör (varsayılan "İndirilenler")'),
       'ad': metin('İsteğe bağlı dosya adı')},
      ['adres'], risk=YAZMA, yan_etki=True, yol_argumanlari=('klasor',), zaman_asimi=7200)
def dosya_indir(baglam, adres, klasor='İndirilenler', ad=''):
    import requests
    hedef_klasor = yollar.coz(klasor or 'İndirilenler')
    sinir = int(os.getenv('JARVIS_MAX_INDIRME_MB', '4096')) * 2**20
    try:
        hedef_klasor.mkdir(parents=True, exist_ok=True)
        yanit = requests.get(adres, stream=True, timeout=(15, 60), headers={'User-Agent': 'Mozilla/5.0 JARVIS'})
    except requests.RequestException as e:
        return Sonuc(False, f'Bağlantı kurulamadı (internet?): {e}', dogrulandi=False)
    except OSError as e:
        return _disk_hatasi(e)
    with yanit:
        if yanit.status_code != 200:
            return Sonuc(False, f'Sunucu {yanit.status_code} döndürdü; dosya indirilemedi.', dogrulandi=False)
        toplam = int(yanit.headers.get('Content-Length') or 0)
        if toplam > sinir:
            return Sonuc(False, f'Dosya {toplam / 2**20:.0f} MB; sınır {sinir // 2**20} MB (JARVIS_MAX_INDIRME_MB).',
                         dogrulandi=False)
        bos = shutil.disk_usage(str(hedef_klasor)).free
        if toplam and toplam > bos - 200 * 2**20:
            return Sonuc(False, f'Disk dolu: {toplam / 2**20:.0f} MB gerekiyor, {bos / 2**20:.0f} MB boş.', dogrulandi=False)
        hedef = _bos_ad(hedef_klasor, _dosya_adi(yanit, adres, ad))
        gecici = hedef.with_name(hedef.name + '.indiriliyor')
        ozet, inen, son = hashlib.sha256(), 0, 0.0
        try:
            with open(gecici, 'wb') as f:
                for parca in yanit.iter_content(1 << 16):
                    baglam.kontrol()
                    f.write(parca)
                    ozet.update(parca)
                    inen += len(parca)
                    if inen > sinir:
                        raise ValueError('boyut sınırı aşıldı')
                    if time.time() - son > 0.5:
                        son = time.time()
                        baglam.ilerleme(f'%{100 * inen // toplam} · {inen / 2**20:.1f}/{toplam / 2**20:.1f} MB'
                                        if toplam else f'{inen / 2**20:.1f} MB')
        except Iptal:
            gecici.unlink(missing_ok=True)
            raise
        except OSError as e:
            gecici.unlink(missing_ok=True)
            return _disk_hatasi(e)
        except Exception as e:
            gecici.unlink(missing_ok=True)
            return Sonuc(False, f'İndirme yarıda kaldı: {e}', dogrulandi=False)
    gecici.replace(hedef)
    boyut = hedef.stat().st_size
    dogru = boyut == toplam if toplam else boyut > 0
    durum = 'boyut doğrulandı' if toplam and dogru else ('sunucu boyut bildirmedi' if not toplam else
                                                          f'BOYUT TUTMUYOR (beklenen {toplam}, inen {boyut})')
    return Sonuc(dogru, f'İndirildi: {hedef} ({boyut / 2**20:.2f} MB, {durum}, sha256 {ozet.hexdigest()[:16]}…)',
                 dogrulandi=dogru, veri={'yol': str(hedef), 'boyut': boyut, 'sha256': ozet.hexdigest()},
                 geri_al={'tur': 'cop_kutusuna', 'yol': str(hedef)})


def _acma_riski(argumanlar: dict) -> str:
    return SISTEM if Path(str(argumanlar.get('yol', ''))).suffix.lower() in CALISTIRILABILIR else YAZMA


@arac('dosya_ac', 'Bir dosyayı varsayılan programıyla açar (PDF, belge, resim, video...). Program/kurulum '
      'dosyaları (.exe, .msi, .bat...) her seferinde kullanıcı onayı ister.',
      {'yol': metin('Açılacak dosyanın yolu')}, ['yol'],
      risk=YAZMA, yan_etki=True, yol_argumanlari=('yol',), zaman_asimi=30, risk_belirle=_acma_riski)
def dosya_ac(baglam, yol):
    p = yollar.coz(yol)
    if not p.exists():
        return Sonuc(False, f'Dosya bulunamadı: {p}', dogrulandi=False)
    try:
        if sys.platform == 'win32':
            os.startfile(str(p))
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', str(p)])
        else:
            subprocess.Popen(['xdg-open', str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        return Sonuc(False, f'{p.name} açılamadı: {e}', dogrulandi=False)
    if sys.platform != 'win32':
        return Sonuc(True, f'{p.name} açılması istendi (bu sistemde pencere doğrulanamıyor).', dogrulandi=None)
    from .uygulamalar import pencere_basliklari
    bitis = time.time() + 12
    while time.time() < bitis:
        baglam.kontrol()
        if any(p.stem.lower() in t.lower() for t in pencere_basliklari()):
            return Sonuc(True, f'{p.name} açıldı.', dogrulandi=True)
        time.sleep(0.5)
    return Sonuc(True, f'{p.name} açılması istendi ama başlığında dosya adı geçen bir pencere görmedim.', dogrulandi=None)
