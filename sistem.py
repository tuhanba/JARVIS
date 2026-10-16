"""Everything JARVIS can do on the computer.

Each public function returns a short Turkish sentence. They are used both
by the fixed voice commands (komutlar.py) and as AI tools (beyin.py),
so the docstrings are written for the model.
"""
import datetime
import difflib
import glob
import json
import os
import re
import subprocess
import sys
import threading
import urllib.parse
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

import ses

WIN = sys.platform == 'win32'
MAC = sys.platform == 'darwin'
PROJE = os.path.dirname(os.path.abspath(__file__))
NOT_DOSYASI = os.path.join(PROJE, 'notlar.txt')
HAFIZA_DOSYASI = os.path.join(PROJE, 'hafiza.json')

# Spoken name stem -> what `start` launches on Windows.
UYGULAMALAR = {
    'not defter': 'notepad', 'notepad': 'notepad',
    'hesap makine': 'calc',
    'paint': 'mspaint',
    'komut istem': 'cmd', 'cmd': 'cmd',
    'powershell': 'powershell', 'terminal': 'wt',
    'dosya gezgin': 'explorer', 'gezgin': 'explorer', 'bilgisayarım': 'explorer',
    'görev yönetici': 'taskmgr',
    'ayarlar': 'ms-settings:',
    'denetim masa': 'control',
    'chrome': 'chrome', 'krom': 'chrome',
    'edge': 'msedge',
    'firefox': 'firefox',
    'word': 'winword',
    'excel': 'excel',
    'powerpoint': 'powerpnt',
    'spotify': 'spotify:',
    'vs code': 'code', 'visual studio code': 'code', 'vscode': 'code',
    'discord': 'discord:',
    'steam': 'steam:',
    'whatsapp': 'whatsapp:',
    'telegram': 'tg:',
    'mağaza': 'ms-windows-store:',
    'saat uygulama': 'ms-clock:',
    'takvim': 'outlookcal:',
    'posta': 'outlookmail:',
}

# Launch target -> process name for taskkill.
SURECLER = {
    'notepad': 'notepad.exe', 'calc': 'CalculatorApp.exe', 'mspaint': 'mspaint.exe',
    'cmd': 'cmd.exe', 'powershell': 'powershell.exe', 'wt': 'WindowsTerminal.exe',
    'taskmgr': 'Taskmgr.exe', 'chrome': 'chrome.exe', 'msedge': 'msedge.exe',
    'firefox': 'firefox.exe', 'winword': 'WINWORD.EXE', 'excel': 'EXCEL.EXE',
    'powerpnt': 'POWERPNT.EXE', 'spotify:': 'Spotify.exe', 'code': 'Code.exe',
    'discord:': 'Discord.exe', 'steam:': 'steam.exe', 'whatsapp:': 'WhatsApp.exe',
    'tg:': 'Telegram.exe', 'ms-settings:': 'SystemSettings.exe',
}

SITELER = {
    'youtube': 'https://www.youtube.com', 'google': 'https://www.google.com',
    'gmail': 'https://mail.google.com', 'instagram': 'https://www.instagram.com',
    'twitter': 'https://x.com', 'facebook': 'https://www.facebook.com',
    'github': 'https://github.com', 'netflix': 'https://www.netflix.com',
    'haritalar': 'https://maps.google.com', 'harita': 'https://maps.google.com',
    'çeviri': 'https://translate.google.com', 'linkedin': 'https://www.linkedin.com',
    'trendyol': 'https://www.trendyol.com', 'hepsiburada': 'https://www.hepsiburada.com',
    'sahibinden': 'https://www.sahibinden.com', 'twitch': 'https://www.twitch.tv',
    'reddit': 'https://www.reddit.com', 'chatgpt': 'https://chatgpt.com',
    'gemini': 'https://gemini.google.com', 'claude': 'https://claude.ai',
}

KLASORLER = {
    'masaüstü': 'Desktop', 'indirilenler': 'Downloads', 'belgeler': 'Documents',
    'resimler': 'Pictures', 'müzik': 'Music', 'videolar': 'Videos', 'ev': '',
}

HAVA_KODLARI = {
    0: 'açık', 1: 'az bulutlu', 2: 'parçalı bulutlu', 3: 'kapalı', 45: 'sisli', 48: 'kırağılı sis',
    51: 'hafif çisenti', 53: 'çisenti', 55: 'yoğun çisenti', 61: 'hafif yağmurlu', 63: 'yağmurlu',
    65: 'şiddetli yağmurlu', 66: 'dondurucu yağmur', 67: 'dondurucu yağmur', 71: 'hafif karlı',
    73: 'karlı', 75: 'yoğun karlı', 77: 'kar taneli', 80: 'sağanak', 81: 'sağanak', 82: 'şiddetli sağanak',
    85: 'kar sağanağı', 86: 'yoğun kar sağanağı', 95: 'gök gürültülü fırtına',
    96: 'dolu ile fırtına', 99: 'dolu ile şiddetli fırtına',
}

