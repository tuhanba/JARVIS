"""Windows UI Automation: list, click and fill controls inside desktop apps by
their accessible names (pywinauto, UIA backend) - no screen coordinates.

The user keeps priority: before acting, the tools wait until the mouse has
been still for a moment, and give up if the user keeps using it."""
import sys
import time

from ..izinler import DIS_ILETISIM, OKUMA, YAZMA
from .temel import Sonuc, arac, metin

WIN = sys.platform == 'win32'
TURLER = ('Button', 'MenuItem', 'Hyperlink', 'CheckBox', 'RadioButton', 'TabItem', 'ListItem', 'TreeItem',
          'Edit', 'ComboBox', 'Document', 'SplitButton')


def _fare():
    import pyautogui
    return pyautogui.position()


def fare_bosta_bekle(baglam, sakin: float = 1.2, en_fazla: float = 12, konum=None) -> bool:
    """Wait until the mouse has not moved for `sakin` seconds. False if the user
    kept using it for `en_fazla` seconds (then the tool backs off)."""
    konum = konum or _fare
    try:
        son = konum()
    except Exception:
        return True          # no display / no mouse: nothing to protect
    son_hareket = time.time() - sakin
    bitis = time.time() + en_fazla
    while time.time() < bitis:
        baglam.kontrol()
        simdi = konum()
        if abs(simdi[0] - son[0]) + abs(simdi[1] - son[1]) > 6:
            son, son_hareket = simdi, time.time()
        if time.time() - son_hareket >= sakin:
            return True
        time.sleep(0.05)
    return False


def _pencere(baslik: str):
    from pywinauto import Desktop
    import re
    adaylar = [w for w in Desktop(backend='uia').windows(title_re=f'(?i).*{re.escape(baslik)}.*', visible_only=True)]
    return adaylar[0] if adaylar else None


def _ogeler(pencere, sinir=80):
    sonuc = []
    for o in pencere.descendants():
        try:
            tur = o.element_info.control_type
            ad = (o.window_text() or o.element_info.name or '').strip()
        except Exception:
            continue
        if tur in TURLER and (ad or tur in ('Edit', 'Document')) and o.is_visible():
            sonuc.append((tur, ad, o))
            if len(sonuc) >= sinir:
                break
    return sonuc


def _bul(pencere, ad: str, tur: str = ''):
    ogeler = _ogeler(pencere, 400)
    if tur:
        ogeler = [x for x in ogeler if x[0].lower() == tur.lower()]
    for eslesme in (lambda a: a.lower() == ad.lower(), lambda a: ad.lower() in a.lower()):
        for t, a, o in ogeler:
            if a and eslesme(a):
                return t, a, o
    return None


@arac('pencere_ogeleri', 'Bir uygulama penceresindeki düğme, menü, sekme, liste ve yazı alanlarını adlarıyla listeler '
      '(Windows UI Automation).',
      {'pencere': metin('Pencere başlığından bir parça, ör. "Ayarlar", "Hesap Makinesi"')},
      ['pencere'], risk=OKUMA, yan_etki=False, zaman_asimi=30, guvenilmez_cikti=True)
def pencere_ogeleri(baglam, pencere):
    if not WIN:
        return Sonuc(False, 'Bu araç yalnızca Windows\'ta çalışır.')
    p = _pencere(pencere)
    if p is None:
        return Sonuc(False, f'"{pencere}" başlıklı açık bir pencere yok.')
    satirlar = [f'{t}: {a or "(adsız)"}' for t, a, _ in _ogeler(p)]
    return Sonuc(True, f'Pencere: {p.window_text()}\n' + '\n'.join(satirlar))


def _tik_riski(a):
    from .tarayici import HASSAS
    return DIS_ILETISIM if a.get('hassas') or HASSAS.search(str(a.get('oge', ''))) else YAZMA


@arac('ogeye_tikla', 'Bir uygulama penceresindeki düğmeye/menüye/sekmeye adıyla tıklar (UI Automation; koordinat yok). '
      'Satın alma, gönderme, silme gibi işlemler için hassas=true gerekir ve onay istenir.',
      {'pencere': metin('Pencere başlığından bir parça'),
       'oge': metin('Öğenin adı, ör. "Kaydet", "Bluetooth", "Tamam"'),
       'tur': metin('İsteğe bağlı öğe türü: Button, MenuItem, TabItem, ListItem, CheckBox...'),
       'hassas': {'type': 'boolean', 'description': 'Geri alınamaz bir işlemse true'}},
      ['pencere', 'oge'], risk=YAZMA, yan_etki=True, zaman_asimi=40, risk_belirle=_tik_riski)
