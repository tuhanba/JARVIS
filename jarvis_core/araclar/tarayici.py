"""Browser control with Playwright, driving the installed Microsoft Edge in a
visible window with its own profile (veri/tarayici_profili).

Elements are found by their visible text / accessible name, never by screen
coordinates. Safety:
- password and payment-card fields are never filled (log in yourself in the
  window; the session stays in the profile);
- clicks and form submits whose element looks like buy / pay / send /
  publish / delete / confirm are 'dis_iletisim' risk: asked every time. The
  tool also checks the real element right before clicking, so the model
  cannot get around it with a harmless-looking label;
- page text is untrusted data.

Playwright's sync API must be used from one thread, so a single browser
thread runs every action and tools hand work to it through a queue."""
import os
import queue
import re
import sys
import threading
import time
from pathlib import Path
from urllib.parse import quote_plus

from .. import yollar
from ..ayarlar import Ayarlar
from ..izinler import DIS_ILETISIM, OKUMA, YAZMA
from .temel import Iptal, Sonuc, arac, metin

HASSAS = re.compile(
    r'satın\s*al|satin\s*al|sepete|ödeme|odeme|öde\b|ode\b|sipariş|siparis|siparişi|gönder|gonder|paylaş|paylas|'
    r'yayınla|yayinla|sil\b|silin|kaldır|kaldir|onayla|abone|kaydol|üye ol|uye ol|bağış|bagis|transfer|havale|'
    r'eft\b|tamamla|satın|kirala|teklif ver|buy|purchase|pay\b|checkout|order|send|submit|post\b|publish|delete|'
    r'remove|confirm|subscribe|sign\s*up|donate|place order', re.IGNORECASE)
GIZLI_ALAN = re.compile(r'password|parola|şifre|sifre|cc-|card|kart|cvv|cvc|iban|otp|one-time', re.IGNORECASE)


class _Tarayici:
    """Owns the Playwright browser on one thread."""

    def __init__(self) -> None:
        self.isler = queue.Queue()
        self.is_parcacigi = None
        self.baglam = None
        self.sayfa = None

    def _dongu(self) -> None:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            self.pw = pw
            while True:
                is_, kutu = self.isler.get()
                if is_ is None:
                    break
                try:
                    kutu['sonuc'] = is_()
                except Exception as e:
                    kutu['hata'] = e
                kutu['olay'].set()
            if self.baglam:
                try:
                    self.baglam.close()
                except Exception:
                    pass

    def calistir(self, is_, baglam, zaman_asimi: float = 60):
        if not self.is_parcacigi or not self.is_parcacigi.is_alive():
            self.is_parcacigi = threading.Thread(target=self._dongu, daemon=True)
            self.is_parcacigi.start()
        kutu = {'olay': threading.Event()}
        self.isler.put((is_, kutu))
        bitis = time.time() + zaman_asimi
        while not kutu['olay'].wait(0.1):
            baglam.kontrol()
            if time.time() > bitis:
                raise TimeoutError('tarayıcı işlemi zaman aşımına uğradı')
        if 'hata' in kutu:
            raise kutu['hata']
        return kutu['sonuc']

    # -------------------------------------------------- browser thread only
    def _ac(self):
        if self.baglam:
            try:
                self.baglam.pages   # still alive?
                if self.sayfa is None or self.sayfa.is_closed():
                    self.sayfa = self.baglam.pages[-1] if self.baglam.pages else self.baglam.new_page()
                return self.sayfa
            except Exception:
                self.baglam = None
        profil = Ayarlar().veri_dizini / 'tarayici_profili'
        profil.mkdir(parents=True, exist_ok=True)
        ayar = dict(user_data_dir=str(profil), headless=os.getenv('JARVIS_TARAYICI_GIZLI') == '1',
                    accept_downloads=True, no_viewport=True, args=['--start-maximized'])
        yol = os.getenv('JARVIS_TARAYICI_YOLU')
        if yol:
            ayar['executable_path'] = yol
        elif sys.platform == 'win32':
            ayar['channel'] = 'msedge'      # the Edge that ships with Windows; nothing to download
        self.baglam = self.pw.chromium.launch_persistent_context(**ayar)
        self.baglam.on('page', lambda p: setattr(self, 'sayfa', p))
        self.sayfa = self.baglam.pages[0] if self.baglam.pages else self.baglam.new_page()
        return self.sayfa


