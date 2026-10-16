"""Stage B: Ollama intelligence layer (tool selection, model profiles, streaming,
measurements, context budget, follow-up references, fast-path routing)."""
import json
from types import SimpleNamespace

from jarvis_core import arac_secimi
from jarvis_core.araclar import KAYIT


def test_ilgili_araclar_secilir_ve_kesif_araci_eklenir(motor_yap, ev):
    m = motor_yap(['Bitti.'])
    m.calistir("Belgeler'deki pdf dosyalarını bul")
    sunulan = m.llm.gorulen_araclar[0]
    assert 'dosya_ara' in sunulan and 'arac_katalogu' in sunulan
    assert 'program_calistir' not in sunulan and 'ekrani_gor' not in sunulan
    assert len(sunulan) < len([a for a in KAYIT.values() if a.modele_acik])


def test_kesif_sonrasi_tum_katalog_acilir(motor_yap, ev):
    m = motor_yap([[('arac_katalogu', {})], 'Tamam.'])
    m.calistir('hava nasıl')
    once, sonra = m.llm.gorulen_araclar
    assert 'program_calistir' not in once
    assert 'program_calistir' in sonra
    katalog = [x for x in m.llm.gorulen[1] if x['role'] == 'tool'][0]['content']
    assert 'dosya_tasi' in katalog and 'bilgisayari_kapat' not in katalog   # fast-only tools stay hidden


def test_takip_istegi_onceki_gruplari_korur(motor_yap, ev):
    m = motor_yap(['Buldum.', 'Taşıdım.'])
    m.calistir('İndirilenler klasöründeki faturayı bul')
    m.calistir('onu diğerine koy')
    assert 'dosya_tasi' in m.llm.gorulen_araclar[1]


def test_secim_kapatilabilir(motor_yap, ev, monkeypatch):
    monkeypatch.setenv('JARVIS_ARAC_SECIMI', '0')
    m = motor_yap(['Tamam.'])
    m.calistir('merhaba')
    assert len(m.llm.gorulen_araclar[0]) == len([a for a in KAYIT.values() if a.modele_acik])


def test_secici_gruplari():
    assert 'web' in arac_secimi.gruplar('dün Fenerbahçe maçı kaç bitti')
    assert 'program' in arac_secimi.gruplar('git status çalıştır')
    assert arac_secimi.gruplar('Türkiye tarihini anlat') == []
    assert 'bilgi' not in arac_secimi.gruplar('bir program yaz')


def test_kod_profili_cagri_yoluna_bagli(motor_yap, ev):
    m = motor_yap(['def topla(a, b): return a + b'], model_kod='kodcu:7b')
    s = m.calistir('Python ile iki sayıyı toplayan bir fonksiyon yaz')
    assert m.llm.is_turleri == ['kod']
    assert m.depo.gorev(s.gorev_id)['model'] == 'kodcu:7b'
    m.llm.senaryo = ['Merhaba.']
    m.calistir('nasılsın')
    assert m.llm.is_turleri[-1] == 'genel'


def test_metin_akisi_bildirilir(motor_yap, ev):
    parcalar = []
    m = motor_yap(['Bugün hava güneşli efendim.'])
    m.bildir = lambda olay, veri: parcalar.append(veri['metin']) if olay == 'parca' else None
    s = m.calistir('hava nasıl')
    assert ''.join(parcalar).strip() == s.cevap


def test_olcumler_kaydedilir(motor_yap, ev):
    m = motor_yap([])

    def sohbet(mesajlar, araclar, iptal, is_turu='genel', akis=None):
        return {'content': 'Tamam.', 'tool_calls': [], 'olcum': {
            'model': 'qwen', 'toplam_sn': 1.5, 'ilk_parca_sn': 0.4, 'yukleme_sn': 0.01, 'prompt_sn': 0.2,
            'uretim_sn': 1.0, 'prompt_token': 300, 'uretim_token': 40, 'soguk': False}}
    m.llm.sohbet = sohbet
    m.calistir('merhaba')
    ozet = m.depo.olcum_ozeti()
    assert ozet[0]['model'] == 'qwen' and ozet[0]['token_hizi'] == 40 and ozet[0]['soguk'] == 0


