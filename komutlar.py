"""Fixed Turkish voice commands: a deterministic fast router.

It only decides *what* is wanted. Anything that touches the computer (or the
network) is returned as a Niyet and executed by the task engine's shared
executor, so fast commands get the same policy, approval, audit log, timeout
and cancel as the model's tool calls. Only canned replies (help, jokes) are
returned as plain text. Anything not matched goes to the model (local Ollama)."""
import random
import re

import sistem
from jarvis_core.niyet import Niyet
from jarvis_core.niyet import kucuk as _kucuk
from ses import dinle, konus

YARDIM = (
    'Şunları yapabilirim: saat ve tarih, hava durumu, haberler, döviz kuru, '
    'uygulama veya site açıp kapatmak, Google ve YouTube araması, YouTube\'dan şarkı çalmak, '
    'Vikipedi, ses ve parlaklık ayarı, ekran görüntüsü, sistem durumu, not almak ve okumak, '
    'hatırlatıcı kurmak, klasör açmak, dosyaları listelemek, yazı yazmak, kısayol tuşları, '
    'bilgisayarı kilitlemek, kapatmak, yeniden başlatmak ve uyutmak. '
    'Yapay zeka açıksa ayrıca internette arama yapabilir, ekranınıza bakabilir, dosyaları bulup taşıyabilir, '
    'program yazıp çalıştırabilir ve söylediklerinizi kalıcı olarak hatırlayabilirim; ne isterseniz söyleyin.'
)

SAKALAR = [
    'Temel ile Dursun bilgisayar almış. Temel sormuş: bunun virüsü var mı? Satıcı: yok. Temel: o zaman aşısını da verin.',
    'Programcı markete gitmiş. Eşi demiş ki: bir ekmek al, yumurta varsa altı tane al. Altı ekmekle dönmüş.',
    'Bilgisayarım bana satrançta yeniliyor, ama kickboks maçında ben kazanıyorum.',
    'Wi-Fi şifresi neydi diye sordum, küçük harflerle demişler. Hâlâ deniyorum: küçükharflerle.',
    'Bir yapay zeka kafeye girmiş, garson ne alırsınız demiş. Yapay zeka: siz ne öneriyorsanız, ama önce verilerinizi göreyim.',
]

CIKIS = ('görüşürüz', 'kapan jarvis', 'jarvis kapan', 'çıkış', 'hoşça kal', 'güle güle', 'uyu jarvis')


def kucuk(metin: str) -> str:
    # Turkish-aware lowercase: 'İ'.lower() would give 'i̇' (with a combining dot).
    return _kucuk(metin)


def _temizle(metin: str, *kelimeler: str) -> str:
    for k in kelimeler:
        metin = metin.replace(k, ' ')
    return re.sub(r'\s+', ' ', metin).strip(" .,'’")


def _ek_at(ad: str) -> str:
    """'chrome'u' -> 'chrome', 'spotify'ı' -> 'spotify'."""
    return re.sub(r"['’]\w*$", '', ad).strip()


def isle(metin: str, beyin) -> bool:
    """Handle one utterance (voice / text loop in jarvis.py). Returns False to quit."""
    k = kucuk(metin)
    if not k or k == 'none':
        return True
    k = re.sub(r'^(hey )?jarvis[, ]*', '', k) or k

    if any(c in k for c in CIKIS):
        konus('Görüşürüz efendim.')
        return False

    cevap = _yerel_komut(k, metin, beyin)
    if isinstance(cevap, Niyet):
        cevap = beyin.hizli(metin, cevap)
    elif cevap is None:
        cevap = beyin.sor(metin) if beyin.aktif else (
            'Bunu anlamadım efendim. Neler yapabildiğimi öğrenmek için "neler yapabilirsin" deyin.')
    if cevap:
        konus(cevap)
    return True


# Dictation: "şunu yaz: ..." / "yaz: ...". Checked before every other command, so the
# dictated text is never read as a command ("şunu yaz: bilgisayarı kapat").
DIKTE = re.compile(r'^\s*(?:hey\s+)?(?:jarvis[,\s]*)?(?:şunu\s+|bunu\s+)?yaz(?:ar mısın)?\s*[:,]\s*(.+)$|'
                   r'^\s*(?:hey\s+)?(?:jarvis[,\s]*)?şunu\s+yaz\s+(.+)$', re.IGNORECASE | re.DOTALL)