# Shell commands that change or destroy things need a spoken "evet" first,
# because a misheard sentence must never wipe files.
_TEHLIKELI = re.compile(
    r'\b(rm|del|erase|rd|rmdir|remove-item|ri|format|format-volume|diskpart|clear-disk|'
    r'shutdown|restart-computer|stop-computer|reg|remove-itemproperty|set-itemproperty|'
    r'cipher|bcdedit|takeown|icacls|mkfs|dd|kill|taskkill|stop-process|set-executionpolicy|'
    r'move|move-item|mv|ren|rename-item|uninstall|winget|choco|net|sc|schtasks|'
    r'new-service|set-service|disable|enable)\b',
    re.IGNORECASE,
)


def _onay(soru: str) -> bool:
    if os.getenv('JARVIS_TAM_YETKI') == '1':
        return True
    return ses.onayla(soru)


def _baslat(hedef: str) -> None:
    if WIN:
        subprocess.Popen(['cmd', '/c', 'start', '', hedef], creationflags=0x08000000)
    elif MAC:
        subprocess.Popen(['open', '-a', hedef] if '/' not in hedef and ':' not in hedef else ['open', hedef])
    else:
        try:
            subprocess.Popen([hedef])
        except FileNotFoundError:
            subprocess.Popen(['xdg-open', hedef])


def _klasor(ad: str) -> Path:
    """Map 'masaüstü' style names (or a real path) to a folder."""
    ad = ad.strip().strip('"\'')
    parcalar = re.split(r'[\\/]', ad, maxsplit=1)
    ilk, kalan = parcalar[0].lower(), (parcalar[1] if len(parcalar) > 1 else '')
    for anahtar, alt in KLASORLER.items():
        if ilk == anahtar or (len(anahtar) > 2 and ilk.split(' ')[0].startswith(anahtar[:5])):
            ev = Path.home()
            kok = ev / alt
            if alt and not kok.exists() and (ev / 'OneDrive' / alt).exists():
                kok = ev / 'OneDrive' / alt
            return kok / kalan if kalan else kok
    return Path(os.path.expandvars(os.path.expanduser(ad)))


def _baslat_menusu_ara(ad: str):
    """Find an installed program's Start Menu shortcut by fuzzy name."""
    if not WIN:
        return None
    kokler = [os.path.join(os.environ.get('ProgramData', r'C:\ProgramData'), r'Microsoft\Windows\Start Menu\Programs'),
              os.path.join(os.environ.get('APPDATA', ''), r'Microsoft\Windows\Start Menu\Programs')]
    kisayollar = {}
    for kok in kokler:
        for yol in glob.glob(os.path.join(kok, '**', '*.lnk'), recursive=True):
            kisayollar[Path(yol).stem.lower()] = yol
    for isim, yol in kisayollar.items():
        if ad in isim:
            return yol
    yakin = difflib.get_close_matches(ad, kisayollar.keys(), n=1, cutoff=0.6)
    return kisayollar[yakin[0]] if yakin else None


# ---------------------------------------------------------------- programs

def uygulama_bul(ad: str) -> bool:
    """True if `ad` is a known app or an installed Start Menu program."""
    ad = ad.lower().strip()
    return any(kok in ad for kok in UYGULAMALAR) or bool(_baslat_menusu_ara(ad))


def uygulama_ac(ad: str) -> str:
    """Bilgisayarda bir uygulamayı açar (ör. 'not defteri', 'chrome', 'spotify', 'excel' ya da kurulu herhangi bir program adı).

    Args:
        ad: Uygulamanın adı.
    """
    ad = ad.lower().strip()
    for kok, hedef in UYGULAMALAR.items():
        if kok in ad:
            _baslat(hedef)
            return f'{ad} açılıyor.'
    kisayol = _baslat_menusu_ara(ad)
    if kisayol:
        os.startfile(kisayol)
        return f'{Path(kisayol).stem} açılıyor.'
    try:
        _baslat(ad)
        return f'{ad} açılmaya çalışılıyor.'
    except Exception:
        return f'{ad} adında bir uygulama bulamadım.'


def uygulama_kapat(ad: str) -> str:
    """Açık bir uygulamayı kapatır.

    Args:
        ad: Uygulamanın adı (ör. 'chrome', 'not defteri') veya süreç adı ('chrome.exe').
    """
    ad = ad.lower().strip()
    surec = None
    for kok, hedef in UYGULAMALAR.items():
        if kok in ad:
            surec = SURECLER.get(hedef)
            break
    surec = surec or (ad if ad.endswith('.exe') else ad.replace(' ', '') + '.exe')
    if WIN:
        p = subprocess.run(['taskkill', '/im', surec, '/f'], capture_output=True, text=True, errors='replace')
    else:
        p = subprocess.run(['pkill', '-f', surec.removesuffix('.exe')], capture_output=True, text=True)
    return f'{ad} kapatıldı.' if p.returncode == 0 else f'{ad} açık görünmüyor.'