_T = _Tarayici()


def _ozet(sayfa) -> str:
    return f'"{sayfa.title()}" ({sayfa.url})'


def _durum_izi(sayfa):
    try:
        return (sayfa.url, sayfa.evaluate('document.body ? document.body.innerText.length : 0'), len(sayfa.context.pages))
    except Exception:
        return (sayfa.url, 0, 0)


def _bul(sayfa, ad: str):
    """Find one visible element by its text / accessible name."""
    adaylar = [sayfa.get_by_role('button', name=ad), sayfa.get_by_role('link', name=ad),
               sayfa.get_by_role('menuitem', name=ad), sayfa.get_by_role('tab', name=ad),
               sayfa.get_by_role('checkbox', name=ad), sayfa.get_by_role('radio', name=ad),
               sayfa.get_by_text(ad, exact=True), sayfa.get_by_text(ad)]
    for aday in adaylar:
        try:
            for i in range(min(aday.count(), 5)):
                o = aday.nth(i)
                if o.is_visible():
                    return o
        except Exception:
            continue
    return None


def _ogeler(sayfa, sinir: int = 40) -> list:
    js = """(n) => {
      const out = [];
      for (const e of document.querySelectorAll('a,button,input,select,textarea,[role=button],[role=link]')) {
        const r = e.getBoundingClientRect();
        if (!r.width || !r.height || getComputedStyle(e).visibility === 'hidden') continue;
        const ad = (e.getAttribute('aria-label') || e.innerText || e.value || e.placeholder || e.name || '').trim().slice(0, 60);
        const tur = e.tagName.toLowerCase() + (e.type ? ':' + e.type : '');
        if (ad || e.tagName === 'INPUT') out.push(tur + ' «' + ad + '»');
        if (out.length >= n) break;
      }
      return out; }"""
    try:
        return sayfa.evaluate(js, sinir)
    except Exception:
        return []


def _harici(a):
    return True


# ------------------------------------------------------------------ tools

@arac('tarayici_git', 'Tarayıcıda (Edge) bir adrese gider. yeni_sekme=true ise yeni sekmede açar.',
      {'adres': metin('Adres, ör. "https://www.trendyol.com" veya "trendyol.com"'),
       'yeni_sekme': {'type': 'boolean', 'description': 'Yeni sekmede aç'}},
      ['adres'], risk=YAZMA, yan_etki=True, zaman_asimi=60, guvenilmez_cikti=True,
      # After untrusted content: a page could ask to "visit evil.com/?data=..." to smuggle data out
      # in the URL, so only short addresses without a query string go through without a yes.
      harici_sonrasi_serbest=lambda a: '?' not in a.get('adres', '') and '#' not in a.get('adres', '')
      and len(a.get('adres', '')) <= 120)
def tarayici_git(baglam, adres, yeni_sekme=False):
    url = adres if re.match(r'^[a-z]+://', adres) else 'https://' + adres.strip()
    if not url.startswith(('http://', 'https://')):
        return Sonuc(False, 'Yalnızca http/https adresleri açılır.')

    def is_():
        sayfa = _T._ac()
        if yeni_sekme:
            sayfa = _T.baglam.new_page()
            _T.sayfa = sayfa
        sayfa.goto(url, wait_until='domcontentloaded', timeout=45000)
        sayfa.bring_to_front()
        return _ozet(sayfa)
    try:
        return Sonuc(True, 'Açıldı: ' + _T.calistir(is_, baglam, 60))
    except Iptal:
        raise
    except Exception as e:
        return Sonuc(False, f'Sayfa açılamadı: {str(e).splitlines()[0][:200]}')


