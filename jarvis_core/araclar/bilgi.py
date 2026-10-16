"""Read-only information tools. Internet results are marked untrusted: they
are shown to the model as data, never as instructions."""
from ..izinler import OKUMA
from .temel import Sonuc, arac, metin


def _sistem():
    import sistem
    return sistem


def _sar(cikti: str, hata_kaliplari=('alamadım', 'ulaşamıyorum', 'ulaşamadım', 'öğrenemedim', 'bulamadım')) -> Sonuc:
    return Sonuc(not any(k in cikti for k in hata_kaliplari), cikti)


@arac('saat_tarih', 'Şu anki saati, tarihi ve günü verir.', {}, [], risk=OKUMA, yan_etki=False)
def saat_tarih(baglam):
    return Sonuc(True, _sistem().saat_tarih())


@arac('sistem_durumu', 'İşlemci, bellek, disk ve pil durumunu verir.', {}, [], risk=OKUMA, yan_etki=False)
def sistem_durumu(baglam):
    return Sonuc(True, _sistem().sistem_durumu())


@arac('hava_durumu', 'Bir şehrin şu anki hava durumunu verir.', {'sehir': metin('Şehir adı, boşsa varsayılan şehir')},
      ['sehir'], risk=OKUMA, yan_etki=False)
def hava_durumu(baglam, sehir):
    return _sar(_sistem().hava_durumu(sehir))


@arac('doviz_kuru', 'Güncel dolar ve euro kurunu (TL) verir.', {}, [], risk=OKUMA, yan_etki=False)
def doviz_kuru(baglam):
    return _sar(_sistem().doviz_kuru())


@arac('haberler', 'Türkiye\'den güncel haber başlıklarını verir.',
      {'adet': {'type': 'integer', 'minimum': 1, 'maximum': 15, 'description': 'Başlık sayısı'}},
      ['adet'], risk=OKUMA, yan_etki=False, guvenilmez_cikti=True)
def haberler(baglam, adet):
    return _sar(_sistem().haberler(adet))


@arac('internette_ara', 'İnternette arama yapar; başlık, özet ve adresleri döndürür. Güncel bilgi gereken '
      'her soruda kullan ve cevapta kaynak sitenin adını söyle.',
      {'sorgu': metin('Arama metni')}, ['sorgu'], risk=OKUMA, yan_etki=False, zaman_asimi=30,
      guvenilmez_cikti=True)
def internette_ara(baglam, sorgu):
    try:
        from ddgs import DDGS
        sonuclar = DDGS(timeout=15).text(sorgu, region='tr-tr', max_results=6)
    except Exception as e:
        return Sonuc(False, f'Arama yapılamadı (internet bağlantısı?): {e}')
    if not sonuclar:
        return Sonuc(True, 'Sonuç bulunamadı.')
    return Sonuc(True, '\n'.join(f"- {r['title']}: {r['body']} [{r['href']}]" for r in sonuclar),
                 veri={'kaynaklar': [r['href'] for r in sonuclar]})


@arac('web_sayfasi_oku', 'Bir web sayfasının düz metnini okur (ilk 6000 karakter).',
      {'adres': metin('Tam adres, https://...', pattern='^https?://')}, ['adres'],
      risk=OKUMA, yan_etki=False, zaman_asimi=30, guvenilmez_cikti=True)
def web_sayfasi_oku(baglam, adres):
    import re
    from bs4 import BeautifulSoup
    from ..ag import AgHatasi, getir
    izinli = tuple(baglam.izinler.veri.get('izinli_aglar', [])) if baglam.izinler else ()
    try:
        html, son_adres, _ = getir(adres, izinli_hostlar=izinli, iptal=baglam.iptal)
    except AgHatasi as e:
        return Sonuc(False, str(e), hata_turu='ag')
    sayfa = BeautifulSoup(html, 'html.parser')
    for etiket in sayfa(['script', 'style', 'nav', 'footer', 'noscript']):
        etiket.decompose()
    metin = re.sub(r'\n\s*\n+', '\n', sayfa.get_text('\n')).strip()[:6000]
    return Sonuc(True, metin, veri={'kaynak': son_adres})
