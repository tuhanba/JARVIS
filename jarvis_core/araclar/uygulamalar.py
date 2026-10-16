"""App and window tools. Opening is verified by a new process or a window
title; typing only happens after the target window is confirmed in front."""
import subprocess
import sys
import time
from pathlib import Path

import psutil

from .. import yollar
from ..izinler import OKUMA, YAZMA
from .temel import PENCERESIZ, Sonuc, arac, metin

WIN = sys.platform == 'win32'


def _sistem():
    import sistem  # app name tables live in the legacy module
    return sistem


def on_plan_basligi() -> str:
    if not WIN:
        return ''
    import ctypes
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    uzunluk = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
    tampon = ctypes.create_unicode_buffer(uzunluk + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, tampon, uzunluk + 1)
    return tampon.value


def pencere_basliklari() -> list:
    if not WIN:
        return []
    try:
        import pygetwindow
        return [t for t in pygetwindow.getAllTitles() if t.strip()]
    except Exception:
        return []


def _hedef_bul(ad: str):
    """(launch target, expected process name or None) for a spoken app name."""
    s = _sistem()
    ad = ad.lower().strip()
    for kok, hedef in s.UYGULAMALAR.items():
        if kok in ad:
            return hedef, s.SURECLER.get(hedef)
    kisayol = s._baslat_menusu_ara(ad)
    if kisayol:
        return kisayol, None
    return None, None


def _surec_adlari() -> dict:
    adlar = {}
    for p in psutil.process_iter(['pid', 'name']):
        adlar[p.info['pid']] = (p.info['name'] or '').lower()
    return adlar


def _calisiyor_mu(surec_adi: str) -> bool:
    surec_adi = surec_adi.lower()
    return any(ad == surec_adi for ad in _surec_adlari().values())


def _acildi_mi(argumanlar: dict) -> bool:
    dosya = argumanlar.get('dosya')
    if dosya:
        return any(Path(dosya).name.lower() in t.lower() for t in pencere_basliklari())
    _, surec = _hedef_bul(argumanlar['ad'])
    return bool(surec) and _calisiyor_mu(surec)


@arac('uygulama_ac', 'Bir uygulamayı (isteğe bağlı bir dosyayla) açar ve açıldığını süreç/pencere ile doğrular. '
      'Ör. ad="not defteri", dosya="Belgeler/not.txt".',
      {'ad': metin('Uygulama adı: "not defteri", "hesap makinesi", "chrome", "excel", "spotify" ya da kurulu bir program'),
       'dosya': metin('İsteğe bağlı: uygulamayla açılacak dosyanın yolu')},
      ['ad'], risk=YAZMA, yan_etki=True, zaman_asimi=30, zaten_yapildi=_acildi_mi)