def calisan_uygulamalar() -> str:
    """En çok bellek kullanan açık uygulamaları listeler."""
    import psutil
    surecler = []
    for p in psutil.process_iter(['name', 'memory_info']):
        try:
            surecler.append((p.info['memory_info'].rss, p.info['name']))
        except Exception:
            pass
    surecler.sort(reverse=True)
    goruldu, satirlar = set(), []
    for rss, isim in surecler:
        if isim and isim not in goruldu:
            goruldu.add(isim)
            satirlar.append(f'{isim} ({rss // 2**20} MB)')
        if len(satirlar) == 10:
            break
    return 'En çok bellek kullananlar: ' + ', '.join(satirlar)


def youtube_indirici_ac() -> str:
    """YouTube video indirme penceresini açar."""
    subprocess.Popen([sys.executable, os.path.join(PROJE, 'youtube_downloader.py')], cwd=PROJE)
    return 'YouTube indirici açılıyor.'


# ---------------------------------------------------------------- web

def web_sitesi_ac(adres: str) -> str:
    """Tarayıcıda bir web sitesi açar.

    Args:
        adres: Site adı ('youtube', 'instagram') veya adresi ('ornek.com').
    """
    adres = adres.strip().lower()
    url = SITELER.get(adres) or (adres if adres.startswith('http') else 'https://' + adres.replace(' ', ''))
    webbrowser.open(url)
    return f'{adres} açılıyor.'


def google_ara(sorgu: str) -> str:
    """Google'da arama yapar ve sonuçları tarayıcıda açar.

    Args:
        sorgu: Aranacak metin.
    """
    webbrowser.open('https://www.google.com/search?q=' + urllib.parse.quote(sorgu))
    return f'Google\'da {sorgu} aranıyor.'


def youtube_ara(sorgu: str) -> str:
    """YouTube'da arama yapar.

    Args:
        sorgu: Aranacak metin.
    """
    webbrowser.open('https://www.youtube.com/results?search_query=' + urllib.parse.quote(sorgu))
    return f'YouTube\'da {sorgu} aranıyor.'


def youtube_cal(sorgu: str) -> str:
    """YouTube'da aranan şarkıyı/videoyu bulup ilk sonucu oynatır.

    Args:
        sorgu: Şarkı veya video adı.
    """
    try:
        sayfa = requests.get('https://www.youtube.com/results', params={'search_query': sorgu},
                             headers={'Accept-Language': 'tr'}, timeout=10).text
        kimlik = re.search(r'"videoId":"([\w-]{11})"', sayfa)
    except requests.RequestException:
        kimlik = None
    if not kimlik:
        return youtube_ara(sorgu)
    webbrowser.open(f'https://www.youtube.com/watch?v={kimlik.group(1)}')
    return f'{sorgu} çalınıyor.'


def vikipedi(konu: str) -> str:
    """Türkçe Vikipedi'den bir konunun kısa özetini getirir.

    Args:
        konu: Aranacak konu.
    """
    # Wikimedia rejects requests without a descriptive User-Agent.
    basliklar = {'User-Agent': 'JARVIS-sesli-asistan/1.0 (https://github.com/tuhanba/JARVIS)'}
    kok = 'https://tr.wikipedia.org'

    def ozet(baslik):
        r = requests.get(f"{kok}/api/rest_v1/page/summary/{urllib.parse.quote(baslik.replace(' ', '_'))}",
                         headers=basliklar, timeout=8)
        veri = r.json() if r.ok else {}
        if veri.get('type') == 'standard' and veri.get('extract'):
            return ' '.join(re.split(r'(?<=[.!?])\s+', veri['extract'])[:2])
        return None

    try:
        sonuc = ozet(konu.strip().title())
        if not sonuc:
            ara = requests.get(f'{kok}/w/rest.php/v1/search/title', params={'q': konu, 'limit': 1},
                               headers=basliklar, timeout=8).json()
            if ara.get('pages'):
                sonuc = ozet(ara['pages'][0]['title'])
    except (requests.RequestException, ValueError):
        sonuc = None
    return sonuc or f'Vikipedi\'de {konu} hakkında bir şey bulamadım.'


