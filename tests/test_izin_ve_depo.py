from jarvis_core.araclar import KAYIT
from jarvis_core.depo import maskele


def test_program_izinleri(motor_yap, ev):
    iz = motor_yap([]).izinler
    p = KAYIT['program_calistir']
    assert iz.karar(p, {'program': 'git', 'argumanlar': ['status']})[0] == 'izin'
    assert iz.karar(p, {'program': 'git', 'argumanlar': ['push']})[0] == 'sor'
    assert iz.karar(p, {'program': 'python', 'argumanlar': ['-c', 'print(1)']})[0] == 'sor'
    assert iz.karar(p, {'program': 'powershell', 'argumanlar': ['Remove-Item', 'x']})[0] == 'sor'


def test_kullanici_kurali_ve_yasak(motor_yap, ev, tmp_path):
    iz = motor_yap([]).izinler
    sil = KAYIT['cop_kutusuna_gonder']
    assert iz.karar(sil, {'yol': 'İndirilenler/a.zip'})[0] == 'sor'
    iz.kural_ekle('cop_kutusuna_gonder', 'İndirilenler', 'izin')
    assert iz.karar(sil, {'yol': 'İndirilenler/a.zip'})[0] == 'izin'
    assert iz.karar(sil, {'yol': 'Belgeler/a.zip'})[0] == 'sor'
    iz.kural_ekle('*', 'Belgeler', 'red')
    assert iz.karar(KAYIT['dosya_yaz'], {'yol': 'Belgeler/x.txt', 'icerik': ''})[0] == 'red'
    assert iz.karar(KAYIT['dosya_yaz'], {'yol': 'Masaüstü/x.txt', 'icerik': ''})[0] == 'izin'


def test_gizli_bilgiler_maskelenir(motor_yap, ev):
    assert maskele('şifre: Gizli123 ve token=abc') == 'şifre: **** ve token=****'
    assert 'ghp_' not in maskele('anahtar ghp_aaaaaaaaaaaaaaaaaaaaaaaa')
    m = motor_yap([[('dosya_yaz', {'yol': 'Belgeler/a.txt', 'icerik': 'parola: 1234'})], 'Tamam.'])
    m.calistir("wifi parola: 1234 olarak not et")
    import sqlite3
    db = sqlite3.connect(m.a.veritabani)
    dokum = '\n'.join(str(r) for t in ('gorevler', 'adimlar') for r in db.execute(f'select * from {t}'))
    assert '1234' not in dokum


def test_hafiza_kaynak_tarih_unutma(motor_yap, ev):
    d = motor_yap([]).depo
    d.hafiza_ekle('Adım Batuhan.', kaynak='kullanıcı')
    d.hafiza_ekle('Ofis klasörüm Belgeler/Is.', kaynak='kullanıcı', tur='proje')
    kayitlar = d.hafiza()
    assert all(k['kaynak'] and k['tarih'] for k in kayitlar)
    assert d.hafiza_unut('batuhan') == 1
    assert [k['metin'] for k in d.hafiza()] == ['Ofis klasörüm Belgeler/Is.']


def test_turkce_klasor_adlari(ev):
    from jarvis_core import yollar
    assert yollar.coz('Belgeler/a.txt') == ev / 'Documents' / 'a.txt'
    assert yollar.coz("Masaüstü'ne") == ev / 'Desktop'
    assert yollar.coz('İndirilenler') == ev / 'Downloads'
    assert yollar.coz('documents/x') == ev / 'Documents' / 'x'


def test_git_parametre_enjeksiyonu_ve_gizli_push(motor_yap, ev):
    iz = motor_yap([]).izinler
    p = KAYIT['program_calistir']
    assert iz.karar(p, {'program': 'git', 'argumanlar': ['-c', 'core.sshCommand=calc', 'fetch']})[0] == 'sor'
    assert iz.karar(p, {'program': 'git', 'argumanlar': ['-C', 'proje', 'push']})[0] == 'sor'
    assert iz.karar(p, {'program': 'git', 'argumanlar': ['-C', 'proje', 'log', '--oneline']})[0] == 'izin'


def test_terminale_yazma_onay_ister(motor_yap, ev):
    iz = motor_yap([]).izinler
    m = KAYIT['metin_yaz']
    assert iz.karar(m, {'metin': 'x', 'pencere': 'Windows PowerShell'})[0] == 'sor'
    assert iz.karar(m, {'metin': 'x', 'pencere': 'Not Defteri'})[0] == 'izin'


def test_gecersiz_cagri_sonsuz_tur_atamaz(motor_yap, ev):
    senaryo = [[('dosya_yaz', {'yol': f'Belgeler/{i}.txt'})] for i in range(100)]   # always missing 'icerik'
    m = motor_yap(senaryo, max_adim=5)
    assert m.calistir('yaz').durum == 'butce_asildi'
    assert len(m.llm.gorulen) <= 11
