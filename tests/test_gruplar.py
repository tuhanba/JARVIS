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