def test_ollama_olcum_cikarma():
    from jarvis_core.llm import olcum_cikar
    son = SimpleNamespace(load_duration=3_000_000_000, prompt_eval_duration=500_000_000, eval_duration=2_000_000_000,
                          prompt_eval_count=1000, eval_count=100)
    o = olcum_cikar(son, 'm', 5.6, 3.4)
    assert o['token_hizi'] == 50 and o['prompt_hizi'] == 2000 and o['soguk'] is True and o['ilk_parca_sn'] == 3.4
    bos = olcum_cikar(None, 'm', 1.0, None)
    assert 'token_hizi' not in bos and bos['soguk'] is False and bos['toplam_sn'] == 1.0


def test_baglam_butcesi_eski_ciktilari_kisaltir_kaydi_bozmaz(motor_yap, ev):
    uzun = 'satır\n' * 3000
    (ev / 'Documents' / 'uzun.txt').write_text(uzun, encoding='utf-8')
    senaryo = [[('dosya_oku', {'yol': 'Belgeler/uzun.txt'})]] + \
              [[('klasor_listele', {'klasor': k})] for k in ('Belgeler', 'Masaüstü', 'İndirilenler')] + ['Özetledim.']
    m = motor_yap(senaryo, baglam=4096)
    s = m.calistir('uzun dosyayı oku ve klasörlere bak')
    son_gorulen = m.llm.gorulen[-1]
    arac = [x for x in son_gorulen if x['role'] == 'tool'][0]['content']
    assert 'kısaltıldı' in arac and len(arac) < 1500
    assert any(x['role'] == 'system' and 'adımların durumu' in x['content'] for x in son_gorulen)
    kayit = json.loads(m.depo.gorev(s.gorev_id)['mesajlar'])
    assert len([x for x in kayit if x['role'] == 'tool'][0]['content']) > 8000   # stored history is complete


def test_referanslar_promptta(motor_yap, ev):
    (ev / 'Downloads' / 'fatura.pdf').write_text('x')
    m = motor_yap([[('dosya_tasi', {'kaynak': 'İndirilenler/fatura.pdf', 'hedef': 'Belgeler'})], 'Taşıdım.',
                   'Hangi klasöre?'])
    m.calistir('faturayı Belgeler’e taşı')
    m.calistir('onu diğer klasöre taşı')
    sistem = m.llm.gorulen[-1][0]['content']
    assert 'Son bahsedilenler' in sistem and 'fatura.pdf' in sistem


def test_cok_amacli_cumle_modele_gider():
    import komutlar

    class AI:
        aktif = True
    ham = "Chrome'u aç ve YouTube'da Tarkan çal"
    assert komutlar._yerel_komut(komutlar.kucuk(ham), ham, AI()) is None
    tek = 'YouTube\'da Tarkan çal'
    assert komutlar._yerel_komut(komutlar.kucuk(tek), tek, AI()).arac == 'youtube_cal'


# ----------------------------------------------------------------- found by the live test (qwen3:1.7b)

def test_arac_cagirmadan_yaptim_demek_basari_sayilmaz(motor_yap, ev):
    m = motor_yap(['Tamamdır efendim.', 'Tamamdır efendim.'])
    s = m.calistir('Belgeler klasörüne alisveris.txt adında bir dosya oluştur, içine süt yaz.')
    assert s.durum == 'dogrulanamadi'
    assert 'hiçbir işlem yapılmadı' in s.cevap
    assert 'Hiçbir araç çağırmadın' in m.llm.gorulen[1][-1]['content']   # one correction turn was given


def test_duzeltme_sonrasi_arac_cagrilirsa_tamamlanir(motor_yap, ev):
    m = motor_yap(['Tamamdır efendim.', [('dosya_yaz', {'yol': 'Belgeler/alisveris.txt', 'icerik': 'süt'})],
                   'Oluşturdum.'])
    s = m.calistir('Belgeler klasörüne alisveris.txt adında bir dosya oluştur, içine süt yaz.')
    assert s.durum == 'tamamlandi' and (ev / 'Documents' / 'alisveris.txt').exists()