def ogeye_tikla(baglam, pencere, oge, tur='', hassas=False):
    if not WIN:
        return Sonuc(False, 'Bu araç yalnızca Windows\'ta çalışır.', dogrulandi=False)
    from .tarayici import HASSAS
    p = _pencere(pencere)
    if p is None:
        return Sonuc(False, f'"{pencere}" başlıklı açık bir pencere yok.', dogrulandi=False)
    bulunan = _bul(p, oge, tur)
    if not bulunan:
        return Sonuc(False, f'"{oge}" bulunamadı. Penceredeki öğeler:\n' +
                     '\n'.join(f'{t}: {a}' for t, a, _ in _ogeler(p, 30)), dogrulandi=False)
    t, ad, o = bulunan
    if not hassas and HASSAS.search(ad):
        return Sonuc(False, f'"{ad}" hassas görünüyor; gerçekten tıklanacaksa hassas=true ile tekrar çağır.', dogrulandi=False)
    if not o.is_enabled():
        return Sonuc(False, f'"{ad}" şu an pasif (tıklanamaz).', dogrulandi=False)
    if not fare_bosta_bekle(baglam):
        return Sonuc(False, 'Fareyi kullanıyorsunuz; size karışmamak için durdum.', dogrulandi=False)
    once = [x[1] for x in _ogeler(p, 120)]
    try:
        if t in ('CheckBox',):
            o.toggle()
        elif t in ('TabItem', 'ListItem', 'TreeItem', 'RadioButton'):
            o.select()
        else:
            o.invoke()           # UIA Invoke pattern: no mouse movement
    except Exception:
        p.set_focus()
        o.click_input()
    time.sleep(0.6)
    try:
        sonra = [x[1] for x in _ogeler(p, 120)]
    except Exception:
        sonra = None             # window closed / replaced: something happened
    degisti = sonra is None or sonra != once
    return Sonuc(True, f'{t} "{ad}" tıklandı' + ('' if degisti else ' (pencerede görünür değişiklik yok)'),
                 dogrulandi=True if degisti else None)


@arac('ogeye_yaz', 'Bir uygulama penceresindeki yazı alanına adıyla bulup yazar ve yazılanı doğrular. Parola alanlarına yazmaz.',
      {'pencere': metin('Pencere başlığından bir parça'),
       'alan': metin('Alanın adı/etiketi; boş bırakılırsa penceredeki ilk yazı alanı'),
       'metin': metin('Yazılacak metin')},
      ['pencere', 'metin'], risk=YAZMA, yan_etki=True, zaman_asimi=40)
def ogeye_yaz(baglam, pencere, metin, alan=''):
    if not WIN:
        return Sonuc(False, 'Bu araç yalnızca Windows\'ta çalışır.', dogrulandi=False)
    p = _pencere(pencere)
    if p is None:
        return Sonuc(False, f'"{pencere}" başlıklı açık bir pencere yok.', dogrulandi=False)
    adaylar = [(t, a, o) for t, a, o in _ogeler(p, 400) if t in ('Edit', 'Document', 'ComboBox')]
    if alan:
        adaylar = [x for x in adaylar if alan.lower() in (x[1] or '').lower()]
    if not adaylar:
        return Sonuc(False, f'"{alan or "yazı alanı"}" bulunamadı.', dogrulandi=False)
    t, ad, o = adaylar[0]
    try:
        parola = bool(o.element_info.element.CurrentIsPassword)
    except Exception:
        parola = False
    if parola:
        return Sonuc(False, 'Bu bir parola alanı; buraya yazmam.', dogrulandi=False)
    if not fare_bosta_bekle(baglam):
        return Sonuc(False, 'Fareyi kullanıyorsunuz; size karışmamak için durdum.', dogrulandi=False)
    try:
        o.set_edit_text(metin)
    except Exception:
        p.set_focus()
        o.click_input()
        o.type_keys(metin, with_spaces=True, set_foreground=True)
    time.sleep(0.3)
    try:
        deger = o.get_value() if hasattr(o, 'get_value') else o.window_text()
    except Exception:
        deger = o.window_text()
    dogru = metin.strip()[:60] in (deger or '')
    return Sonuc(dogru, f'"{ad or t}" alanına yazıldı' + ('' if dogru else ' ama değeri okuyamadım'),
                 dogrulandi=dogru if dogru else None)