@arac('tarayici_ara', 'Tarayıcıda internette arama yapar ve sonuç sayfasını açar.',
      {'sorgu': metin('Arama metni')}, ['sorgu'], risk=YAZMA, yan_etki=True, zaman_asimi=60, guvenilmez_cikti=True,
      harici_sonrasi_serbest=lambda a: len(a.get('sorgu', '')) <= 80)
def tarayici_ara(baglam, sorgu):
    return tarayici_git(baglam, 'https://duckduckgo.com/?q=' + quote_plus(sorgu))


@arac('sayfa_oku', 'Tarayıcıda açık sayfanın metnini ve tıklanabilir öğelerin/alanların listesini okur.',
      {}, [], risk=OKUMA, yan_etki=False, zaman_asimi=30, guvenilmez_cikti=True)
def sayfa_oku(baglam):
    def is_():
        sayfa = _T._ac()
        govde = sayfa.evaluate('document.body ? document.body.innerText : ""') or ''
        govde = re.sub(r'\n\s*\n+', '\n', govde).strip()
        return f'{_ozet(sayfa)}\n{govde[:7000]}\n\nTıklanabilir öğeler ve alanlar:\n' + '\n'.join(_ogeler(sayfa))
    try:
        return Sonuc(True, _T.calistir(is_, baglam, 30))
    except Iptal:
        raise
    except Exception as e:
        return Sonuc(False, f'Sayfa okunamadı: {e}')


def _tik_riski(a):
    return DIS_ILETISIM if a.get('hassas') or HASSAS.search(str(a.get('metin', ''))) else YAZMA


@arac('tarayici_tikla', 'Açık sayfada görünen metni/adı verilen bağlantıya veya düğmeye tıklar ve sayfanın değiştiğini '
      'doğrular. Satın alma, ödeme, gönderme, silme, yayınlama gibi düğmeler için hassas=true gerekir ve kullanıcı onayı istenir.',
      {'metin': metin('Öğenin görünen metni veya adı, ör. "Sonraki sayfa", "Giriş"'),
       'hassas': {'type': 'boolean', 'description': 'Satın alma/gönderme/silme gibi geri alınamaz bir düğmeyse true'}},
      ['metin'], risk=YAZMA, yan_etki=True, zaman_asimi=60, risk_belirle=_tik_riski,
      harici_sonrasi_serbest=lambda a: _tik_riski(a) == YAZMA)
def tarayici_tikla(baglam, metin, hassas=False):
    def is_():
        sayfa = _T._ac()
        oge = _bul(sayfa, metin)
        if oge is None:
            return Sonuc(False, f'"{metin}" adlı görünür bir öğe bulamadım. Sayfadaki öğeler:\n' + '\n'.join(_ogeler(sayfa, 25)),
                         dogrulandi=False)
        gercek = ' '.join(filter(None, [oge.get_attribute('aria-label') or '', oge.inner_text(timeout=2000) or '',
                                        oge.get_attribute('value') or '', oge.get_attribute('type') or '']))
        tur = (oge.get_attribute('type') or '').lower()
        if not hassas and (HASSAS.search(gercek) or (tur == 'submit' and oge.evaluate(
                'e => !!(e.form && e.form.querySelector("input[type=password]"))'))):
            return Sonuc(False, f'Bu öğe hassas görünüyor ("{gercek.strip()[:60]}"). Gerçekten tıklanacaksa '
                                'hassas=true ile tekrar çağır; kullanıcıdan onay istenecek.', dogrulandi=False)
        once = _durum_izi(sayfa)
        oge.scroll_into_view_if_needed(timeout=5000)
        oge.click(timeout=10000)
        try:
            sayfa.wait_for_load_state('domcontentloaded', timeout=8000)
        except Exception:
            pass
        sayfa.wait_for_timeout(700)
        sayfa = _T.sayfa or sayfa
        sonra = _durum_izi(sayfa)
        degisti = once != sonra
        return Sonuc(True, f'Tıklandı: "{metin}". Şimdi: {_ozet(sayfa)}' + ('' if degisti else ' (sayfada görünür değişiklik yok)'),
                     dogrulandi=True if degisti else None)
    try:
        return _T.calistir(is_, baglam, 60)
    except Iptal:
        raise
    except Exception as e:
        return Sonuc(False, f'Tıklanamadı: {str(e).splitlines()[0][:200]}', dogrulandi=False)


