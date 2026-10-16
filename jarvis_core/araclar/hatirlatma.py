"""Reminder tools backed by the persistent scheduler (zamanlayici.py)."""
import datetime as dt

from ..izinler import OKUMA, YAZMA
from .temel import Sonuc, arac, metin


def _zamanlayici(baglam):
    from ..zamanlayici import Zamanlayici
    return Zamanlayici(baglam.depo)


def _zaman(dakika, zaman):
    from ..zamanlayici import saat_dilimi, zaman_coz
    if dakika:
        return dt.datetime.now(saat_dilimi()) + dt.timedelta(minutes=float(dakika))
    try:
        return dt.datetime.strptime(zaman.strip(), '%Y-%m-%d %H:%M').replace(tzinfo=saat_dilimi())
    except (ValueError, AttributeError):
        return zaman_coz(zaman or '')


@arac('hatirlatici_kur', 'Belirtilen zamanda sesli hatırlatma kurar; JARVIS kapanıp açılsa da kaybolmaz. '
      'dakika (ör. 10) ya da zaman (ör. "yarın 09:00", "2026-10-17 15:30", "saat 18") ver.',
      {'mesaj': metin('Hatırlatılacak şey'),
       'dakika': {'type': 'number', 'exclusiveMinimum': 0, 'maximum': 527040, 'description': 'Kaç dakika sonra'},
       'zaman': metin('Ne zaman: "yarın 09:00", "saat 18:30" veya "YYYY-AA-GG SS:DD"'),
       'tekrar': {'type': 'string', 'enum': ['yok', 'gunluk', 'haftalik'], 'description': 'Tekrar'}},
      ['mesaj'], risk=YAZMA, yan_etki=True, tekrarlanabilir=True)
def hatirlatici_kur(baglam, mesaj, dakika=None, zaman='', tekrar='yok'):
    hedef = _zaman(dakika, zaman)
    if hedef is None:
        return Sonuc(False, 'Hatırlatma zamanını anlayamadım; "10 dakika sonra" veya "yarın 09:00" gibi söyleyin.',
                     dogrulandi=False, hata_turu='zaman')
    if hedef.timestamp() < dt.datetime.now(hedef.tzinfo).timestamp() - 60:
        return Sonuc(False, f'{hedef:%d.%m.%Y %H:%M} geçmişte kalıyor.', dogrulandi=False, hata_turu='zaman')
    z = _zamanlayici(baglam)
    kayit = z.ekle(hedef.timestamp(), mesaj or 'süre doldu', tekrar)
    dogru = z.kayit(kayit['id']) is not None
    return Sonuc(dogru, f"Tamam, {kayit['metin_ozet']} için hatırlatma kuruldu: {mesaj}.", dogrulandi=dogru,
                 veri={'hatirlatma_id': kayit['id'], 'zaman': kayit['zaman']})


@arac('hatirlatmalari_listele', 'Bekleyen hatırlatmaları tarih ve saatleriyle listeler.', {}, [],
      risk=OKUMA, yan_etki=False)
def hatirlatmalari_listele(baglam):
    from ..zamanlayici import yerel_metin
    bekleyen = _zamanlayici(baglam).bekleyenler()
    if not bekleyen:
        return Sonuc(True, 'Bekleyen hatırlatma yok.')
    return Sonuc(True, '\n'.join(f"#{k['id']} {yerel_metin(k['zaman'])}"
                                 f"{' (' + k['tekrar'] + ')' if k['tekrar'] != 'yok' else ''}: {k['metin']}"
                                 for k in bekleyen))


@arac('hatirlatma_iptal', 'Numarası verilen hatırlatmayı iptal eder.',
      {'numara': {'type': 'integer', 'minimum': 1, 'description': 'Hatırlatma numarası (listeden)'}}, ['numara'],
      risk=YAZMA, yan_etki=True)
def hatirlatma_iptal(baglam, numara):
    z = _zamanlayici(baglam)
    if not z.iptal(numara):
        return Sonuc(False, f'#{numara} numaralı bekleyen hatırlatma yok.', dogrulandi=False, hata_turu='bulunamadi')
    return Sonuc(True, f'#{numara} iptal edildi.', dogrulandi=z.kayit(numara)['durum'] == 'iptal')