def hava_durumu(sehir: str) -> str:
    """Bir şehrin şu anki hava durumunu söyler.

    Args:
        sehir: Şehir adı. Boş bırakılırsa ayarlardaki şehir (SEHIR) kullanılır.
    """
    sehir = sehir.strip() or os.getenv('SEHIR', 'İstanbul')
    try:
        yer = requests.get('https://geocoding-api.open-meteo.com/v1/search',
                           params={'name': sehir, 'count': 1, 'language': 'tr'}, timeout=8).json()
        yer = yer['results'][0]
        hava = requests.get('https://api.open-meteo.com/v1/forecast', timeout=8, params={
            'latitude': yer['latitude'], 'longitude': yer['longitude'],
            'current': 'temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code',
            'daily': 'temperature_2m_max,temperature_2m_min', 'forecast_days': 1, 'timezone': 'auto',
        }).json()
        c, g = hava['current'], hava['daily']
    except Exception:
        return f'{sehir} için hava durumunu alamadım.'
    durum = HAVA_KODLARI.get(c['weather_code'], 'değişken')
    return (f"{yer['name']}'da hava {durum}, {round(c['temperature_2m'])} derece, "
            f"hissedilen {round(c['apparent_temperature'])}. Bugün en yüksek {round(g['temperature_2m_max'][0])}, "
            f"en düşük {round(g['temperature_2m_min'][0])} derece. Nem yüzde {c['relative_humidity_2m']}, "
            f"rüzgar saatte {round(c['wind_speed_10m'])} kilometre.")


def haberler(adet: int) -> str:
    """Türkiye'den güncel haber başlıklarını okur.

    Args:
        adet: Kaç başlık okunacağı (ör. 5).
    """
    try:
        rss = requests.get('https://news.google.com/rss?hl=tr&gl=TR&ceid=TR:tr', timeout=10).content
        basliklar = [i.findtext('title') for i in ET.fromstring(rss).iter('item')][:max(1, int(adet))]
    except Exception:
        return 'Haberlere şu an ulaşamıyorum.'
    return 'Güncel başlıklar: ' + '. '.join(b.rsplit(' - ', 1)[0] for b in basliklar) + '.'


def doviz_kuru() -> str:
    """Güncel dolar ve euro kurunu (Türk lirası karşılığı) söyler."""
    try:
        kur = requests.get('https://open.er-api.com/v6/latest/TRY', timeout=8).json()['rates']
        return f"1 dolar {1 / kur['USD']:.2f} lira, 1 euro {1 / kur['EUR']:.2f} lira."
    except Exception:
        return 'Döviz kurlarına ulaşamadım.'


def ip_adresi() -> str:
    """Bilgisayarın internet (dış) IP adresini söyler."""
    try:
        return 'IP adresiniz ' + requests.get('https://api.ipify.org', timeout=8).text
    except requests.RequestException:
        return 'IP adresini öğrenemedim.'


# ---------------------------------------------------------------- files

def klasor_ac(klasor: str) -> str:
    """Dosya gezgininde bir klasörü açar.

    Args:
        klasor: 'masaüstü', 'indirilenler', 'belgeler', 'resimler', 'müzik', 'videolar' veya tam yol.
    """
    yol = _klasor(klasor)
    if not yol.exists():
        return f'{klasor} klasörünü bulamadım.'
    _baslat(str(yol))
    return f'{yol.name or yol} açılıyor.'


