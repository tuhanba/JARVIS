"""File tools. Every change is verified on disk afterwards and records how
to undo it; overwrites keep a backup copy first."""
import errno
import hashlib
import os
import shutil
import time
from pathlib import Path

from .. import yollar
from ..ayarlar import Ayarlar
from ..izinler import OKUMA, SILME, YAZMA
from .temel import Sonuc, arac, metin

ATLA = {'appdata', 'node_modules', '.git', '__pycache__', '$recycle.bin', 'windows', 'program files',
        'program files (x86)', 'programdata', '.venv', 'venv'}


def _ozet(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, 'rb') as f:
        for parca in iter(lambda: f.read(1 << 20), b''):
            h.update(parca)
    return h.hexdigest()


def _disk_hatasi(e: OSError) -> Sonuc:
    if e.errno == errno.ENOSPC:
        return Sonuc(False, 'Disk dolu: işlem yapılamadı. Biraz yer açıp tekrar deneyin.', dogrulandi=False)
    if isinstance(e, PermissionError):
        return Sonuc(False, f'Erişim reddedildi: {e.filename}. Dosya açık olabilir veya yetki gerekebilir.',
                     dogrulandi=False)
    return Sonuc(False, f'Dosya hatası: {e}', dogrulandi=False)


def _yedekle(yol: Path) -> Path:
    yedek_dizini = Ayarlar().veri_dizini / 'yedek'
    yedek_dizini.mkdir(parents=True, exist_ok=True)
    yedek = yedek_dizini / f'{time.strftime("%Y%m%d_%H%M%S")}_{yol.name}'
    shutil.copy2(yol, yedek)
    return yedek


# ------------------------------------------------------------------ read

@arac('dosya_ara', 'Adında verilen metin geçen dosyaları alt klasörler dahil arar.',
      {'ad': metin('Dosya adının bir parçası, ör. "rapor" veya ".pdf"'),
       'klasor': metin('Aramanın başlayacağı klasör: "Belgeler", "Masaüstü", "İndirilenler", "ev" veya tam yol')},
      ['ad', 'klasor'], risk=OKUMA, yan_etki=False, zaman_asimi=60)
def dosya_ara(baglam, ad, klasor):
    kok = yollar.coz(klasor or 'ev')
    if not kok.is_dir():
        return Sonuc(False, f'Klasör bulunamadı: {kok}')
    bulunan, aranan = [], ad.lower()
    for dizin, altlar, dosyalar in os.walk(kok):
        baglam.kontrol()
        altlar[:] = [a for a in altlar if a.lower() not in ATLA and not a.startswith('.')]
        bulunan += [str(Path(dizin) / d) for d in dosyalar if aranan in d.lower()]
        if len(bulunan) >= 30:
            break
    if not bulunan:
        return Sonuc(True, f'{kok} içinde "{ad}" geçen dosya yok.', veri={'dosyalar': []})
    return Sonuc(True, '\n'.join(bulunan[:30]), veri={'dosyalar': bulunan[:30]})


@arac('klasor_listele', 'Bir klasördeki dosya ve klasörleri boyut ve tarihleriyle listeler.',
      {'klasor': metin('"Belgeler", "Masaüstü", "İndirilenler" gibi bir ad veya tam yol')},
      ['klasor'], risk=OKUMA, yan_etki=False)