def uygulama_ac(baglam, ad, dosya=''):
    hedef, surec = _hedef_bul(ad)
    if not hedef:
        return Sonuc(False, f'"{ad}" adında kurulu bir uygulama bulamadım.', dogrulandi=False)
    dosya_yolu = str(yollar.coz(dosya)) if dosya else ''
    if dosya_yolu and not Path(dosya_yolu).exists():
        return Sonuc(False, f'Açılacak dosya yok: {dosya_yolu}', dogrulandi=False)

    onceki = set(_surec_adlari())
    try:
        if WIN:
            if hedef.lower().endswith('.lnk'):
                import os
                os.startfile(hedef)
            else:
                subprocess.Popen(['cmd', '/c', 'start', '', hedef] + ([dosya_yolu] if dosya_yolu else []),
                                 creationflags=0x08000000)
        else:
            subprocess.Popen([hedef] + ([dosya_yolu] if dosya_yolu else []),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        return Sonuc(False, f'{ad} başlatılamadı: {e}', dogrulandi=False)

    # Verify: a new process with the expected name, or a window showing the file / app name.
    aranan_baslik = Path(dosya_yolu).name.lower() if dosya_yolu else ''
    bitis = time.time() + 15
    while time.time() < bitis:
        baglam.kontrol()
        if surec and any(pid not in onceki and ad_ == surec.lower() for pid, ad_ in _surec_adlari().items()):
            if not aranan_baslik or any(aranan_baslik in t.lower() for t in pencere_basliklari()) or not WIN:
                return Sonuc(True, f'{ad} açıldı.', dogrulandi=True)
        if aranan_baslik and any(aranan_baslik in t.lower() for t in pencere_basliklari()):
            return Sonuc(True, f'{ad} {Path(dosya_yolu).name} ile açıldı.', dogrulandi=True)
        if not surec and not aranan_baslik and any(ad.lower() in t.lower() for t in pencere_basliklari()):
            return Sonuc(True, f'{ad} açıldı.', dogrulandi=True)
        time.sleep(0.5)
    if surec and _calisiyor_mu(surec) and not aranan_baslik:
        return Sonuc(True, f'{ad} zaten açıktı.', dogrulandi=True)
    return Sonuc(False, f'{ad} için başlatma komutu verildi ama 15 saniyede açılan pencere veya süreç göremedim.',
                 dogrulandi=False)


@arac('uygulama_kapat', 'Bir uygulamayı normal yolla kapatır (kaydedilmemiş iş varsa uygulama kendisi sorar) '
      've kapandığını doğrular. Zorla kapatmaz.',
      {'ad': metin('Uygulama adı veya süreç adı, ör. "chrome", "notepad.exe"')},
      ['ad'], risk=YAZMA, yan_etki=True, zaman_asimi=20,
      zaten_yapildi=lambda a: not _calisiyor_mu(_hedef_bul(a['ad'])[1] or a['ad']))
def uygulama_kapat(baglam, ad):
    _, surec = _hedef_bul(ad)
    surec = (surec or (ad if ad.lower().endswith('.exe') else ad.replace(' ', '') + ('.exe' if WIN else ''))).lower()
    hedefler = [p for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower() == surec]
    if not hedefler:
        return Sonuc(True, f'{ad} zaten açık değil.', dogrulandi=True)
    if WIN:
        subprocess.run(['taskkill', '/im', surec], capture_output=True, creationflags=PENCERESIZ)
    else:
        for p in hedefler:
            p.terminate()
    bitis = time.time() + 10
    while time.time() < bitis:
        baglam.kontrol()
        if not _calisiyor_mu(surec):
            return Sonuc(True, f'{ad} kapatıldı.', dogrulandi=True)
        time.sleep(0.5)
    return Sonuc(False, f'{ad} kapanmadı; kaydedilmemiş değişiklik sorusu açık olabilir.', dogrulandi=False)


@arac('pencereleri_listele', 'Açık pencerelerin başlıklarını ve öndeki pencereyi listeler.', {}, [],
      risk=OKUMA, yan_etki=False)
def pencereleri_listele(baglam):
    if not WIN:
        return Sonuc(False, 'Pencere listesi yalnızca Windows\'ta destekleniyor.')
    return Sonuc(True, f'Öndeki: {on_plan_basligi()}\nAçık pencereler: ' + ' | '.join(pencere_basliklari()[:40]))


def _one_getir(baslik: str) -> bool:
    import pygetwindow
    adaylar = [w for w in pygetwindow.getWindowsWithTitle(baslik) if w.title]
    if not adaylar:
        return False
    w = adaylar[0]
    if w.isMinimized:
        w.restore()
    try:
        w.activate()
    except Exception:
        # Windows refuses SetForegroundWindow from background processes; an Alt tap unlocks it.
        import pyautogui
        pyautogui.press('alt')
        w.activate()
    time.sleep(0.4)
    return baslik.lower() in on_plan_basligi().lower()


@arac('pencereye_gec', 'Başlığında verilen metin geçen pencereyi öne getirir ve öne geldiğini doğrular.',
      {'baslik': metin('Pencere başlığının bir parçası, ör. "Not Defteri", "Chrome"')},
      ['baslik'], risk=YAZMA, yan_etki=True)
def pencereye_gec(baglam, baslik):
    if not WIN:
        return Sonuc(False, 'Pencere yönetimi yalnızca Windows\'ta destekleniyor.', dogrulandi=False)
    if _one_getir(baslik):
        return Sonuc(True, f'"{on_plan_basligi()}" öne getirildi.', dogrulandi=True)
    return Sonuc(False, f'"{baslik}" başlıklı pencere bulunamadı veya öne getirilemedi.', dogrulandi=False)


def _odaktaki_metin():
    """Text of the focused control via UI Automation (Windows, needs pywinauto)."""
    try:
        from pywinauto import Desktop
        pencere = Desktop(backend='uia').window(active_only=True)
        for tur in ('Document', 'Edit'):
            kontrol = pencere.child_window(control_type=tur, found_index=0)
            if kontrol.exists(timeout=1):
                return kontrol.window_text() or kontrol.legacy_properties().get('Value', '')
    except Exception:
        return None
    return None


@arac('metin_yaz', 'Belirtilen pencereyi öne getirip imlecin olduğu yere metin yazar (Türkçe karakterler dahil). '
      'Pencere öne gelmezse yazmaz.',
      {'metin': metin('Yazılacak metin'), 'pencere': metin('Yazılacak pencerenin başlığından bir parça, ör. "Not Defteri"')},
      ['metin', 'pencere'], risk=YAZMA, yan_etki=True)
def metin_yaz(baglam, metin, pencere):
    if not WIN:
        return Sonuc(False, 'Metin yazma yalnızca Windows\'ta destekleniyor.', dogrulandi=False)
    from .arayuz_otomasyonu import fare_bosta_bekle
    if not fare_bosta_bekle(baglam):
        return Sonuc(False, 'Fareyi kullanıyorsunuz; size karışmamak için durdum.', dogrulandi=False)
    if not _one_getir(pencere):
        return Sonuc(False, f'"{pencere}" penceresi öne gelmedi; kör yazmamak için durdum.', dogrulandi=False)
    import pyautogui
    import pyperclip
    eski = pyperclip.paste()
    pyperclip.copy(metin)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.3)
    pyperclip.copy(eski)
    okunan = _odaktaki_metin()
    if okunan is None:
        return Sonuc(True, f'"{on_plan_basligi()}" penceresine yazıldı (içerik okunamadı, doğrulanamadı).',
                     dogrulandi=None)
    dogru = metin.strip()[:50] in okunan
    return Sonuc(dogru, 'Yazıldı ve pencerede görüldü.' if dogru else 'Yazıldı ama pencerede göremedim.',
                 dogrulandi=dogru)


@arac('pano_oku', 'Panodaki metni okur.', {}, [], risk=OKUMA, yan_etki=False, guvenilmez_cikti=True)
def pano_oku(baglam):
    import pyperclip
    return Sonuc(True, pyperclip.paste()[:4000] or '(pano boş)')


@arac('pano_yaz', 'Bir metni panoya kopyalar.', {'metin': metin('Kopyalanacak metin')}, ['metin'],
      risk=YAZMA, yan_etki=True)
def pano_yaz(baglam, metin):
    import pyperclip
    pyperclip.copy(metin)
    dogru = pyperclip.paste() == metin
    return Sonuc(dogru, 'Panoya kopyalandı.', dogrulandi=dogru)