def dosyalari_listele(klasor: str) -> str:
    """Bir klasördeki dosya ve klasörleri listeler.

    Args:
        klasor: 'masaüstü', 'indirilenler', 'belgeler' gibi bir ad veya tam yol.
    """
    yol = _klasor(klasor)
    if not yol.is_dir():
        return f'{klasor} klasörünü bulamadım.'
    ogeler = sorted(yol.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    adlar = [p.name + ('/' if p.is_dir() else '') for p in ogeler[:100]]
    ek = f' (ve {len(ogeler) - 100} öğe daha)' if len(ogeler) > 100 else ''
    return f'{yol} içinde {len(ogeler)} öğe: ' + ', '.join(adlar) + ek


def dosya_ac(yol: str) -> str:
    """Bir dosyayı varsayılan programıyla açar.

    Args:
        yol: Dosyanın tam yolu.
    """
    p = _klasor(yol)
    if not p.exists():
        return f'{yol} bulunamadı.'
    _baslat(str(p))
    return f'{p.name} açılıyor.'


def dosya_ara(ad: str, klasor: str) -> str:
    """Bir klasörün içinde (alt klasörler dahil) adı eşleşen dosyaları arar.

    Args:
        ad: Dosya adının bir parçası.
        klasor: Aramanın başlayacağı klasör ('masaüstü', 'belgeler', 'ev' ya da tam yol).
    """
    kok = _klasor(klasor or 'ev')
    bulunan = []
    for dizin, _, dosyalar in os.walk(kok):
        bulunan += [os.path.join(dizin, d) for d in dosyalar if ad.lower() in d.lower()]
        if len(bulunan) >= 20:
            break
    return '\n'.join(bulunan[:20]) if bulunan else f'{kok} içinde {ad} bulunamadı.'


def dosya_oku(yol: str) -> str:
    """Bir metin dosyasının içeriğini okur (ilk 4000 karakter).

    Args:
        yol: Dosyanın tam yolu.
    """
    try:
        return _klasor(yol).read_text(encoding='utf-8', errors='replace')[:4000]
    except OSError as e:
        return f'Dosya okunamadı: {e}'


def dosya_yaz(yol: str, icerik: str) -> str:
    """Bir metin dosyası oluşturur veya üzerine yazar.

    Args:
        yol: Dosyanın tam yolu.
        icerik: Dosyaya yazılacak metin.
    """
    p = _klasor(yol)
    if p.exists() and not _onay(f'{p.name} zaten var, üzerine yazayım mı?'):
        return 'Dosyaya yazılmadı.'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(icerik, encoding='utf-8')
    return f'{p} kaydedildi.'


# ---------------------------------------------------------------- shell

def komut_calistir(komut: str) -> str:
    """Bilgisayarda bir kabuk komutu çalıştırır (Windows'ta PowerShell) ve çıktısını döndürür.
    Başka bir araç işi yapamıyorsa bunu kullan. Silme/taşıma/kapatma gibi komutlar için kullanıcıdan onay istenir.

    Args:
        komut: Çalıştırılacak komut, ör. 'Get-ChildItem $HOME\\Desktop'.
    """
    if _TEHLIKELI.search(komut) and not _onay(f'Şu komutu çalıştırayım mı: {komut}'):
        return 'Kullanıcı onay vermedi, komut çalıştırılmadı.'
    if WIN:
        args = ['powershell', '-NoProfile', '-Command',
                '[Console]::OutputEncoding=[Text.Encoding]::UTF8; ' + komut]
    else:
        args = ['bash', '-lc', komut]
    try:
        p = subprocess.run(args, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=120)
    except subprocess.TimeoutExpired:
        return 'Komut 120 saniyede bitmedi.'
    cikti = (p.stdout + p.stderr).strip() or f'(çıktı yok, çıkış kodu {p.returncode})'
    return cikti[:4000]


# ---------------------------------------------------------------- system

def saat_tarih() -> str:
    """Şu anki saati, tarihi ve günü söyler."""
    simdi = datetime.datetime.now()
    gunler = ['Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi', 'Pazar']
    aylar = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran', 'Temmuz', 'Ağustos',
             'Eylül', 'Ekim', 'Kasım', 'Aralık']
    return f'Saat {simdi:%H:%M}. Bugün {simdi.day} {aylar[simdi.month - 1]} {simdi.year}, {gunler[simdi.weekday()]}.'


def sistem_durumu() -> str:
    """İşlemci, bellek, disk ve pil durumunu söyler."""
    import psutil
    disk = psutil.disk_usage(os.path.abspath(os.sep))
    metin = (f'İşlemci yüzde {psutil.cpu_percent(interval=0.5):.0f}, bellek yüzde {psutil.virtual_memory().percent:.0f}, '
             f'disk yüzde {disk.percent:.0f} dolu, {disk.free // 2**30} gigabayt boş.')
    pil = psutil.sensors_battery()
    if pil:
        metin += f' Pil yüzde {pil.percent:.0f}' + (', şarj oluyor.' if pil.power_plugged else '.')
    return metin


def ses_ayarla(islem: str, adim: int) -> str:
    """Bilgisayarın ses seviyesini değiştirir.

    Args:
        islem: 'artır', 'azalt' veya 'sessiz' (sessiz aç/kapat).
        adim: Kaç adım değişeceği (her adım yaklaşık yüzde 2), ör. 5.
    """
    import pyautogui
    if 'sessiz' in islem or 'kapat' in islem:
        pyautogui.press('volumemute')
        return 'Ses kapatıldı / açıldı.'
    tus = 'volumeup' if any(k in islem for k in ('art', 'aç', 'yüksel')) else 'volumedown'
    pyautogui.press(tus, presses=max(1, int(adim)))
    return 'Ses artırıldı.' if tus == 'volumeup' else 'Ses azaltıldı.'


def parlaklik_ayarla(yuzde: int) -> str:
    """Ekran parlaklığını ayarlar.

    Args:
        yuzde: 0 ile 100 arası parlaklık.
    """
    try:
        import screen_brightness_control as sbc
        sbc.set_brightness(max(0, min(100, int(yuzde))))
        return f'Parlaklık yüzde {yuzde}.'
    except Exception:
        return 'Bu ekranın parlaklığını değiştiremiyorum.'


