"""Long-term memory tools (stored in SQLite with source and date)."""
from ..izinler import OKUMA, YAZMA
from .temel import Sonuc, arac, metin


@arac('hafizaya_kaydet', 'Kullanıcının açıkça hatırlanmasını istediği bir bilgiyi kalıcı hafızaya kaydeder.',
      {'bilgi': metin('Kısa, net bir cümle, ör. "Kullanıcının adı Batuhan."'),
       'tur': {'type': 'string', 'enum': ['tercih', 'kisisel', 'proje'], 'description': 'Bilgi türü'}},
      ['bilgi', 'tur'], risk=YAZMA, yan_etki=True)
def hafizaya_kaydet(baglam, bilgi, tur):
    kayit = baglam.depo.hafiza_ekle(bilgi, kaynak='görev sırasında yapay zeka', tur=tur)
    return Sonuc(True, f'Kaydedildi (#{kayit}).', dogrulandi=True)


@arac('hafizayi_listele', 'Kalıcı hafızadaki bilgileri tarih ve kaynaklarıyla listeler.', {}, [],
      risk=OKUMA, yan_etki=False)
def hafizayi_listele(baglam):
    import time
    kayitlar = baglam.depo.hafiza()
    if not kayitlar:
        return Sonuc(True, 'Hafıza boş.')
    return Sonuc(True, '\n'.join(f"#{k['id']} [{k['tur']}, {time.strftime('%d.%m.%Y', time.localtime(k['tarih']))}, "
                                 f"{k['kaynak']}] {k['metin']}" for k in kayitlar))


@arac('hafizadan_unut', 'Kalıcı hafızadan, verilen metni içeren bilgileri siler.',
      {'parca': metin('Unutulacak bilginin bir parçası')}, ['parca'], risk=YAZMA, yan_etki=True)
def hafizadan_unut(baglam, parca):
    adet = baglam.depo.hafiza_unut(parca)
    return Sonuc(True, f'{adet} bilgi unutuldu.', dogrulandi=True)
