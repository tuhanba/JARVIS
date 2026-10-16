"""Tools behind the fast (model-free) voice and panel commands.

They wrap the legacy functions in sistem.py so that a fast command runs
through the same executor as the model: policy, approval, step log, timeout
and cancel. They are not offered to the model (modele_acik=False); power and
hotkey actions stay a direct user command. Where nothing observable can be
checked (a volume key press), the result is 'succeeded', not 'verified', and
the spoken text says what was done, not what was achieved."""
import datetime
from pathlib import Path

from .. import yollar
from ..izinler import OKUMA, SILME, SISTEM, YAZMA
from .temel import Sonuc, arac, metin


def _sistem():
    import sistem
    return sistem


def _hizli(ad, aciklama, ozellikler, gerekli, risk, yan_etki, **ek):
    return arac(ad, aciklama, ozellikler, gerekli, risk=risk, yan_etki=yan_etki, modele_acik=False, **ek)


# ------------------------------------------------------------------ browser / media

@_hizli('web_sitesi_ac', 'Bir siteyi varsayılan tarayıcıda açar.', {'adres': metin('Site adı veya adresi')},
        ['adres'], YAZMA, True, tekrarlanabilir=True)
def web_sitesi_ac(baglam, adres):
    return Sonuc(True, _sistem().web_sitesi_ac(adres))


@_hizli('google_ara', 'Google araması açar.', {'sorgu': metin('Aranacak metin')}, ['sorgu'], YAZMA, True,
        tekrarlanabilir=True)
def google_ara(baglam, sorgu):
    return Sonuc(True, _sistem().google_ara(sorgu))


@_hizli('youtube_ara', 'YouTube araması açar.', {'sorgu': metin('Aranacak metin')}, ['sorgu'], YAZMA, True,
        tekrarlanabilir=True)
def youtube_ara(baglam, sorgu):
    return Sonuc(True, _sistem().youtube_ara(sorgu))


@_hizli('youtube_cal', "YouTube'da bir şarkı veya videoyu açar.", {'sorgu': metin('Şarkı veya video')}, ['sorgu'],
        YAZMA, True, tekrarlanabilir=True, zaman_asimi=30)
def youtube_cal(baglam, sorgu):
    cikti = _sistem().youtube_cal(sorgu)
    return Sonuc('bulamadım' not in cikti and 'açamadım' not in cikti, cikti)


@_hizli('youtube_indirici_ac', 'YouTube indirici penceresini açar.', {}, [], YAZMA, True, tekrarlanabilir=True)
def youtube_indirici_ac(baglam):
    return Sonuc(True, _sistem().youtube_indirici_ac())


@_hizli('klasor_ac', 'Bir klasörü dosya gezgininde açar.', {'klasor': metin('Klasör adı')}, ['klasor'], YAZMA, True,
        tekrarlanabilir=True)
def klasor_ac(baglam, klasor):
    cikti = _sistem().klasor_ac(klasor)
    return Sonuc('bulunamadı' not in cikti and 'yok' not in cikti, cikti)


# ------------------------------------------------------------------ info

@_hizli('vikipedi', "Vikipedi'den kısa özet okur.", {'konu': metin('Konu')}, ['konu'], OKUMA, False,
        guvenilmez_cikti=True, zaman_asimi=20)
def vikipedi(baglam, konu):
    cikti = _sistem().vikipedi(konu)
    return Sonuc(not any(k in cikti for k in ('bulamadım', 'ulaşamadım', 'ulaşamıyorum')), cikti)


@_hizli('ip_adresi', 'Bilgisayarın IP adresini söyler.', {}, [], OKUMA, False, zaman_asimi=15)
def ip_adresi(baglam):
    return Sonuc(True, _sistem().ip_adresi())


@_hizli('klasor_ozeti', 'Bir klasördeki dosyaları kısaca söyler.', {'klasor': metin('Klasör adı')}, ['klasor'],
        OKUMA, False)
def klasor_ozeti(baglam, klasor):
    cikti = _sistem().dosyalari_listele(klasor)
    return Sonuc('bulunamadı' not in cikti, cikti)


# ------------------------------------------------------------------ sound / screen / keyboard

@_hizli('ses_ayarla', 'Ses seviyesini değiştirir.',
        {'islem': {'type': 'string', 'enum': ['artır', 'azalt', 'sessiz']},
         'adim': {'type': 'integer', 'minimum': 1, 'maximum': 50}}, ['islem', 'adim'], YAZMA, True,
        tekrarlanabilir=True)
def ses_ayarla(baglam, islem, adim):
    _sistem().ses_ayarla(islem, adim)
    return Sonuc(True, {'artır': 'Ses açma tuşuna basıldı.', 'azalt': 'Ses kısma tuşuna basıldı.',
                        'sessiz': 'Sessiz tuşuna basıldı.'}[islem])


@_hizli('parlaklik_ayarla', 'Ekran parlaklığını ayarlar.',
        {'yuzde': {'type': 'integer', 'minimum': 0, 'maximum': 100}}, ['yuzde'], YAZMA, True, tekrarlanabilir=True)