def klasor_listele(baglam, klasor):
    yol = yollar.coz(klasor)
    if not yol.is_dir():
        return Sonuc(False, f'Klasör bulunamadı: {yol}')
    ogeler = sorted(yol.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    satirlar = []
    for p in ogeler[:100]:
        try:
            st = p.stat()
            tarih = time.strftime('%d.%m.%Y %H:%M', time.localtime(st.st_mtime))
            satirlar.append(f'{p.name}/' if p.is_dir() else f'{p.name}  ({st.st_size // 1024} KB, {tarih})')
        except OSError:
            satirlar.append(p.name)
    ek = f'\n... ve {len(ogeler) - 100} öğe daha' if len(ogeler) > 100 else ''
    return Sonuc(True, f'{yol} ({len(ogeler)} öğe):\n' + '\n'.join(satirlar) + ek)


@arac('dosya_oku', 'Bir metin dosyasının içeriğini okur (ilk 8000 karakter).',
      {'yol': metin('Dosyanın tam yolu veya "Belgeler/not.txt" gibi yol')},
      ['yol'], risk=OKUMA, yan_etki=False, guvenilmez_cikti=True)
def dosya_oku(baglam, yol):
    p = yollar.coz(yol)
    if not p.is_file():
        return Sonuc(False, f'Dosya bulunamadı: {p}')
    try:
        return Sonuc(True, p.read_text(encoding='utf-8', errors='replace')[:8000])
    except OSError as e:
        return _disk_hatasi(e)


# ------------------------------------------------------------------ write

def _yazildi_mi(argumanlar):
    p = yollar.coz(argumanlar['yol'])
    try:
        return p.is_file() and p.read_text(encoding='utf-8') == argumanlar['icerik']
    except OSError:
        return False


@arac('dosya_yaz', 'Bir metin dosyası oluşturur. Var olan dosyanın üzerine yazmak için uzerine_yaz=true '
      'gerekir; o zaman eski hali yedeklenir.',
      {'yol': metin('Dosyanın yolu, ör. "Belgeler/alisveris.txt"'),
       'icerik': metin('Dosyaya yazılacak metin'),
       'uzerine_yaz': {'type': 'boolean', 'description': 'Dosya varsa üzerine yazılsın mı'}},
      ['yol', 'icerik'], risk=YAZMA, yan_etki=True, yol_argumanlari=('yol',), zaten_yapildi=_yazildi_mi,
      harici_sonrasi_serbest=lambda a: not a.get('uzerine_yaz'))
def dosya_yaz(baglam, yol, icerik, uzerine_yaz=False):
    p = yollar.coz(yol)
    yedek = None
    try:
        if p.exists():
            if not uzerine_yaz:
                return Sonuc(False, f'{p} zaten var. Üzerine yazmak için uzerine_yaz=true kullanın '
                                    'veya başka bir ad seçin.', dogrulandi=False)
            yedek = _yedekle(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(icerik, encoding='utf-8')
        dogru = p.read_text(encoding='utf-8') == icerik
    except OSError as e:
        return _disk_hatasi(e)
    geri = ({'tur': 'yedekten_yukle', 'yedek': str(yedek), 'hedef': str(p)} if yedek
            else {'tur': 'cop_kutusuna', 'yol': str(p)})
    return Sonuc(dogru, f'{p} kaydedildi ({len(icerik)} karakter).' if dogru else f'{p} yazıldı ama içerik tutmuyor.',
                 dogrulandi=dogru, veri={'yol': str(p)}, geri_al=geri)


@arac('klasor_olustur', 'Yeni bir klasör oluşturur.',
      {'yol': metin('Klasör yolu, ör. "Belgeler/Faturalar"')},
      ['yol'], risk=YAZMA, yan_etki=True, yol_argumanlari=('yol',),
      zaten_yapildi=lambda a: yollar.coz(a['yol']).is_dir(), harici_sonrasi_serbest=lambda a: True)
def klasor_olustur(baglam, yol):
    p = yollar.coz(yol)
    vardi = p.is_dir()
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return _disk_hatasi(e)
    return Sonuc(p.is_dir(), f'{p} {"zaten vardı" if vardi else "oluşturuldu"}.', dogrulandi=p.is_dir(),
                 veri={'yol': str(p)}, geri_al=None if vardi else {'tur': 'bos_klasoru_sil', 'yol': str(p)})


def _hedef(kaynak: Path, hedef: str) -> Path:
    h = yollar.coz(hedef)
    # "Belgeler/Faturalar" that does not exist yet is meant as a folder when the
    # source has an extension and the target has none.
    if h.is_dir() or (not h.exists() and not h.suffix and kaynak.suffix):
        return h / kaynak.name
    return h


@arac('dosya_kopyala', 'Bir dosyayı veya klasörü kopyalar. Hedef var olan bir klasörse içine kopyalar.',
      {'kaynak': metin('Kopyalanacak dosyanın yolu'), 'hedef': metin('Hedef klasör veya yeni dosya yolu')},
      ['kaynak', 'hedef'], risk=YAZMA, yan_etki=True, yol_argumanlari=('hedef',), zaman_asimi=600)
def dosya_kopyala(baglam, kaynak, hedef):
    k = yollar.coz(kaynak)
    if not k.exists():
        return Sonuc(False, f'Kaynak bulunamadı: {k}', dogrulandi=False)
    son = _hedef(k, hedef)
    if son.exists():
        return Sonuc(False, f'Hedefte aynı adda öğe var: {son}. Başka bir ad verin.', dogrulandi=False)
    try:
        son.parent.mkdir(parents=True, exist_ok=True)
        if k.is_dir():
            shutil.copytree(k, son)
            dogru = son.is_dir()
        else:
            shutil.copy2(k, son)
            dogru = son.is_file() and son.stat().st_size == k.stat().st_size
    except OSError as e:
        return _disk_hatasi(e)
    return Sonuc(dogru, f'{k.name} kopyalandı: {son}', dogrulandi=dogru, veri={'yol': str(son)},
                 geri_al={'tur': 'cop_kutusuna', 'yol': str(son)})


def _tasindi_mi(argumanlar):
    k = yollar.coz(argumanlar['kaynak'])
    return not k.exists() and _hedef(k, argumanlar['hedef']).exists()


@arac('dosya_tasi', 'Bir dosyayı veya klasörü başka bir klasöre taşır. Hedef var olan bir klasörse içine taşır.',
      {'kaynak': metin('Taşınacak dosyanın yolu'), 'hedef': metin('Hedef klasör veya yeni yol')},
      ['kaynak', 'hedef'], risk=YAZMA, yan_etki=True, yol_argumanlari=('kaynak', 'hedef'),
      zaman_asimi=600, zaten_yapildi=_tasindi_mi)
def dosya_tasi(baglam, kaynak, hedef):
    k = yollar.coz(kaynak)
    if not k.exists():
        return Sonuc(False, f'Kaynak bulunamadı: {k}', dogrulandi=False)
    son = _hedef(k, hedef)
    if son.exists():
        return Sonuc(False, f'Hedefte aynı adda öğe var: {son}. Üzerine yazmıyorum.', dogrulandi=False)
    try:
        son.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(k), str(son))
    except OSError as e:
        return _disk_hatasi(e)
    dogru = son.exists() and not k.exists()
    return Sonuc(dogru, f'{k.name} taşındı: {son}', dogrulandi=dogru, veri={'yol': str(son)},
                 geri_al={'tur': 'tasi', 'kaynak': str(son), 'hedef': str(k)})


@arac('yeniden_adlandir', 'Bir dosyanın veya klasörün adını değiştirir (aynı klasörde kalır).',
      {'yol': metin('Dosyanın yolu'), 'yeni_ad': metin('Yeni ad (uzantısıyla), ör. "rapor-2026.pdf"')},
      ['yol', 'yeni_ad'], risk=YAZMA, yan_etki=True, yol_argumanlari=('yol',))
def yeniden_adlandir(baglam, yol, yeni_ad):
    if any(c in yeni_ad for c in '\\/:*?"<>|'):
        return Sonuc(False, 'Yeni ad klasör yolu veya geçersiz karakter içeremez.', dogrulandi=False)
    k = yollar.coz(yol)
    return dosya_tasi(baglam, str(k), str(k.with_name(yeni_ad)))


@arac('cop_kutusuna_gonder', 'Bir dosyayı veya klasörü Geri Dönüşüm Kutusu\'na gönderir (oradan geri yüklenebilir).',
      {'yol': metin('Silinecek dosyanın yolu')},
      ['yol'], risk=SILME, yan_etki=True, yol_argumanlari=('yol',),
      zaten_yapildi=lambda a: not yollar.coz(a['yol']).exists())
def cop_kutusuna_gonder(baglam, yol):
    p = yollar.coz(yol)
    if not p.exists():
        return Sonuc(False, f'Bulunamadı: {p}', dogrulandi=False)
    from send2trash import send2trash
    try:
        send2trash(str(p))
    except OSError as e:
        return _disk_hatasi(e)
    dogru = not p.exists()
    return Sonuc(dogru, f'{p.name} Geri Dönüşüm Kutusu\'na gönderildi.', dogrulandi=dogru)


# ------------------------------------------------------------------ undo

def geri_al_uygula(kayit: dict) -> Sonuc:
    tur = kayit['tur']
    try:
        if tur == 'tasi':
            k, h = Path(kayit['kaynak']), Path(kayit['hedef'])
            if h.exists():
                return Sonuc(False, f'{h} zaten var, geri taşıyamıyorum.', dogrulandi=False)
            shutil.move(str(k), str(h))
            return Sonuc(h.exists(), f'{h.name} eski yerine taşındı: {h.parent}', dogrulandi=h.exists())
        if tur == 'yedekten_yukle':
            shutil.copy2(kayit['yedek'], kayit['hedef'])
            return Sonuc(True, f'{Path(kayit["hedef"]).name} önceki haline döndürüldü.', dogrulandi=True)
        if tur == 'cop_kutusuna':
            from send2trash import send2trash
            send2trash(kayit['yol'])
            return Sonuc(True, f'{Path(kayit["yol"]).name} geri dönüşüm kutusuna gönderildi.',
                         dogrulandi=not Path(kayit['yol']).exists())
        if tur == 'bos_klasoru_sil':
            os.rmdir(kayit['yol'])
            return Sonuc(True, f'{kayit["yol"]} kaldırıldı.', dogrulandi=True)
    except OSError as e:
        return _disk_hatasi(e)
    return Sonuc(False, f'Bu işlem geri alınamıyor ({tur}).')


@arac('son_islemi_geri_al', 'JARVIS\'in yaptığı son geri alınabilir dosya işlemini geri alır '
      '(ör. yanlış klasöre taşınan dosyayı eski yerine koyar).',
      {}, [], risk=YAZMA, yan_etki=True)
def son_islemi_geri_al(baglam):
    adim = baglam.depo.son_geri_alinabilir() if baglam.depo else None
    if not adim:
        return Sonuc(False, 'Geri alınacak bir işlem yok.')
    import json
    sonuc = geri_al_uygula(json.loads(adim['geri_al']))
    if sonuc.basarili:
        baglam.depo.geri_alindi_isaretle(adim['id'])
    return sonuc
