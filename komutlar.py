"""Fixed Turkish voice commands. Anything not matched here goes to Gemini
(when an API key is set), which saves the small free-tier quota."""
import random
import re

import sistem
from ses import dinle, konus

YARDIM = (
    'Şunları yapabilirim: saat ve tarih, hava durumu, haberler, döviz kuru, '
    'uygulama veya site açıp kapatmak, Google ve YouTube araması, YouTube\'dan şarkı çalmak, '
    'Vikipedi, ses ve parlaklık ayarı, ekran görüntüsü, sistem durumu, not almak ve okumak, '
    'hatırlatıcı kurmak, klasör açmak, dosyaları listelemek, yazı yazmak, kısayol tuşları, '
    'bilgisayarı kilitlemek, kapatmak, yeniden başlatmak ve uyutmak. '
    'Yapay zeka açıksa aklınıza gelen her şeyi sorabilir ya da bilgisayarda yaptırabilirsiniz.'
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
    return metin.replace('İ', 'i').replace('I', 'ı').lower().strip()


def _temizle(metin: str, *kelimeler: str) -> str:
    for k in kelimeler:
        metin = metin.replace(k, ' ')
    return re.sub(r'\s+', ' ', metin).strip(" .,'’")


def _ek_at(ad: str) -> str:
    """'chrome'u' -> 'chrome', 'spotify'ı' -> 'spotify'."""
    return re.sub(r"['’]\w*$", '', ad).strip()


def isle(metin: str, beyin) -> bool:
    """Handle one utterance. Returns False when the user wants to quit."""
    k = kucuk(metin)
    if not k or k == 'none':
        return True
    k = re.sub(r'^(hey )?jarvis[, ]*', '', k) or k

    if any(c in k for c in CIKIS):
        konus('Görüşürüz efendim.')
        return False

    cevap = _yerel_komut(k, metin)
    if cevap is None:
        cevap = beyin.sor(metin) if beyin.aktif else (
            'Bunu anlamadım efendim. Neler yapabildiğimi öğrenmek için "neler yapabilirsin" deyin.')
    if cevap:
        konus(cevap)
    return True


def _yerel_komut(k: str, ham: str):
    """Return the spoken answer, or None if no fixed command matched."""
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
        return sistem.saat_tarih()

    # info
    if 'hava' in k and ('durum' in k or 'nasıl' in k or 'kaç derece' in k or k.startswith('hava')):
        sehir = re.search(r"(\w+)['’]?(?:da|de|ta|te)\s+hava", k)
        return sistem.hava_durumu(sehir.group(1) if sehir else '')
    if 'haber' in k:
        return sistem.haberler(5)
    if 'dolar' in k or 'euro' in k or 'döviz' in k:
        return sistem.doviz_kuru()
    if 'ip adres' in k:
        return sistem.ip_adresi()
    if 'vikipedi' in k or 'wikipedia' in k:
        return sistem.vikipedi(_temizle(k, "vikipedi'de", "wikipedia'da", 'vikipedi', 'wikipedia', 'ara', 'nedir', 'kimdir'))
    if 'sistem durumu' in k or 'işlemci' in k or 'pil durumu' in k or 'şarj' in k or 'bellek' in k:
        return sistem.sistem_durumu()
    if 'şaka' in k or 'fıkra' in k:
        return random.choice(SAKALAR)

    # media / search
    if 'youtube' in k and ('indir' in k):
        return sistem.youtube_indirici_ac()
    if re.search(r'\b(çal|oynat)\b', k):
        sorgu = _temizle(k, "youtube'da", 'youtubeda', 'youtube', 'şarkısını', 'şarkı', 'müziğini', 'videosunu', 'çal', 'oynat')
        return sistem.youtube_cal(sorgu) if sorgu else 'Ne çalayım efendim?'
    if 'youtube' in k and 'ara' in k:
        return sistem.youtube_ara(_temizle(k, "youtube'da", 'youtubeda', 'youtube', 'ara', 'arat'))
    if re.search(r"\b(google'da|googleda|internette)\b.*\bara", k) or re.search(r'\b(ara|arat)$', k):
        return sistem.google_ara(_temizle(k, "google'da", 'googleda', 'internette', 'arat', 'ara'))

    # sound / screen
    if 'ses' in k and any(w in k for w in ('aç', 'artır', 'yükselt', 'kıs', 'azalt', 'düşür', 'kapat', 'sessiz')):
        if any(w in k for w in ('kapat', 'sessiz')):
            return sistem.ses_ayarla('sessiz', 1)
        return sistem.ses_ayarla('artır' if any(w in k for w in ('aç', 'artır', 'yükselt')) else 'azalt', 5)
    if k == 'sessiz' or 'sessize al' in k:
        return sistem.ses_ayarla('sessiz', 1)
    if 'parlaklı' in k:
        sayi = re.search(r'\d+', k)
        if sayi:
            return sistem.parlaklik_ayarla(int(sayi.group()))
        return sistem.parlaklik_ayarla(100 if any(w in k for w in ('artır', 'aç', 'yükselt')) else 30)
    if 'ekran görüntüsü' in k:
        return sistem.ekran_goruntusu_al()
    if 'masaüstünü göster' in k or 'pencereleri küçült' in k:
        return sistem.masaustunu_goster()

    # notes / reminders
    if 'not al' in k or 'not et' in k:
        icerik = _temizle(k, 'not al', 'not et', 'şunu', ':')
        if not icerik:
            konus('Ne not alayım?')
            icerik = dinle()
        return sistem.not_al(icerik) if icerik else 'Not almadım.'
    if 'notları sil' in k or 'notlarımı sil' in k:
        return sistem.notlari_sil()
    if 'notlar' in k and ('oku' in k or 'neler' in k or 'göster' in k):
        return sistem.notlari_oku()
    sure = re.search(r'(\d+(?:[.,]\d+)?)\s*(saniye|dakika|saat)', k)
    if sure and any(w in k for w in ('hatırlat', 'zamanlayıcı', 'alarm', 'sonra', 'kur')):
        miktar = float(sure.group(1).replace(',', '.'))
        dakika = {'saniye': miktar / 60, 'dakika': miktar, 'saat': miktar * 60}[sure.group(2)]
        mesaj = _temizle(k[sure.end():], 'sonra', 'bana', 'hatırlat', 'zamanlayıcı', 'alarm', 'kur', 'diye')
        return sistem.hatirlatici_kur(dakika, mesaj)

    # power
    if 'kilitle' in k:
        return sistem.bilgisayari_kilitle()
    if 'yeniden başlat' in k:
        return sistem.yeniden_baslat()
    if 'uyku mod' in k or 'bilgisayarı uyut' in k:
        return sistem.uyku_moduna_al()
    if re.search(r'bilgisayar\w* kapat', k):
        return sistem.bilgisayari_kapat()

    # keyboard
    if 'panoyu oku' in k or 'panoda ne var' in k:
        return sistem.panoyu_oku()
    if re.match(r'^(?:şunu )?yaz[:\s]+\S', k):
        # Type the original text so capital letters survive.
        yazi = re.match(r'^\s*(?:hey\s+)?(?:jarvis[,\s]*)?(?:şunu\s+)?yaz[:\s]+(.+)', ham, re.IGNORECASE)
        return sistem.metin_yaz(yazi.group(1) if yazi else k.split(' ', 1)[1])
    if 'kopyala' == k:
        return sistem.tus_bas('ctrl+c')
    if 'yapıştır' == k:
        return sistem.tus_bas('ctrl+v')
    if 'geri al' == k:
        return sistem.tus_bas('ctrl+z')
    if 'kaydet' == k:
        return sistem.tus_bas('ctrl+s')
    if 'pencere değiştir' in k:
        return sistem.tus_bas('alt+tab')

    # folders
    klasor = re.search(r'(masaüstü|indirilenler|belgeler|resimler|müzik|videolar)\w*\s+(?:klasörünü\s+)?(aç|listele|neler var)', k)
    if klasor:
        if klasor.group(2) == 'aç':
            return sistem.klasor_ac(klasor.group(1))
        return sistem.dosyalari_listele(klasor.group(1))

    # close an app
    kapat = re.match(r'^(.+?)\s+(?:uygulamasını\s+)?kapat$', k)
    if kapat:
        return sistem.uygulama_kapat(_ek_at(kapat.group(1)))

    # open a site or an app
    ac = re.match(r'^(.+?)\s+(?:uygulamasını\s+|sitesini\s+)?(?:aç|başlat|çalıştır)$', k)
    if ac:
        hedef = _ek_at(ac.group(1))
        if re.search(r'\.\w{2,}', hedef) or hedef in sistem.SITELER:
            return sistem.web_sitesi_ac(hedef)
        return sistem.uygulama_ac(hedef)

    return None