def parlaklik_ayarla(baglam, yuzde):
    cikti = _sistem().parlaklik_ayarla(yuzde)
    if 'değiştiremiyorum' in cikti:
        return Sonuc(False, cikti, hata_turu='desteklenmiyor')
    try:
        import screen_brightness_control as sbc
        olcum = sbc.get_brightness()
        olcum = olcum[0] if isinstance(olcum, list) else olcum
        return Sonuc(True, cikti, dogrulandi=abs(int(olcum) - int(yuzde)) <= 2)
    except Exception:
        return Sonuc(True, cikti)


@_hizli('ekran_goruntusu_al', 'Ekran görüntüsünü Resimler klasörüne kaydeder.', {}, [], YAZMA, True,
        tekrarlanabilir=True)
def ekran_goruntusu_al(baglam):
    import pyautogui
    klasor = yollar.coz('Resimler')
    klasor.mkdir(parents=True, exist_ok=True)
    yol = klasor / f'JARVIS_{datetime.datetime.now():%Y%m%d_%H%M%S_%f}.png'
    pyautogui.screenshot().save(yol)
    dogru = yol.is_file() and yol.stat().st_size > 0
    return Sonuc(dogru, f'Ekran görüntüsü {yol.name} olarak Resimler klasörüne kaydedildi.' if dogru
                 else 'Ekran görüntüsü kaydedilemedi.', dogrulandi=dogru, veri={'yol': str(yol)})


@_hizli('masaustunu_goster', 'Pencereleri küçültüp masaüstünü gösterir.', {}, [], YAZMA, True, tekrarlanabilir=True)
def masaustunu_goster(baglam):
    _sistem().masaustunu_goster()
    return Sonuc(True, 'Masaüstünü gösterme kısayoluna basıldı.')


@_hizli('tus_bas', 'Klavye kısayolu basar.', {'tuslar': metin('ör. ctrl+c')}, ['tuslar'], YAZMA, True,
        tekrarlanabilir=True)
def tus_bas(baglam, tuslar):
    return Sonuc(True, _sistem().tus_bas(tuslar))


@_hizli('aktif_pencereye_yaz', 'Öndeki pencereye dikte edilen metni yazar. Terminal pencerelerine yazmaz.',
        {'metin': metin('Yazılacak metin')}, ['metin'], YAZMA, True, tekrarlanabilir=True)
def aktif_pencereye_yaz(baglam, metin):
    from ..izinler import TERMINAL
    from .uygulamalar import on_plan_basligi
    baslik = on_plan_basligi()
    if TERMINAL.search(baslik or ''):
        return Sonuc(False, f'Öndeki pencere bir terminal ({baslik}); yazılan metin komut olarak çalışabileceği için '
                            'dikte yazmıyorum.', dogrulandi=False, hata_turu='izin')
    _sistem().metin_yaz(metin)
    return Sonuc(True, f'Yazıldı ({baslik or "öndeki pencere"}).')


# ------------------------------------------------------------------ power (ask unless the user allowed it)

def _guc(ad, aciklama, fonksiyon_adi):
    @_hizli(ad, aciklama, {}, [], SISTEM, True)
    def guc(baglam):
        cikti = getattr(_sistem(), fonksiyon_adi)(onaylandi=True)
        return Sonuc(True, cikti)
    return guc


_guc('bilgisayari_kapat', 'Bilgisayarı kapatır.', 'bilgisayari_kapat')
_guc('yeniden_baslat', 'Bilgisayarı yeniden başlatır.', 'yeniden_baslat')
_guc('uyku_moduna_al', 'Bilgisayarı uyku moduna alır.', 'uyku_moduna_al')


@_hizli('bilgisayari_kilitle', 'Bilgisayarı kilitler.', {}, [], YAZMA, True, tekrarlanabilir=True)
def bilgisayari_kilitle(baglam):
    return Sonuc(True, _sistem().bilgisayari_kilitle())


# ------------------------------------------------------------------ notes / reminders

@_hizli('not_al', 'Not dosyasına bir not ekler.', {'metin': metin('Not')}, ['metin'], YAZMA, True,
        tekrarlanabilir=True)
def not_al(baglam, metin):
    s = _sistem()
    s.not_al(metin)
    try:
        dogru = Path(s.NOT_DOSYASI).read_text(encoding='utf-8').rstrip().endswith(metin.strip())
    except OSError:
        dogru = False
    return Sonuc(dogru, 'Not aldım.' if dogru else 'Notu yazdım ama dosyada göremedim.', dogrulandi=dogru)


@_hizli('notlari_oku', 'Kayıtlı notları okur.', {}, [], OKUMA, False)
def notlari_oku(baglam):
    return Sonuc(True, _sistem().notlari_oku())


@_hizli('notlari_sil', 'Bütün notları siler.', {}, [], SILME, True)
def notlari_sil(baglam):
    s = _sistem()
    cikti = s.notlari_sil(onaylandi=True)
    import os
    return Sonuc(True, cikti, dogrulandi=not os.path.exists(s.NOT_DOSYASI))
