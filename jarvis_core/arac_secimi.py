"""Pick the few tool schemas a request needs instead of sending all of them.

Small local models choose better among 6-12 tools than among 30, and the
prompt gets shorter (faster prompt eval). Selection is by Turkish word stems
(case and suffix tolerant). The model can always call `arac_katalogu` to see
every tool; after that the full catalogue is sent for the rest of the task
(controlled expansion). Follow-ups ("onu diğer klasöre taşı") keep the
previous request's groups. JARVIS_ARAC_SECIMI=0 turns selection off."""
import os
import re

from .niyet import kucuk

GRUPLAR = {
    'dosya': (r'dosya|klasör|belge|masaüst|indir|resim|müzik|video|taşı|kopyala|sil|adlandır|adını değiştir|kaydet|'
              r'pdf|docx|xlsx|txt|csv|uzantı|çöp|geri dönüşüm|oluştur|listele|neler var|yedek|fatura|rapor',
              ['dosya_ara', 'klasor_listele', 'dosya_oku', 'belge_oku', 'dosya_yaz', 'klasor_olustur', 'dosya_kopyala',
               'dosya_tasi', 'yeniden_adlandir', 'cop_kutusuna_gonder', 'son_islemi_geri_al']),
    'uygulama': (r'\baç\b|\baçar|kapat|uygulama|pencere|program|chrome|edge|firefox|word|excel|powerpoint|not defter|'
                 r'hesap makine|spotify|discord|steam|whatsapp|telegram|vs ?code|pano|yapıştır|yaz\b|yazar mısın',
                 ['uygulama_ac', 'uygulama_kapat', 'pencereleri_listele', 'pencereye_gec', 'metin_yaz', 'pano_oku',
                  'pano_yaz']),
    'web': (r'internet|ara\b|araştır|güncel|haber|son dakika|kimdir|nedir|ne zaman|kaç bitti|maç|fiyat|site|sayfa|'
            r'http|www\.|\.com|link|kaynak|wikipedia|vikipedi',
            ['internette_ara', 'web_sayfasi_oku', 'haberler']),
    'bilgi': (r'\bsaat\b|tarih (ne|kaç)|bugünün tarihi|günlerden|ayın kaçı|hava|derece|döviz|dolar|euro|\bkur\b|'
              r'sistem durumu|işlemci|bellek|\bram\b|\bpil\b|şarj|\bdisk\b',
              ['saat_tarih', 'hava_durumu', 'doviz_kuru', 'sistem_durumu']),
    'ekran': (r'ekran', ['ekrani_gor']),
    'hafiza': (r'hatırla|unut|hafıza|aklında|hakkımda|biliyor musun|adım\b|benim adım|tercih',
               ['hafizaya_kaydet', 'hafizayi_listele', 'hafizadan_unut']),
    'program': (r'çalıştır|git\b|commit|python|node|npm|pip|komut satırı|script|betik|derle|test|ipconfig|ping|'
                r'ollama|nvidia',
                ['program_calistir']),
    'geri_al': (r'geri al|eski haline|yanlış (klasör|yer)|düzelt', ['son_islemi_geri_al']),
    'hatirlatma': (r'hatırlat|alarm|zamanlayıcı|uyandır', ['hatirlatici_kur', 'hatirlatmalari_listele',
                                                          'hatirlatma_iptal']),
}
# When nothing matches (a chat question, or an unusual request) these are cheap and common.
VARSAYILAN = ['bilgi', 'web']
KESIF = 'arac_katalogu'
TAKIP = re.compile(r'^(onu|bunu|şunu|onları|bunları|aynısını|diğer|o dosya|bu dosya|peki|bir de|şimdi de|sonra)\b|'
                   r'\b(onu|bunu|onları|bunları)\b')


def gruplar(istek: str) -> list:
    k = kucuk(istek)
    return [ad for ad, (desen, _) in GRUPLAR.items() if re.search(desen, k)]


def sec(istek: str, onceki_gruplar: list = (), katalog=None) -> tuple:
    """(tool names, groups). `katalog` = names the model may see (modele_acik)."""
    secili = gruplar(istek)
    if TAKIP.search(kucuk(istek)) or len(kucuk(istek).split()) <= 3:
        secili = list(dict.fromkeys(secili + list(onceki_gruplar)))
    if not secili:
        secili = list(VARSAYILAN)
    adlar = []
    for g in secili:
        adlar += GRUPLAR[g][1]
    adlar.append(KESIF)
    adlar = list(dict.fromkeys(adlar))
    if katalog is not None:
        adlar = [a for a in adlar if a in katalog]
    return adlar, secili


def acik_mi() -> bool:
    return os.getenv('JARVIS_ARAC_SECIMI', '1') != '0'
