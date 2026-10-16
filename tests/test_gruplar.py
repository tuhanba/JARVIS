"""Tool routing keeps the prompt small but still offers what a request needs."""
from jarvis_core import gruplar
from jarvis_core.araclar import KAYIT


def test_her_arac_bir_grupta():
    eksik = [ad for ad in KAYIT if gruplar.grup_bul(ad) is None and not ad.startswith('yavas')]
    assert not eksik, f'grupsuz araçlar: {eksik}'


def test_istege_gore_secim():
    assert gruplar.sec('Saat kaç') == {'temel'}
    assert 'belge' in gruplar.sec("Bu klasördeki PDF'leri özetle ve rapor oluştur")
    assert 'indirme' in gruplar.sec('https://ornek.com/a.pdf bağlantısındaki dosyayı indir, tamamlanınca aç')
    assert 'tarayici' in gruplar.sec("Trendyol'da klor tableti ara")
    assert 'dosya' in gruplar.sec('Yanlış klasörü söyledim, diğerine taşı')
    assert 'bilgi' in gruplar.sec('İstanbul hava durumu')


def test_model_araclari_kendisi_acabilir(motor_yap, ev):
    m = motor_yap([[('araclari_ac', {'gruplar': ['tarayici']})], 'Tamam.'])
    m.calistir('Saat kaç')                                   # starts with core tools only
    ilk = {t['function']['name'] for t in m._araclar(gruplar.sec('Saat kaç'))}
    assert 'tarayici_git' not in ilk and 'araclari_ac' in ilk
    sonuc = [x for x in m.llm.gorulen[1] if x['role'] == 'tool'][0]['content']
    assert sonuc.startswith('BAŞARILI') and 'tarayici' in sonuc


def test_baglam_tasmasi_eski_arac_ciktilarini_kisaltir(motor_yap, ev):
    m = motor_yap([], baglam=2048)
    mesajlar = [{'role': 'system', 'content': 's'}, {'role': 'user', 'content': 'u'}] + \
               [{'role': 'tool', 'tool_name': 'x', 'content': 'a' * 3000} for _ in range(6)]
    m._baglami_sigdir(mesajlar)
    assert len(mesajlar[2]['content']) < 500 and len(mesajlar[-1]['content']) == 3000


def test_fare_kullanilirken_bekler_ve_vazgecer():
    import threading
    import time
    from jarvis_core.araclar import Baglam
    from jarvis_core.araclar.arayuz_otomasyonu import fare_bosta_bekle
    b = Baglam(threading.Event())
    sabit = lambda: (100, 100)
    t0 = time.time()
    assert fare_bosta_bekle(b, sakin=0.3, en_fazla=2, konum=sabit)
    assert time.time() - t0 < 0.5
    hareket = iter(range(10_000))
    oynayan = lambda: (next(hareket) * 10, 0)          # user keeps moving the mouse
    assert not fare_bosta_bekle(b, sakin=0.3, en_fazla=0.6, konum=oynayan)


def test_uygulama_icinde_hassas_tiklama_onay_ister(motor_yap, ev):
    from jarvis_core.araclar import KAYIT
    iz = motor_yap([]).izinler
    iz.kural_ekle('*', '', 'izin')
    t = KAYIT['ogeye_tikla']
    assert iz.karar(t, {'pencere': 'Ayarlar', 'oge': 'Bluetooth'})[0] == 'izin'
    assert iz.karar(t, {'pencere': 'Mağaza', 'oge': 'Satın al'})[0] == 'sor'