def ekran_goruntusu_al() -> str:
    """Ekran görüntüsü alıp Resimler klasörüne kaydeder."""
    import pyautogui
    klasor = _klasor('resimler')
    klasor.mkdir(parents=True, exist_ok=True)
    yol = klasor / f'JARVIS_{datetime.datetime.now():%Y%m%d_%H%M%S}.png'
    pyautogui.screenshot().save(yol)
    return f'Ekran görüntüsü {yol.name} olarak Resimler klasörüne kaydedildi.'


def masaustunu_goster() -> str:
    """Tüm pencereleri küçültüp masaüstünü gösterir."""
    import pyautogui
    pyautogui.hotkey('win', 'd')
    return 'Masaüstü gösteriliyor.'


def metin_yaz(metin: str) -> str:
    """Aktif penceredeki imlecin olduğu yere metin yazar (Türkçe karakterler dahil).

    Args:
        metin: Yazılacak metin.
    """
    import pyautogui
    import pyperclip
    pyperclip.copy(metin)
    pyautogui.hotkey('ctrl', 'v')
    return 'Yazıldı.'


def tus_bas(tuslar: str) -> str:
    """Klavye kısayolu veya tuş basar, ör. 'ctrl+c', 'alt+tab', 'enter', 'win+e'.

    Args:
        tuslar: Artı ile ayrılmış tuşlar.
    """
    import pyautogui
    pyautogui.hotkey(*[t.strip().lower() for t in tuslar.split('+')])
    return f'{tuslar} basıldı.'


def panoyu_oku() -> str:
    """Panoya kopyalanmış metni okur."""
    import pyperclip
    metin = pyperclip.paste()
    return metin[:2000] if metin else 'Pano boş.'


def bilgisayari_kilitle() -> str:
    """Bilgisayarı kilitler (oturum açık kalır)."""
    if WIN:
        subprocess.run(['rundll32.exe', 'user32.dll,LockWorkStation'])
    else:
        subprocess.run(['loginctl', 'lock-session'])
    return 'Bilgisayar kilitlendi.'


def bilgisayari_kapat() -> str:
    """Bilgisayarı kapatır (onay ister)."""
    if not _onay('Bilgisayarı kapatayım mı?'):
        return 'Kapatma iptal edildi.'
    subprocess.run(['shutdown', '/s', '/t', '5'] if WIN else ['shutdown', '-h', '+0'])
    return 'Bilgisayar 5 saniye içinde kapanıyor.'


def yeniden_baslat() -> str:
    """Bilgisayarı yeniden başlatır (onay ister)."""
    if not _onay('Bilgisayarı yeniden başlatayım mı?'):
        return 'Yeniden başlatma iptal edildi.'
    subprocess.run(['shutdown', '/r', '/t', '5'] if WIN else ['shutdown', '-r', '+0'])
    return 'Bilgisayar 5 saniye içinde yeniden başlıyor.'


def uyku_moduna_al() -> str:
    """Bilgisayarı uyku moduna alır (onay ister)."""
    if not _onay('Bilgisayarı uyku moduna alayım mı?'):
        return 'İptal edildi.'
    if WIN:
        subprocess.run(['rundll32.exe', 'powrprof.dll,SetSuspendState', '0,1,0'])
    else:
        subprocess.run(['systemctl', 'suspend'])
    return 'Uyku moduna geçiliyor.'


# ---------------------------------------------------------------- memory

def not_al(metin: str) -> str:
    """Kullanıcının söylediği bir notu kaydeder.

    Args:
        metin: Kaydedilecek not.
    """
    with open(NOT_DOSYASI, 'a', encoding='utf-8') as f:
        f.write(f'{datetime.datetime.now():%d.%m.%Y %H:%M} - {metin}\n')
    return 'Not aldım.'


def notlari_oku() -> str:
    """Kaydedilmiş notları okur."""
    if not os.path.exists(NOT_DOSYASI):
        return 'Hiç notunuz yok.'
    with open(NOT_DOSYASI, encoding='utf-8') as f:
        satirlar = f.read().strip().splitlines()
    return 'Notlarınız: ' + '. '.join(satirlar[-10:]) if satirlar else 'Hiç notunuz yok.'


def notlari_sil() -> str:
    """Tüm notları siler (onay ister)."""
    if not os.path.exists(NOT_DOSYASI) or not _onay('Tüm notları sileyim mi?'):
        return 'Notlar silinmedi.'
    os.remove(NOT_DOSYASI)
    return 'Notlar silindi.'


def hatirlatici_kur(dakika: float, mesaj: str) -> str:
    """Belirtilen dakika sonra sesli hatırlatma yapar (zamanlayıcı/alarm olarak da kullanılır).

    Args:
        dakika: Kaç dakika sonra (ör. 0.5 = 30 saniye).
        mesaj: Hatırlatılacak şey.
    """
    t = threading.Timer(float(dakika) * 60, ses.konus, args=[f'Hatırlatma: {mesaj or "süre doldu"}'])
    t.daemon = True
    t.start()
    zaman = f'{int(dakika * 60)} saniye' if dakika < 1 else f'{dakika:g} dakika'
    return f'Tamam, {zaman} sonra hatırlatacağım.'


