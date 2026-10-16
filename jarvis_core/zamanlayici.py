"""Persistent reminders (replaces the in-memory threading.Timer, finding F14).

- Stored in SQLite as UTC epoch seconds; shown in the user's time zone
  (JARVIS_SAAT_DILIMI, default Europe/Istanbul) with the exact date and time.
- Survive restarts. A reminder whose time passed while JARVIS was closed is
  handled by its missed-run policy: 'tek_sefer' (deliver once, marked late)
  or 'atla' (record as missed).
- Delivery is claimed with one atomic UPDATE, so two running JARVIS
  instances (panel + voice) never announce the same reminder twice.
- Repeats: 'gunluk' / 'haftalik' keep the wall-clock time across DST."""
import datetime as dt
import os
import re
import threading
import time
from zoneinfo import ZoneInfo

TABLO = """CREATE TABLE IF NOT EXISTS hatirlatmalar (
    id INTEGER PRIMARY KEY AUTOINCREMENT, zaman REAL NOT NULL, metin TEXT NOT NULL,
    durum TEXT NOT NULL DEFAULT 'bekliyor', tekrar TEXT NOT NULL DEFAULT 'yok',
    kacirilan TEXT NOT NULL DEFAULT 'tek_sefer', olusturma REAL NOT NULL, teslim REAL, sahip TEXT)"""
GEC_TOLERANS = 120     # seconds: later than this counts as missed (JARVIS was not running)


# Windows has no IANA time zone database; the `tzdata` package provides it. Without it,
# fall back to fixed offsets (Turkey has been UTC+3 all year since 2016).
SABIT = {'Europe/Istanbul': dt.timezone(dt.timedelta(hours=3), 'TRT'), 'UTC': dt.timezone.utc}


def saat_dilimi():
    ad = os.getenv('JARVIS_SAAT_DILIMI', 'Europe/Istanbul')
    try:
        return ZoneInfo(ad)
    except Exception:
        return SABIT.get(ad, dt.timezone.utc)


def yerel_metin(zaman: float) -> str:
    return dt.datetime.fromtimestamp(zaman, saat_dilimi()).strftime('%d.%m.%Y %H:%M')


def zaman_coz(metin: str, simdi: dt.datetime = None):
    """'10 dakika sonra', '2 saat sonra', 'yarın 9', 'yarın saat 09:30', 'saat 15:45', 'bugün 18'
    -> aware datetime in the user's zone, or None."""
    tz = saat_dilimi()
    simdi = simdi or dt.datetime.now(tz)
    k = (metin or '').replace('İ', 'i').lower()
    m = re.search(r'(\d+(?:[.,]\d+)?)\s*(saniye|dakika|saat)\s*sonra', k)
    if m:
        miktar = float(m.group(1).replace(',', '.'))
        return simdi + dt.timedelta(seconds=miktar * {'saniye': 1, 'dakika': 60, 'saat': 3600}[m.group(2)])
    m = re.search(r'\b(yarın|bugün|öbür gün)?\s*(?:saat\s*)?(\d{1,2})(?:[:.](\d{2}))?\s*(?:\'?(?:de|da|te|ta))?\b', k)
    if m and (m.group(1) or 'saat' in k):
        saat, dakika = int(m.group(2)), int(m.group(3) or 0)
        if saat > 23 or dakika > 59:
            return None
        gun = simdi.date() + dt.timedelta(days={'yarın': 1, 'öbür gün': 2}.get(m.group(1), 0))
        hedef = dt.datetime.combine(gun, dt.time(saat, dakika), tz)
        if hedef <= simdi and not m.group(1):
            hedef += dt.timedelta(days=1)          # "saat 9" said at 10:00 means tomorrow
        return hedef
    return None


