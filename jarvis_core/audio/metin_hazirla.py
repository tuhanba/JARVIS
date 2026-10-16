"""Turn a written answer into something a Turkish voice reads naturally.

The panel shows the original text; TTS gets this version: numbers, times,
percentages, units, file names, URLs and common abbreviations spelled out,
markdown and emoji removed."""
import re

BIRLER = ['', 'bir', 'iki', 'üç', 'dört', 'beş', 'altı', 'yedi', 'sekiz', 'dokuz']
ONLAR = ['', 'on', 'yirmi', 'otuz', 'kırk', 'elli', 'altmış', 'yetmiş', 'seksen', 'doksan']
BUYUK = [(10 ** 12, 'trilyon'), (10 ** 9, 'milyar'), (10 ** 6, 'milyon'), (1000, 'bin')]


def sayi_oku(n: int) -> str:
    """Integer to Turkish words: 1984 -> 'bin dokuz yüz seksen dört'."""
    if n == 0:
        return 'sıfır'
    if n < 0:
        return 'eksi ' + sayi_oku(-n)
    parcalar = []
    for deger, ad in BUYUK:
        if n >= deger:
            bolum, n = divmod(n, deger)
            # Turkish says "bin", not "bir bin" (but "bir milyon").
            parcalar.append(ad if (deger == 1000 and bolum == 1) else f'{sayi_oku(bolum)} {ad}')
    if n >= 100:
        yuz, n = divmod(n, 100)
        parcalar.append('yüz' if yuz == 1 else f'{BIRLER[yuz]} yüz')
    if n >= 10:
        parcalar.append(ONLAR[n // 10])
        n %= 10
    if n:
        parcalar.append(BIRLER[n])
    return ' '.join(parcalar)


KISALTMALAR = {
    r'\bvb\.': 've benzeri', r'\bvs\.': 'vesaire', r'\bör\.': 'örneğin', r'\bDr\.': 'doktor',
    r'\bProf\.': 'profesör', r'\bsn\b': 'saniye', r'\bdk\b': 'dakika', r'\bkm\b': 'kilometre',
    r'\bkg\b': 'kilogram', r'\bGB\b': 'gigabayt', r'\bMB\b': 'megabayt', r'\bKB\b': 'kilobayt', r'\bTB\b': 'terabayt',
    r'\bTL\b': 'lira', r'₺': ' lira', r'\$': ' dolar', r'€': ' avro', r'°C': ' derece', r'°': ' derece',
    r'\bCPU\b': 'işlemci', r'\bRAM\b': 'ram', r'\bJARVIS\b': 'Jarvis',
}
_EMOJI = re.compile(r'[\U0001F000-\U0001FAFF☀-➿️‍]')


def _yol_oku(m: re.Match) -> str:
    """'C:\\Users\\x\\Belgeler\\rapor_2026.pdf' -> 'rapor 2026 pdf dosyası'."""
    ad = re.split(r'[\\/]', m.group(0).rstrip('\\/'))[-1]
    kok, _, uzanti = ad.rpartition('.')
    if not kok:
        return ad.replace('_', ' ')
    return f"{kok.replace('_', ' ').replace('-', ' ')} {uzanti.lower()} dosyası"


def _adres_oku(m: re.Match) -> str:
    alan = re.sub(r'^(https?://)?(www\.)?', '', m.group(0)).split('/')[0]
    return alan.replace('.', ' nokta ') + ' sitesi'


def _ondalik(m: re.Match) -> str:
    tam, kesir = m.group(1), m.group(2)
    return f'{sayi_oku(int(tam))} virgül {" ".join(sayi_oku(int(c)) for c in kesir) if kesir.startswith("0") else sayi_oku(int(kesir))}'


def seslendirme_metni(metin: str) -> str:
    m = _EMOJI.sub('', metin or '')
    m = re.sub(r'```.*?```', ' ', m, flags=re.S)
    m = re.sub(r'\*\*|__|`|^#+\s*|^\s*[-*•]\s+', '', m, flags=re.M)
    m = re.sub(r'https?://\S+|www\.\S+', _adres_oku, m)
    m = re.sub(r'(?:[A-Za-z]:\\|/)?(?:[\w .-]+[\\/])+[\w .-]+\.\w{1,5}\b', _yol_oku, m)     # paths
    m = re.sub(r'\b([\w-]+)\.(pdf|docx?|xlsx?|pptx?|txt|csv|md|png|jpe?g|mp3|mp4|zip|exe|py|html?)\b',
               lambda x: f'{x.group(1).replace("_", " ")} {x.group(2).lower()}', m, flags=re.I)
    for desen, yerine in KISALTMALAR.items():
        m = re.sub(desen, yerine, m)
    # times 14:05 -> "on dört sıfır beş", 09:30 -> "dokuz otuz", 14:00 -> "on dört"
    m = re.sub(r'\b([01]?\d|2[0-3])[:.]([0-5]\d)\b(?![.,]\d)', lambda x: sayi_oku(int(x.group(1))) + (
        '' if x.group(2) == '00' else ' ' + ('sıfır ' + sayi_oku(int(x.group(2))) if x.group(2)[0] == '0'
                                               else sayi_oku(int(x.group(2))))), m)
    m = re.sub(r'%\s?(\d+(?:,\d+)?)|(\d+(?:,\d+)?)\s?%', lambda x: 'yüzde ' + (x.group(1) or x.group(2)), m)
    m = re.sub(r'\b(\d{1,3}(?:\.\d{3})+)\b', lambda x: x.group(1).replace('.', ''), m)        # 1.250.000
    m = re.sub(r'\b(\d+),(\d+)\b', _ondalik, m)
    m = re.sub(r'\b(\d+)\.(\d+)\b', lambda x: f'{sayi_oku(int(x.group(1)))} nokta {sayi_oku(int(x.group(2)))}', m)
    m = re.sub(r'\b\d{1,15}\b', lambda x: sayi_oku(int(x.group(0))), m)
    m = re.sub(r'[*#_|<>]+', ' ', m)
    return re.sub(r'\s{2,}', ' ', m).strip()
