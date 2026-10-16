"""Tool routing: the model only sees the tool groups a request needs.

All 40+ tool schemas cost ~5.5k prompt tokens, which leaves little room in
an 8k context. A small core set is always sent; other groups are added by
keywords in the request (and recent conversation), and the model can open
more with the `araclari_ac` meta-tool when it realises it needs them."""
import re

GRUPLAR = {
    'temel': ['saat_tarih', 'dosya_ara', 'klasor_listele', 'dosya_oku', 'dosya_yaz', 'son_islemi_geri_al',
              'uygulama_ac', 'hafizaya_kaydet'],
    'dosya': ['klasor_olustur', 'dosya_kopyala', 'dosya_tasi', 'yeniden_adlandir', 'cop_kutusuna_gonder'],
    'uygulama': ['uygulama_kapat', 'pencereleri_listele', 'pencereye_gec', 'metin_yaz', 'pano_oku', 'pano_yaz'],
    'bilgi': ['sistem_durumu', 'hava_durumu', 'doviz_kuru', 'haberler', 'internette_ara', 'web_sayfasi_oku'],
    'belge': ['belge_oku', 'rapor_yaz'],
    'indirme': ['dosya_indir', 'dosya_ac'],
    'tarayici': ['tarayici_git', 'tarayici_ara', 'sayfa_oku', 'tarayici_tikla', 'tarayici_yaz', 'sekmeler',
                 'sekme_sec', 'sekme_kapat', 'tarayici_indir'],
    'sistem': ['program_calistir', 'ekrani_gor'],
    'hafiza': ['hafizayi_listele', 'hafizadan_unut'],
}
ACIKLAMALAR = {
    'dosya': 'taşıma, kopyalama, yeniden adlandırma, klasör oluşturma, silme',
    'uygulama': 'uygulama kapatma, pencereler, metin yazma, pano',
    'bilgi': 'internette arama, web sayfası okuma, hava, haber, döviz, sistem durumu',
    'belge': 'PDF/Word/Excel okuma, rapor yazma',
    'indirme': 'bağlantıdan dosya indirme, dosya açma',
    'tarayici': 'tarayıcıyı yönetme: siteye gitme, sayfa okuma, tıklama, form doldurma, sekmeler',
    'sistem': 'program çalıştırma (git vb.), ekranı görme',
    'hafiza': 'kalıcı hafızayı listeleme ve silme',
}
ANAHTARLAR = {
    'dosya': r'taşı|tasi|kopyala|yeniden adlandır|adını değiştir|klasör oluştur|yeni klasör|(?<!\w)sil|çöp|geri dönüşüm|'
             r'(?<!\w)koy\b|yerleştir|diğer klasör',
    'uygulama': r'(?<!\w)kapat|pencere|(?<!\w)yaz\b|yazı yaz|pano|kopyalanan|odakla|(?<!\w)geç\b',
    'bilgi': r'(?<!\w)hava|(?<!\w)haber|döviz|dolar|euro|(?<!\w)kur\b|internet|(?<!\w)ara\b|(?<!\w)arat|(?<!\w)güncel|son dakika|kimdir|nedir|ne zaman|kaç tl|'
             r'(?<!\w)fiyat|sistem durumu|işlemci|(?<!\w)ram|bellek|(?<!\w)pil|(?<!\w)maç|skor',
    'belge': r'pdf|word|excel|docx|xlsx|csv|belge|rapor|özetle|özet çıkar|(?<!\w)tablo|döküman|doküman',
    'indirme': r'(?<!\w)indir|bağlantı|(?<!\w)link|https?://|\.(pdf|zip|exe|mp4|mp3|docx|xlsx)\b|(?<!\w)aç\b',
    'tarayici': r'tarayıcı|(?<!\w)site|(?<!\w)sayfa|(?<!\w)sekme|tıkla|google|edge|form|giriş yap|(?<!\w)üye|alışveriş|sepet|trendyol|'
                r'hepsiburada|youtube|instagram|twitter|(?<!\w)web\b|www\.|\.com',
    'sistem': r'(?<!\w)program|(?<!\w)komut|(?<!\w)git\b|terminal|(?<!\w)ekran|ekranda|görüntü',
    'hafiza': r'hafıza|unut|hatırla|bildiklerin|saklıyorsun',
}


def sec(metin: str) -> set:
    k = (metin or '').replace('İ', 'i').replace('I', 'ı').lower()
    return {'temel'} | {g for g, desen in ANAHTARLAR.items() if re.search(desen, k)}


def araclar(gruplar: set) -> list:
    adlar = []
    for g in GRUPLAR:
        if g in gruplar:
            adlar += GRUPLAR[g]
    return adlar


def grup_bul(arac_adi: str):
    return next((g for g, adlar in GRUPLAR.items() if arac_adi in adlar), None)


META = {'type': 'function', 'function': {
    'name': 'araclari_ac',
    'description': 'Gereken araçlar listede yoksa ek araç gruplarını açar. Gruplar: '
                   + '; '.join(f'{g} ({a})' for g, a in ACIKLAMALAR.items()),
    'parameters': {'type': 'object', 'additionalProperties': False, 'required': ['gruplar'],
                   'properties': {'gruplar': {'type': 'array', 'items': {'type': 'string', 'enum': list(ACIKLAMALAR)},
                                              'description': 'Açılacak gruplar'}}}}}