# ---------------------------------------------------------------- internet

def internette_ara(sorgu: str) -> str:
    """İnternette arama yapar ve ilk sonuçların başlık, özet ve adreslerini döndürür.
    Güncel bilgi (haber, maç sonucu, fiyat, kişi, olay) gerektiren her soruda önce bunu kullan.

    Args:
        sorgu: Arama metni.
    """
    try:
        from ddgs import DDGS
        sonuclar = DDGS().text(sorgu, region='tr-tr', max_results=6)
    except Exception as e:
        return f'Arama yapılamadı: {e}'
    if not sonuclar:
        return 'Sonuç bulunamadı.'
    return '\n'.join(f"- {r['title']}: {r['body']} ({r['href']})" for r in sonuclar)


def web_sayfasi_oku(adres: str) -> str:
    """Bir web sayfasını indirip düz metnini döndürür (ilk 5000 karakter).

    Args:
        adres: Sayfanın tam adresi (https://...).
    """
    from bs4 import BeautifulSoup
    try:
        r = requests.get(adres, timeout=12, headers={'User-Agent': 'Mozilla/5.0 JARVIS'})
    except requests.RequestException as e:
        return f'Sayfa açılamadı: {e}'
    sayfa = BeautifulSoup(r.text, 'html.parser')
    for etiket in sayfa(['script', 'style', 'nav', 'footer', 'header', 'noscript']):
        etiket.decompose()
    return re.sub(r'\n\s*\n+', '\n', sayfa.get_text('\n')).strip()[:5000]


# ---------------------------------------------------------------- more files

def dosya_sil(yol: str) -> str:
    """Bir dosyayı veya klasörü Geri Dönüşüm Kutusu'na gönderir (onay ister, geri alınabilir).

    Args:
        yol: Silinecek dosya/klasörün tam yolu.
    """
    p = _klasor(yol)
    if not p.exists():
        return f'{yol} bulunamadı.'
    if not _onay(f'{p.name} geri dönüşüm kutusuna gönderilsin mi?'):
        return 'Silinmedi.'
    from send2trash import send2trash
    send2trash(str(p))
    return f'{p.name} geri dönüşüm kutusuna gönderildi.'


def dosya_tasi(kaynak: str, hedef: str) -> str:
    """Bir dosyayı/klasörü başka yere taşır veya yeniden adlandırır.

    Args:
        kaynak: Taşınacak dosyanın tam yolu.
        hedef: Yeni yol (klasör ya da yeni dosya adı).
    """
    import shutil
    k, h = _klasor(kaynak), _klasor(hedef)
    if not k.exists():
        return f'{kaynak} bulunamadı.'
    son = h / k.name if h.is_dir() else h
    if son.exists() and not _onay(f'{son.name} zaten var, üzerine yazılsın mı?'):
        return 'Taşınmadı.'
    shutil.move(str(k), str(son))
    return f'{k.name} taşındı: {son}'


def dosya_kopyala(kaynak: str, hedef: str) -> str:
    """Bir dosyayı/klasörü kopyalar.

    Args:
        kaynak: Kopyalanacak dosyanın tam yolu.
        hedef: Hedef klasör veya dosya yolu.
    """
    import shutil
    k, h = _klasor(kaynak), _klasor(hedef)
    if not k.exists():
        return f'{kaynak} bulunamadı.'
    son = h / k.name if h.is_dir() else h
    if k.is_dir():
        shutil.copytree(k, son, dirs_exist_ok=True)
    else:
        shutil.copy2(k, son)
    return f'{k.name} kopyalandı: {son}'


def klasor_olustur(yol: str) -> str:
    """Yeni bir klasör oluşturur.

    Args:
        yol: Klasörün tam yolu veya 'masaüstü/Yeni Klasör' gibi bir yol.
    """
    p = _klasor(yol)
    p.mkdir(parents=True, exist_ok=True)
    return f'{p} oluşturuldu.'


# ---------------------------------------------------------------- code

_TEHLIKELI_PY = re.compile(
    r'\b(remove|unlink|rmtree|rmdir|system|popen|subprocess|move|rename|replace|'
    r'send2trash|truncate|kill|shutdown|winreg)\b|open\([^)]*[\'"][wa]',
)