def _yaz_riski(a):
    if not a.get('gonder'):
        return YAZMA
    return YAZMA if re.search(r'\b(ara|arama|search|q|sorgu|bul)\b', str(a.get('alan', '')), re.IGNORECASE) else DIS_ILETISIM


@arac('tarayici_yaz', 'Açık sayfadaki bir metin alanına yazar (etiketi, yer tutucusu veya adıyla bulunur) ve yazılanı doğrular. '
      'gonder=true Enter\'a basar (arama kutusu dışında onay ister). Parola ve kart alanlarına asla yazmaz.',
      {'alan': metin('Alanın etiketi/yer tutucusu/adı, ör. "Ara", "E-posta", "Ad Soyad"'),
       'metin': metin('Yazılacak metin'),
       'gonder': {'type': 'boolean', 'description': 'Yazdıktan sonra Enter ile gönder'}},
      ['alan', 'metin'], risk=YAZMA, yan_etki=True, zaman_asimi=60, risk_belirle=_yaz_riski,
      harici_sonrasi_serbest=lambda a: not a.get('gonder'))
def tarayici_yaz(baglam, alan, metin, gonder=False):
    def is_():
        sayfa = _T._ac()
        oge = None
        for aday in (sayfa.get_by_label(alan), sayfa.get_by_placeholder(alan), sayfa.get_by_role('searchbox', name=alan),
                     sayfa.get_by_role('textbox', name=alan), sayfa.locator(f'[name="{alan}"]')):
            try:
                if aday.count() and aday.first.is_visible():
                    oge = aday.first
                    break
            except Exception:
                continue
        if oge is None:
            return Sonuc(False, f'"{alan}" adlı bir yazı alanı bulamadım. Sayfadaki alanlar:\n' + '\n'.join(
                o for o in _ogeler(sayfa, 40) if o.startswith(('input', 'textarea', 'select'))), dogrulandi=False)
        ozellik = ' '.join(oge.get_attribute(a) or '' for a in ('type', 'name', 'id', 'autocomplete', 'aria-label', 'placeholder'))
        if GIZLI_ALAN.search(ozellik):
            return Sonuc(False, 'Bu bir parola/ödeme alanı; buraya yazmam. Lütfen tarayıcı penceresinde kendiniz girin.',
                         dogrulandi=False)
        oge.fill(metin, timeout=10000)
        dogru = oge.input_value(timeout=3000) == metin
        if gonder:
            oge.press('Enter')
            try:
                sayfa.wait_for_load_state('domcontentloaded', timeout=8000)
            except Exception:
                pass
        return Sonuc(dogru, f'"{alan}" alanına yazıldı{" ve gönderildi" if gonder else ""}. Sayfa: {_ozet(_T.sayfa or sayfa)}',
                     dogrulandi=dogru)
    try:
        return _T.calistir(is_, baglam, 60)
    except Iptal:
        raise
    except Exception as e:
        return Sonuc(False, f'Yazılamadı: {str(e).splitlines()[0][:200]}', dogrulandi=False)


@arac('sekmeler', 'Tarayıcıdaki açık sekmeleri numaralarıyla listeler.', {}, [], risk=OKUMA, yan_etki=False,
      zaman_asimi=20, guvenilmez_cikti=True)
def sekmeler(baglam):
    def is_():
        _T._ac()
        return '\n'.join(f'{i}. {"* " if p == _T.sayfa else ""}{p.title()} ({p.url})' for i, p in enumerate(_T.baglam.pages))
    try:
        return Sonuc(True, _T.calistir(is_, baglam, 20))
    except Iptal:
        raise
    except Exception as e:
        return Sonuc(False, f'Sekmeler alınamadı: {e}')