def test_sohbet_yazma_istegi_eylem_sayilmaz(motor_yap, ev):
    from jarvis_core.yurutucu import eylem_istegi
    assert not eylem_istegi('Bana kısa bir şiir yaz')
    assert not eylem_istegi('Türkiye tarihini anlat')
    assert eylem_istegi("Chrome'u aç") and eylem_istegi('raporu Masaüstüne taşı')
    m = motor_yap(['Gül dalında bülbül...'])
    assert m.calistir('Bana kısa bir şiir yaz').durum == 'tamamlandi'


def test_degerlendirme_bagimsiz_kontrol_ve_izolasyon(ev):
    """The benchmark judges the end state, not the model's words, and never touches the real home."""
    from pathlib import Path
    from conftest import SahteLLM
    from jarvis_core import degerlendirme
    gorevler = {g['ad']: g for g in degerlendirme.GOREVLER}
    gercek_ev = Path.home()
    yalanci = degerlendirme.gorevi_calistir(gorevler['tasi'], 'sahte', llm=SahteLLM(['Taşıdım.', 'Taşıdım.']))
    assert not yalanci['gecti'] and not yalanci['sahte_basari']        # engine did not claim success
    durust = degerlendirme.gorevi_calistir(gorevler['tasi'], 'sahte', llm=SahteLLM([
        [('dosya_tasi', {'kaynak': 'İndirilenler/fatura.pdf', 'hedef': 'Belgeler'})], 'Taşıdım.']))
    assert durust['gecti'] and durust['durumlar'] == ['tamamlandi']
    assert Path.home() == gercek_ev and not (gercek_ev / 'Documents' / 'fatura.pdf').exists()
    ozet = degerlendirme.ozetle([yalanci, durust])
    assert ozet[0]['gecen'] == 1 and ozet[0]['sahte_basari'] == 0


# ----------------------------------------------------------------- found by the live test (qwen3:4b)

def test_dusunce_etiketleri_akista_gizlenir():
    from jarvis_core.llm import _DusunceAyiklayici, dusunceyi_ayikla
    a = _DusunceAyiklayici()
    parcalar = ['Mer', '<thi', 'nk>gizli plan', ' devam</th', 'ink>haba', ' efendim <', 'b>']
    cikti = ''.join(a.besle(p) for p in parcalar) + a.bitir()
    assert cikti == 'Merhaba efendim <b>'
    assert dusunceyi_ayikla('<think>x</think>Ankara') == 'Ankara'
    assert dusunceyi_ayikla('Ankara<think>yarım kaldı') == 'Ankara'


def test_think_false_dinlemeyen_model_ayri_alanda_dusunur(monkeypatch):
    """qwen3:4b (thinking-only build) wrote its reasoning into the answer with think=False."""
    from types import SimpleNamespace
    from jarvis_core.ayarlar import Ayarlar
    from jarvis_core.llm import OllamaIstemci
    a = Ayarlar()
    a.dusunme = False
    ist = OllamaIstemci(a)
    OllamaIstemci._dusunme_karari.clear()
    monkeypatch.setattr(ist, 'yetenekler', lambda m: ['completion', 'tools', 'thinking'])
    cevaplar = {'inatci': 'Okay, so the user wants me to write tamam. Let me think...', 'uysal': 'tamam'}
    monkeypatch.setattr(ist.istemci, 'chat', lambda model, **k: SimpleNamespace(
        message=SimpleNamespace(content=cevaplar[model])))
    assert ist.dusunme_ayari('inatci') is None          # let it think in the hidden field
    assert ist.dusunme_ayari('uysal') is False           # honours think=False: fast path
    monkeypatch.setattr(ist, 'yetenekler', lambda m: ['completion', 'tools'])
    assert ist.dusunme_ayari('dusunmeyen') is False


def test_tek_model_kurali_surec_genelinde(monkeypatch):
    from jarvis_core.ayarlar import Ayarlar
    from jarvis_core.llm import OllamaIstemci
    a = Ayarlar()
    a.tek_model = True
    bosaltilan = []
    OllamaIstemci._yuklu_model = None
    i1, i2 = OllamaIstemci(a), OllamaIstemci(a)
    for i in (i1, i2):
        monkeypatch.setattr(i.istemci, 'generate', lambda model, **k: bosaltilan.append(model))
    i1._bosalt('kucuk')
    i2._bosalt('buyuk')                                  # another instance: still unloads 'kucuk'
    assert bosaltilan == ['kucuk']
