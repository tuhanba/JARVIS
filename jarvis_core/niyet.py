"""Turkish text helpers shared by every input path (panel, voice, CLI).

- cevap_coz: yes / no / unclear for an approval answer. Negation and doubt
  win over any positive word, so "yapma", "olur mu bilmiyorum" or
  "evet değil" are never taken as a yes.
- durdurma_mi: is this utterance a stop command? Whole words only, so
  "durum ne" does not cancel a task.
- Niyet: what a fast (model-free) command wants done; it is executed by
  the same executor, policy and audit log as the model's tool calls."""
import re
import unicodedata
from dataclasses import dataclass, field


def kucuk(metin: str) -> str:
    """Turkish-aware lowercase ('İ' -> 'i', 'I' -> 'ı'), NFC-normalised."""
    metin = unicodedata.normalize('NFC', metin or '')
    return metin.replace('İ', 'i').replace('I', 'ı').lower().strip()


def kelimeler(metin: str) -> list:
    return re.findall(r"[0-9a-zçğıöşüâîû]+", kucuk(metin))


OLUMLU = {'evet', 'tamam', 'tamamdır', 'olur', 'onay', 'onaylıyorum', 'onayla', 'onaylarım', 'yap', 'yapabilirsin',
          'peki', 'kabul', 'tabii', 'tabi', 'elbette', 'aynen', 'ok', 'okey', 'e', 'evt', 'sil', 'gönder', 'kapat',
          'devam', 'yes', 'y', 'hıhı', 'olsun', 'lütfen', 'hemen', 'bunu', 'şunu', 'et', 'jarvis', 'efendim'}
# Words that carry a positive decision on their own (the rest above only fill out a yes).
KARAR = {'evet', 'tamam', 'tamamdır', 'olur', 'onay', 'onaylıyorum', 'onayla', 'onaylarım', 'yap', 'yapabilirsin',
         'peki', 'kabul', 'tabii', 'tabi', 'elbette', 'aynen', 'ok', 'okey', 'e', 'evt', 'yes', 'y', 'hıhı', 'olsun'}
OLUMSUZ = {'hayır', 'hayir', 'yok', 'iptal', 'vazgeç', 'vazgec', 'dur', 'durdur', 'olmaz', 'değil', 'degil', 'no',
           'sakın', 'sakin', 'reddet', 'reddediyorum', 'istemem', 'istemiyorum', 'yapma', 'etme', 'asla', 'kesinlikle'}
SUPHE = {'belki', 'bilmiyorum', 'bilmem', 'emin', 'sanırım', 'galiba', 'herhalde', 'acaba', 'mı', 'mi', 'mu', 'mü',
         'neden', 'niye', 'ne', 'nasıl', 'hangi', 'kim', 'düşüneyim', 'bekle', 'sonra'}
# Negative verb suffixes: yap-ma, yap-mayın, onayla-mıyorum, ol-maz, yap-madım...
_OLUMSUZ_EK = re.compile(r'^\w{2,}(m[ae]|m[ae]y[ıi]n(ız)?|m[ae]s[ıi]n|m[ıiuü]yor\w*|m[ae]z\w*|m[ae]d[ıiuü]\w*|m[ae]yalım)$')


def cevap_coz(metin: str) -> str:
    """'evet' | 'hayir' | 'belirsiz'. Anything not clearly yes is not a yes."""
    sozcukler = kelimeler(metin)
    if not sozcukler:
        return 'belirsiz'
    if any(s in SUPHE for s in sozcukler) or '?' in (metin or ''):
        return 'belirsiz'
    if any(s in OLUMSUZ or (s not in OLUMLU and _OLUMSUZ_EK.match(s)) for s in sozcukler):
        return 'hayir'
    if any(s in KARAR for s in sozcukler) and all(s in OLUMLU for s in sozcukler):
        return 'evet'
    return 'belirsiz'


DURDURMA = {'dur', 'durdur', 'iptal', 'vazgeç', 'vazgec', 'stop', 'cancel', 'kes', 'sus', 'yeter'}
_DOLGU = {'jarvis', 'hey', 'et', 'lütfen', 'hemen', 'artık', 'tamam', 'görevi', 'işlemi', 'her', 'şeyi', 'bunu', 'şunu'}


def durdurma_mi(metin: str) -> bool:
    """A short utterance whose only real word is a stop word."""
    sozcukler = kelimeler(metin)
    gercek = [s for s in sozcukler if s not in _DOLGU]
    return bool(gercek) and len(gercek) <= 2 and gercek[0] in DURDURMA and all(
        s in DURDURMA for s in gercek)


@dataclass
class Niyet:
    """A fast command resolved without the model: run tool `arac` with `argumanlar`."""
    arac: str
    argumanlar: dict = field(default_factory=dict)
    # Spoken when the tool succeeds; the tool's own output is used if empty.
    basari_metni: str = ''