COK_AMACLI = re.compile(r'\b(ve|sonra|ardından|daha sonra|bir de|ayrıca)\b|,')
EYLEM = re.compile(r'\b(aç|kapat|çal|oynat|ara|arat|yaz|taşı|sil|kopyala|kaydet|oku|bul|göster|kur|başlat|'
                   r'listele|indir|gönder|hatırlat|kilitle)\b')


def _yerel_komut(k: str, ham: str, beyin=None):
    """A Niyet (tool + arguments) for the executor, a canned reply (str), or None
    when the request should go to the model."""
    ai_var = bool(getattr(beyin, 'aktif', False))

    dikte = DIKTE.match(ham)
    if dikte:
        return Niyet('aktif_pencereye_yaz', {'metin': (dikte.group(1) or dikte.group(2)).strip()})
    # Several actions in one sentence ("Chrome'u aç ve Tarkan çal"): a fixed command would
    # do only the first one, so the model plans it.
    if ai_var and COK_AMACLI.search(k) and len(EYLEM.findall(k)) >= 2:
        return None

    if ai_var and re.search(r'ekran(a|ı|da|daki)\b.*(bak|gör|ne var|oku|açıkla)|ekranda ne', k):
        return None  # the AI answers with its ekrani_gor tool
    # Long-term memory is saved here, not left to the model: small models often
    # say "I'll remember" without calling the tool. Source = the user's own words.
    if re.search(r'\b(unutma|aklında tut|aklında olsun|hatırla ki|bunu hatırla)\b', k) and 'hatırlat' not in k:
        bilgi = re.sub(r'[,.\s]*\b(bunu |şunu )?(unutma|aklında tut|aklında olsun|hatırla ki|hatırla)\b[,.!:\s]*',
                       ' ', ham, flags=re.IGNORECASE).strip(' ,.')
        if bilgi:
            return Niyet('hafizaya_kaydet', {'bilgi': bilgi, 'tur': 'tercih'}, 'Aklımda tutacağım efendim.')
    unut = re.match(r'^(?:şunu |bunu )?unut[:\s]+(.+)$|^(.+?)\s+(?:bilgisini\s+)?unut$', k)
    if unut:
        return Niyet('hafizadan_unut', {'parca': (unut.group(1) or unut.group(2)).strip()})
    if re.search(r'(benim hakkımda|hakkımda) (ne|neler) biliyorsun|hangi bilgileri (saklıyorsun|tutuyorsun)|'
                 r'neleri hatırlıyorsun', k):
        return Niyet('hafizayi_listele')
    if 'neler yapabilirsin' in k or k in ('yardım', 'komutlar'):
        return YARDIM
    if 'nasılsın' in k:
        return 'İyiyim efendim, teşekkür ederim. Size nasıl yardımcı olabilirim?'
    if 'adın ne' in k or 'sen kimsin' in k:
        return 'Ben JARVIS, kişisel asistanınız.'
    if 'teşekkür' in k or 'sağ ol' in k:
        return 'Rica ederim efendim.'

    # time / date
    if re.search(r'\bsaat kaç\b|\bsaat\b$|\btarih\b|günlerden ne|bugün ayın kaçı', k):
        return Niyet('saat_tarih')

    # info
    if 'hava' in k and ('durum' in k or 'nasıl' in k or 'kaç derece' in k or k.startswith('hava')):
        sehir = re.search(r"(\w+)['’]?(?:da|de|ta|te)\s+hava", k)
        return Niyet('hava_durumu', {'sehir': sehir.group(1) if sehir else ''})
    if re.search(r'\bhaber(ler|leri)?\b', k) and not re.search(r'\b(dosya|klasör)', k):
        return Niyet('haberler', {'adet': 5})
    # Exchange rate only when asked as a rate ("dolar kaç", "döviz kuru"), not for
    # "dolar geçen dosyayı bul".
    if re.search(r'\bdöviz\b|\b(dolar|euro|avro)\b.*\b(kaç|kur|kuru|ne kadar|fiyat|tl)\b|^(dolar|euro|avro)\??$', k) \
            and not re.search(r'\b(dosya|klasör|bul|ara|geçen)\b', k):
        return Niyet('doviz_kuru')
    if 'ip adres' in k:
        return Niyet('ip_adresi')
    if 'vikipedi' in k or 'wikipedia' in k:
        return Niyet('vikipedi', {'konu': _temizle(k, "vikipedi'de", "wikipedia'da", 'vikipedi', 'wikipedia', 'ara',
                                                   'nedir', 'kimdir')})
    if 'sistem durumu' in k or 'işlemci' in k or 'pil durumu' in k or 'şarj' in k or 'bellek' in k:
        return Niyet('sistem_durumu')
    if 'şaka' in k or 'fıkra' in k:
        return random.choice(SAKALAR)

    # media / search
    if 'youtube' in k and ('indir' in k):
        return Niyet('youtube_indirici_ac')
    if re.search(r'\b(çal|oynat)\b', k):
        sorgu = _temizle(k, "youtube'da", 'youtubeda', 'youtube', 'şarkısını', 'şarkı', 'müziğini', 'videosunu', 'çal', 'oynat')
        return Niyet('youtube_cal', {'sorgu': sorgu}) if sorgu else 'Ne çalayım efendim?'
    if 'youtube' in k and 'ara' in k:
        return Niyet('youtube_ara', {'sorgu': _temizle(k, "youtube'da", 'youtubeda', 'youtube', 'ara', 'arat')})
    # With an AI the "search the internet" requests get a spoken answer instead of a browser tab.
    if re.search(r"\b(google'da|googleda)\b.*\bara", k) or (
            not ai_var and (re.search(r'\binternette(n)?\b.*\bara', k) or re.search(r'\b(ara|arat)$', k))):
        return Niyet('google_ara', {'sorgu': _temizle(k, "google'da", 'googleda', 'internetten', 'internette', 'arat',
                                                      'ara', ',')})

    # sound / screen
    if re.search(r'\bses(i|ini)?\b', k) and any(w in k for w in ('aç', 'artır', 'yükselt', 'kıs', 'azalt', 'düşür',
                                                                   'kapat', 'sessiz')):
        if any(w in k for w in ('kapat', 'sessiz')):
            return Niyet('ses_ayarla', {'islem': 'sessiz', 'adim': 1})
        return Niyet('ses_ayarla', {'islem': 'artır' if any(w in k for w in ('aç', 'artır', 'yükselt')) else 'azalt',
                                    'adim': 5})
    if k == 'sessiz' or 'sessize al' in k:
        return Niyet('ses_ayarla', {'islem': 'sessiz', 'adim': 1})
    if 'parlaklı' in k:
        sayi = re.search(r'\d+', k)
        yuzde = int(sayi.group()) if sayi else (100 if any(w in k for w in ('artır', 'aç', 'yükselt')) else 30)
        return Niyet('parlaklik_ayarla', {'yuzde': max(0, min(100, yuzde))})
    if 'ekran görüntüsü' in k:
        return Niyet('ekran_goruntusu_al')
    if 'masaüstünü göster' in k or 'pencereleri küçült' in k:
        return Niyet('masaustunu_goster')

    # notes / reminders
    if 'not al' in k or 'not et' in k:
        icerik = _temizle(k, 'not al', 'not et', 'şunu', ':')
        if not icerik:
            konus('Ne not alayım?')
            icerik = dinle()
        return Niyet('not_al', {'metin': icerik}) if icerik else 'Not almadım.'
    if 'notları sil' in k or 'notlarımı sil' in k:
        return Niyet('notlari_sil')
    if 'notlar' in k and ('oku' in k or 'neler' in k or 'göster' in k):
        return Niyet('notlari_oku')
    if re.search(r'hatırlat|zamanlayıcı|alarm', k) and not re.search(r'hatırlatmalar|listele|iptal', k):
        from jarvis_core.zamanlayici import zaman_coz
        hedef = zaman_coz(k)
        if hedef is not None:
            mesaj = re.sub(r"(\d+(?:[.,]\d+)?)\s*(saniye|dakika|saat)\s*sonra|\b(yarın|bugün|öbür gün)\b|"
                           r"\bsaat\s*\d{1,2}(?:[:.]\d{2})?(?:'?(?:de|da|te|ta))?|\b\d{1,2}[:.]\d{2}(?:'?(?:de|da|te|ta))?|"
                           r"\b(bana|hatırlat|hatırlatır mısın|zamanlayıcı|alarm|kur|diye|lütfen|jarvis)\b", ' ', k)
            mesaj = re.sub(r"\b\d{1,2}'?(?:de|da|te|ta)\b|\b(?:de|da|te|ta)\b|\bher (?:gün|sabah|akşam|hafta)\b", ' ',
                           mesaj)
            mesaj = re.sub(r'\s+', ' ', mesaj).strip(" .,'’")
            tekrar = 'gunluk' if re.search(r'her gün|her sabah|her akşam', k) else (
                'haftalik' if 'her hafta' in k else 'yok')
            return Niyet('hatirlatici_kur', {'zaman': hedef.strftime('%Y-%m-%d %H:%M'), 'mesaj': mesaj or 'süre doldu',
                                             'tekrar': tekrar})
    if re.search(r'hatırlatmalar\w*.*(neler|listele|göster|oku)|hangi hatırlatma', k):
        return Niyet('hatirlatmalari_listele')

    # power
    if 'kilitle' in k:
        return Niyet('bilgisayari_kilitle')
    if 'yeniden başlat' in k:
        return Niyet('yeniden_baslat')
    if 'uyku mod' in k or 'bilgisayarı uyut' in k:
        return Niyet('uyku_moduna_al')
    if re.search(r'bilgisayar\w* kapat', k):
        return Niyet('bilgisayari_kapat')

    # keyboard / undo: "geri al" alone is the active app's Ctrl+Z; JARVIS's own last
    # file action is undone with "son işlemi / görevi geri al".
    if re.search(r'\b(son işlemi|son işlemini|görevi|yaptığını|dosya işlemini)\s+geri al', k):
        return Niyet('son_islemi_geri_al')
    if 'panoyu oku' in k or 'panoda ne var' in k:
        return Niyet('pano_oku')
    if 'kopyala' == k:
        return Niyet('tus_bas', {'tuslar': 'ctrl+c'})
    if 'yapıştır' == k:
        return Niyet('tus_bas', {'tuslar': 'ctrl+v'})
    if 'geri al' == k:
        return Niyet('tus_bas', {'tuslar': 'ctrl+z'})
    if 'kaydet' == k:
        return Niyet('tus_bas', {'tuslar': 'ctrl+s'})
    if 'pencere değiştir' in k:
        return Niyet('tus_bas', {'tuslar': 'alt+tab'})

    # folders
    klasor = re.search(r'(masaüstü|indirilenler|belgeler|resimler|müzik|videolar)\w*\s+(?:klasörünü\s+)?(aç|listele|neler var)', k)
    if klasor:
        if klasor.group(2) == 'aç':
            return Niyet('klasor_ac', {'klasor': klasor.group(1)})
        return Niyet('klasor_ozeti', {'klasor': klasor.group(1)})

    # close an app
    kapat = re.match(r'^(.+?)\s+(?:uygulamasını\s+)?kapat$', k)
    if kapat:
        return Niyet('uygulama_kapat', {'ad': _ek_at(kapat.group(1))})

    # open a site or an app
    ac = re.match(r'^(.+?)\s+(?:uygulamasını\s+|sitesini\s+)?(?:aç|başlat|çalıştır)$', k)
    if ac:
        hedef = _ek_at(ac.group(1))
        if re.search(r'\.\w{2,}', hedef) or hedef in sistem.SITELER:
            return Niyet('web_sitesi_ac', {'adres': hedef})
        # Unknown names ("kapıyı aç", "son indirdiğim dosyayı aç") are better left to the AI.
        if sistem.uygulama_bul(hedef) or not ai_var:
            return Niyet('uygulama_ac', {'ad': hedef})

    return None