class Zamanlayici:
    def __init__(self, depo, teslim=None, sahip: str = '') -> None:
        self.depo = depo
        self.teslim = teslim or (lambda kayit: None)
        self.sahip = sahip
        self._dur = threading.Event()
        self._uyandir = threading.Event()
        depo.calistir_ham(TABLO)

    # ------------------------------------------------------------- records
    def ekle(self, zaman: float, metin: str, tekrar: str = 'yok', kacirilan: str = 'tek_sefer') -> dict:
        cur = self.depo.calistir_ham('INSERT INTO hatirlatmalar (zaman, metin, tekrar, kacirilan, olusturma) '
                                     'VALUES (?,?,?,?,?)', (float(zaman), metin, tekrar, kacirilan, time.time()))
        self._uyandir.set()
        kayit = self.kayit(cur.lastrowid)
        tekrar_metni = {'gunluk': ' (her gün)', 'haftalik': ' (her hafta)'}.get(tekrar, '')
        kayit['metin_ozet'] = f'{yerel_metin(zaman)}{tekrar_metni}'
        return kayit

    def kayit(self, kimlik: int):
        r = self.depo.calistir_ham('SELECT * FROM hatirlatmalar WHERE id=?', (kimlik,)).fetchone()
        return dict(r) if r else None

    def bekleyenler(self) -> list:
        return [dict(r) for r in self.depo.calistir_ham(
            "SELECT * FROM hatirlatmalar WHERE durum='bekliyor' ORDER BY zaman")]

    def iptal(self, kimlik: int) -> bool:
        return self.depo.calistir_ham("UPDATE hatirlatmalar SET durum='iptal' WHERE id=? AND durum='bekliyor'",
                                      (kimlik,)).rowcount == 1

    # ------------------------------------------------------------- delivery
    def _sahiplen(self, kayit: dict) -> bool:
        return self.depo.calistir_ham("UPDATE hatirlatmalar SET durum='teslim', teslim=?, sahip=? "
                                      "WHERE id=? AND durum='bekliyor'",
                                      (time.time(), self.sahip, kayit['id'])).rowcount == 1

    def _sonraki(self, kayit: dict) -> None:
        if kayit['tekrar'] not in ('gunluk', 'haftalik'):
            return
        tz = saat_dilimi()
        adim = dt.timedelta(days=1 if kayit['tekrar'] == 'gunluk' else 7)
        yerel = dt.datetime.fromtimestamp(kayit['zaman'], tz)
        simdi = dt.datetime.now(tz)
        sonraki = yerel + adim
        while sonraki <= simdi:                     # several periods missed: next future one only
            sonraki += adim
        # rebuild from the wall-clock time so DST changes do not shift it
        sonraki = dt.datetime.combine(sonraki.date(), yerel.time(), tz)
        self.ekle(sonraki.timestamp(), kayit['metin'], kayit['tekrar'], kayit['kacirilan'])

    def tara(self, simdi: float = None) -> list:
        """Deliver everything due. Returns what this instance delivered."""
        simdi = time.time() if simdi is None else simdi
        teslim_edilen = []
        for kayit in self.depo.calistir_ham("SELECT * FROM hatirlatmalar WHERE durum='bekliyor' AND zaman<=? "
                                            "ORDER BY zaman", (simdi,)).fetchall():
            kayit = dict(kayit)
            gec = simdi - kayit['zaman'] > GEC_TOLERANS
            if gec and kayit['kacirilan'] == 'atla':
                self.depo.calistir_ham("UPDATE hatirlatmalar SET durum='kacirildi' WHERE id=? AND durum='bekliyor'",
                                       (kayit['id'],))
                self._sonraki(kayit)
                continue
            if not self._sahiplen(kayit):
                continue                             # another instance took it
            kayit['gec'] = gec
            kayit['metin_soz'] = (f"Kaçırılan hatırlatma ({yerel_metin(kayit['zaman'])}): {kayit['metin']}" if gec
                                  else f"Hatırlatma: {kayit['metin']}")
            try:
                self.teslim(kayit)
            finally:
                self._sonraki(kayit)
            teslim_edilen.append(kayit)
        return teslim_edilen

    def baslat(self) -> None:
        threading.Thread(target=self._dongu, daemon=True, name='zamanlayici').start()

    def durdur(self) -> None:
        self._dur.set()
        self._uyandir.set()

    def _dongu(self) -> None:
        while not self._dur.is_set():
            try:
                self.tara()
                sonraki = self.depo.calistir_ham("SELECT min(zaman) FROM hatirlatmalar WHERE durum='bekliyor'"
                                                 ).fetchone()[0]
            except Exception:
                sonraki = None
            bekle = 30.0 if sonraki is None else min(30.0, max(0.2, sonraki - time.time()))
            self._uyandir.wait(bekle)
            self._uyandir.clear()