@arac('sekme_sec', 'Numarası verilen sekmeye geçer (numaralar sekmeler aracından).',
      {'no': {'type': 'integer', 'minimum': 0, 'description': 'Sekme numarası'}}, ['no'],
      risk=YAZMA, yan_etki=True, zaman_asimi=20, harici_sonrasi_serbest=_harici)
def sekme_sec(baglam, no):
    def is_():
        _T._ac()
        if no >= len(_T.baglam.pages):
            return Sonuc(False, f'{no} numaralı sekme yok.', dogrulandi=False)
        _T.sayfa = _T.baglam.pages[no]
        _T.sayfa.bring_to_front()
        return Sonuc(True, f'Sekme {no}: {_ozet(_T.sayfa)}', dogrulandi=True)
    return _T.calistir(is_, baglam, 20)


@arac('sekme_kapat', 'Numarası verilen sekmeyi (verilmezse etkin sekmeyi) kapatır.',
      {'no': {'type': 'integer', 'minimum': 0, 'description': 'Sekme numarası'}}, [],
      risk=YAZMA, yan_etki=True, zaman_asimi=20)
def sekme_kapat(baglam, no=None):
    def is_():
        _T._ac()
        sayfalar = _T.baglam.pages
        hedef = _T.sayfa if no is None else (sayfalar[no] if no < len(sayfalar) else None)
        if hedef is None:
            return Sonuc(False, f'{no} numaralı sekme yok.', dogrulandi=False)
        once = len(sayfalar)
        hedef.close()
        kalan = _T.baglam.pages
        _T.sayfa = kalan[-1] if kalan else None
        return Sonuc(True, f'Sekme kapatıldı ({len(kalan)} sekme kaldı).', dogrulandi=len(kalan) == once - 1)
    return _T.calistir(is_, baglam, 20)


@arac('tarayici_indir', 'Açık sayfada metni verilen indirme bağlantısına/düğmesine tıklayıp dosyayı indirir ve doğrular.',
      {'metin': metin('İndirme bağlantısının görünen metni, ör. "PDF indir"'),
       'klasor': metin('Kaydedilecek klasör (varsayılan "İndirilenler")')},
      ['metin'], risk=YAZMA, yan_etki=True, yol_argumanlari=('klasor',), zaman_asimi=3600)
def tarayici_indir(baglam, metin, klasor='İndirilenler'):
    hedef_klasor = yollar.coz(klasor or 'İndirilenler')
    hedef_klasor.mkdir(parents=True, exist_ok=True)

    def is_():
        sayfa = _T._ac()
        oge = _bul(sayfa, metin)
        if oge is None:
            return Sonuc(False, f'"{metin}" adlı bir bağlantı bulamadım.', dogrulandi=False)
        with sayfa.expect_download(timeout=60000) as bilgi:
            oge.click()
        indirme = bilgi.value
        hedef = hedef_klasor / re.sub(r'[\\/:*?"<>|]', '_', indirme.suggested_filename)
        sayi = 1
        while hedef.exists():
            hedef = hedef_klasor / f'{Path(indirme.suggested_filename).stem} ({sayi}){Path(indirme.suggested_filename).suffix}'
            sayi += 1
        indirme.save_as(str(hedef))
        if indirme.failure():
            return Sonuc(False, f'İndirme başarısız: {indirme.failure()}', dogrulandi=False)
        boyut = hedef.stat().st_size if hedef.exists() else 0
        return Sonuc(boyut > 0, f'İndirildi: {hedef} ({boyut / 2**20:.2f} MB)', dogrulandi=boyut > 0,
                     veri={'yol': str(hedef)}, geri_al={'tur': 'cop_kutusuna', 'yol': str(hedef)})
    try:
        return _T.calistir(is_, baglam, 3600)
    except Iptal:
        raise
    except Exception as e:
        return Sonuc(False, f'İndirilemedi: {str(e).splitlines()[0][:200]}', dogrulandi=False)


def kapat() -> None:
    """Close the browser (used on shutdown and in tests)."""
    if _T.is_parcacigi and _T.is_parcacigi.is_alive():
        _T.isler.put((None, None))
        _T.is_parcacigi.join(10)
    _T.baglam = _T.sayfa = None