def python_calistir(kod: str) -> str:
    """Python kodu çalıştırır ve çıktısını (print) döndürür. Hesaplama, veri işleme,
    dosya dönüştürme, toplu işlem gibi işler için kullan. Dosya değiştiren kodlar için onay istenir.

    Args:
        kod: Çalıştırılacak tam Python kodu. Sonuçları print ile yazdır.
    """
    if _TEHLIKELI_PY.search(kod) and not _onay('Bu Python kodu bilgisayarda değişiklik yapacak. Çalıştırayım mı?'):
        return 'Kullanıcı onay vermedi, kod çalıştırılmadı.'
    try:
        p = subprocess.run([sys.executable, '-c', kod], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=120, cwd=str(Path.home()),
                           env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
    except subprocess.TimeoutExpired:
        return 'Kod 120 saniyede bitmedi.'
    return ((p.stdout + p.stderr).strip() or '(çıktı yok)')[:4000]


# ---------------------------------------------------------------- windows

def pencereye_gec(baslik: str) -> str:
    """Başlığında verilen metin geçen açık pencereyi öne getirir.

    Args:
        baslik: Pencere başlığının bir parçası (ör. 'Chrome', 'Word').
    """
    try:
        import pygetwindow
        pencereler = [w for w in pygetwindow.getWindowsWithTitle(baslik) if w.title]
    except Exception:
        return 'Pencere yönetimi bu sistemde desteklenmiyor.'
    if not pencereler:
        return f'{baslik} adlı bir pencere bulamadım.'
    w = pencereler[0]
    if w.isMinimized:
        w.restore()
    w.activate()
    return f'{w.title} öne getirildi.'


def acik_pencereler() -> str:
    """Açık pencerelerin başlıklarını listeler."""
    try:
        import pygetwindow
        basliklar = [t for t in pygetwindow.getAllTitles() if t.strip()]
    except Exception:
        return 'Pencere listesi bu sistemde alınamıyor.'
    return 'Açık pencereler: ' + ', '.join(basliklar[:30])


def panoya_kopyala(metin: str) -> str:
    """Bir metni panoya kopyalar.

    Args:
        metin: Kopyalanacak metin.
    """
    import pyperclip
    pyperclip.copy(metin)
    return 'Panoya kopyalandı.'


# ---------------------------------------------------------------- long-term memory

def hafizayi_yukle() -> list:
    try:
        with open(HAFIZA_DOSYASI, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def hafizaya_kaydet(bilgi: str) -> str:
    """Kullanıcı hakkında kalıcı olarak hatırlanacak bir bilgiyi kaydeder (adı, tercihleri,
    önemli tarihler, sık kullandığı klasörler...). Kullanıcı 'unutma', 'hatırla' dediğinde
    veya kendisi hakkında önemli bir şey söylediğinde kullan.

    Args:
        bilgi: Kısa ve net bir cümle, ör. 'Kullanıcının adı Batuhan.'
    """
    hafiza = hafizayi_yukle()
    if bilgi not in hafiza:
        hafiza.append(bilgi)
        with open(HAFIZA_DOSYASI, 'w', encoding='utf-8') as f:
            json.dump(hafiza, f, ensure_ascii=False, indent=1)
    return 'Aklımda tutacağım.'


def hafizadan_sil(bilgi: str) -> str:
    """Kalıcı hafızadan, verilen metni içeren bilgileri siler.

    Args:
        bilgi: Silinecek bilginin bir parçası.
    """
    hafiza = hafizayi_yukle()
    kalan = [h for h in hafiza if bilgi.lower() not in h.lower()]
    with open(HAFIZA_DOSYASI, 'w', encoding='utf-8') as f:
        json.dump(kalan, f, ensure_ascii=False, indent=1)
    return f'{len(hafiza) - len(kalan)} bilgi unutuldu.'


# Functions the AI may call on its own (beyin.py adds ekrani_gor).
ARACLAR = [
    uygulama_ac, uygulama_kapat, calisan_uygulamalar, youtube_indirici_ac,
    web_sitesi_ac, google_ara, youtube_ara, youtube_cal, vikipedi, hava_durumu, haberler,
    doviz_kuru, ip_adresi,
    klasor_ac, dosyalari_listele, dosya_ac, dosya_ara, dosya_oku, dosya_yaz,
    komut_calistir,
    saat_tarih, sistem_durumu, ses_ayarla, parlaklik_ayarla, ekran_goruntusu_al,
    masaustunu_goster, metin_yaz, tus_bas, panoyu_oku,
    bilgisayari_kilitle, bilgisayari_kapat, yeniden_baslat, uyku_moduna_al,
    not_al, notlari_oku, notlari_sil, hatirlatici_kur,
    internette_ara, web_sayfasi_oku,
    dosya_sil, dosya_tasi, dosya_kopyala, klasor_olustur,
    python_calistir, pencereye_gec, acik_pencereler, panoya_kopyala,
    hafizaya_kaydet, hafizadan_sil,
]
