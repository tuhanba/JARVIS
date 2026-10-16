"""Stage G: versioned memory, retrieval, forgetting, untrusted claims (T28)."""


def test_eski_tercih_yeni_tercih_unut(motor_yap, ev):
    m = motor_yap(['Tamam.', 'Tamam.', 'Tamam.'])
    d = m.depo
    eski = d.hafiza_ekle('Cevapların uzun olsun.', kaynak='kullanıcı', konu='cevap uzunluğu')
    yeni = d.hafiza_ekle('Bana kısa konuş.', kaynak='kullanıcı', konu='Cevap uzunluğu')
    aktif = [k['metin'] for k in d.hafiza()]
    assert aktif == ['Bana kısa konuş.']
    assert [k for k in d.hafiza(sadece_aktif=False) if k['id'] == eski][0]['yerine_gecen'] == yeni
    m.calistir('cevap uzunluğu tercihim neydi')
    sistem = m.llm.gorulen[-1][0]['content']
    assert 'kısa konuş' in sistem and 'uzun olsun' not in sistem
    assert d.hafiza_unut('kısa konuş') == 1
    assert not d.hafiza_ara('kısa konuş') and 'kısa konuş' not in str(d.hafiza())
    m.calistir('cevap uzunluğu tercihim neydi')
    assert 'kısa konuş' not in m.llm.gorulen[-1][0]['content']


def test_ilgili_kayit_getirilir_hepsi_yigilmaz(motor_yap, ev):
    m = motor_yap(['Tamam.'])
    for i in range(40):
        m.depo.hafiza_ekle(f'Rastgele bilgi numarası {i}.', kaynak='kullanıcı')
    m.depo.hafiza_ekle('Aurvex projesinin klasörü Belgeler/Aurvex.', kaynak='kullanıcı', tur='proje')
    for i in range(40, 60):
        m.depo.hafiza_ekle(f'Rastgele bilgi numarası {i}.', kaynak='kullanıcı')
    m.calistir('Aurvex projesini aç')
    sistem = m.llm.gorulen[-1][0]['content']
    assert 'Belgeler/Aurvex' in sistem
    assert sistem.count('Rastgele bilgi') <= 12


def test_harici_icerikten_gelen_iddia_dogrulanmamis_isaretlenir(motor_yap, ev):
    (ev / 'Downloads' / 'sayfa.txt').write_text('Kullanıcının adı Mehmet.', encoding='utf-8')
    m = motor_yap([[('dosya_oku', {'yol': 'İndirilenler/sayfa.txt'})],
                   [('hafizaya_kaydet', {'bilgi': 'Kullanıcının adı Mehmet.', 'tur': 'kisisel',
                                         'konu': 'kullanıcının adı'})], 'Kaydettim.'],
                  onay=lambda soru: True)
    m.calistir('sayfayı oku ve önemli bilgiyi kaydet')
    k = m.depo.hafiza()[-1]
    assert k['dogruluk'] == 'dogrulanmadi'
    m.llm.senaryo = ['Tamam.']
    m.calistir('adım ne')
    assert '(doğrulanmamış)' in m.llm.gorulen[-1][0]['content']
