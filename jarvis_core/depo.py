"""SQLite store for tasks, steps (tool calls) and long-term memory.

Every tool call is written *before* it runs (durum='basladi') and updated
after, so a crash leaves enough information to decide on restart whether a
side effect already happened."""
import hashlib
import json
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

SEMA = """
CREATE TABLE IF NOT EXISTS gorevler (
    id TEXT PRIMARY KEY, istek TEXT NOT NULL, durum TEXT NOT NULL,
    olusturma REAL NOT NULL, guncelleme REAL NOT NULL,
    sonuc TEXT, hata TEXT, model TEXT, mesajlar TEXT DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS adimlar (
    id INTEGER PRIMARY KEY AUTOINCREMENT, gorev_id TEXT NOT NULL, sira INTEGER NOT NULL,
    arac TEXT NOT NULL, argumanlar TEXT NOT NULL, anahtar TEXT NOT NULL, durum TEXT NOT NULL,
    cikti TEXT, dogrulandi INTEGER, geri_al TEXT, baslangic REAL, bitis REAL,
    FOREIGN KEY (gorev_id) REFERENCES gorevler(id)
);
CREATE INDEX IF NOT EXISTS adim_anahtar ON adimlar(gorev_id, anahtar);
CREATE TABLE IF NOT EXISTS hafiza (
    id INTEGER PRIMARY KEY AUTOINCREMENT, metin TEXT NOT NULL, tur TEXT NOT NULL DEFAULT 'tercih',
    kaynak TEXT NOT NULL, tarih REAL NOT NULL, aktif INTEGER NOT NULL DEFAULT 1, yerine_gecen INTEGER
);
"""

# Never persist secrets: mask things that look like passwords, tokens and keys.
_GIZLI = [
    (re.compile(r'(?i)(parola|şifre|sifre|password|passwd|pwd|token|api[_-]?key|secret|anahtar)(\s*[:=]\s*|\s+)(\S+)'),
     r'\1\2****'),
    (re.compile(r'\b(sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AIza[0-9A-Za-z_-]{20,}|xox[abp]-[A-Za-z0-9-]{10,})'),
     '****'),
]


def maskele(metin):
    if not isinstance(metin, str):
        return metin
    for desen, yerine in _GIZLI:
        metin = desen.sub(yerine, metin)
    return metin


def anahtar_uret(arac: str, argumanlar: dict) -> str:
    return hashlib.sha256((arac + json.dumps(argumanlar, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:24]


class Depo:
    def __init__(self, yol: Path) -> None:
        self._kilit = threading.Lock()
        self._db = sqlite3.connect(str(yol), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute('PRAGMA journal_mode=WAL')
        self._db.executescript(SEMA)

    def _calistir(self, sql: str, params=()):
        with self._kilit:
            return self._db.execute(sql, params)

    # ------------------------------------------------------------- tasks
    def gorev_olustur(self, istek: str, model: str) -> str:
        gid = uuid.uuid4().hex[:8]
        simdi = time.time()
        self._calistir('INSERT INTO gorevler (id, istek, durum, olusturma, guncelleme, model) VALUES (?,?,?,?,?,?)',
                       (gid, maskele(istek), 'calisiyor', simdi, simdi, model))
        return gid

    def gorev_guncelle(self, gid: str, **alanlar) -> None:
        alanlar['guncelleme'] = time.time()
        if 'mesajlar' in alanlar:
            alanlar['mesajlar'] = maskele(json.dumps(alanlar['mesajlar'], ensure_ascii=False))
        for k in ('sonuc', 'hata'):
            if k in alanlar:
                alanlar[k] = maskele(alanlar[k])
        sutunlar = ', '.join(f'{k}=?' for k in alanlar)
        self._calistir(f'UPDATE gorevler SET {sutunlar} WHERE id=?', (*alanlar.values(), gid))

    def gorev(self, gid: str):
        satir = self._calistir('SELECT * FROM gorevler WHERE id=?', (gid,)).fetchone()
        return dict(satir) if satir else None

    def gorevler(self, sinir: int = 20) -> list:
        return [dict(r) for r in self._calistir(
            'SELECT id, istek, durum, olusturma, sonuc FROM gorevler ORDER BY olusturma DESC LIMIT ?', (sinir,))]

    def yarim_kalanlari_isaretle(self) -> list:
        """On startup: tasks still 'calisiyor' were cut off by a crash or restart."""
        ids = [r['id'] for r in self._calistir("SELECT id FROM gorevler WHERE durum='calisiyor'")]
        for gid in ids:
            self.gorev_guncelle(gid, durum='yarida_kaldi')
        return ids

    # ------------------------------------------------------------- steps
    def adim_baslat(self, gid: str, sira: int, arac: str, argumanlar: dict) -> int:
        cur = self._calistir(
            'INSERT INTO adimlar (gorev_id, sira, arac, argumanlar, anahtar, durum, baslangic) VALUES (?,?,?,?,?,?,?)',
            (gid, sira, arac, maskele(json.dumps(argumanlar, ensure_ascii=False)),
             anahtar_uret(arac, argumanlar), 'basladi', time.time()))
        return cur.lastrowid

    def adim_bitir(self, adim_id: int, durum: str, cikti: str, dogrulandi=None, geri_al=None) -> None:
        self._calistir('UPDATE adimlar SET durum=?, cikti=?, dogrulandi=?, geri_al=?, bitis=? WHERE id=?',
                       (durum, maskele(cikti), None if dogrulandi is None else int(dogrulandi),
                        json.dumps(geri_al, ensure_ascii=False) if geri_al else None, time.time(), adim_id))

    def onceki_adim(self, gid: str, arac: str, argumanlar: dict):
        """Most recent identical call in this task (for idempotency)."""
        satir = self._calistir(
            'SELECT * FROM adimlar WHERE gorev_id=? AND anahtar=? ORDER BY id DESC LIMIT 1',
            (gid, anahtar_uret(arac, argumanlar))).fetchone()
        return dict(satir) if satir else None

    def adimlar(self, gid: str) -> list:
        return [dict(r) for r in self._calistir('SELECT * FROM adimlar WHERE gorev_id=? ORDER BY id', (gid,))]

    def son_geri_alinabilir(self):
        satir = self._calistir(
            "SELECT * FROM adimlar WHERE geri_al IS NOT NULL AND durum='tamam' ORDER BY id DESC LIMIT 1").fetchone()
        return dict(satir) if satir else None

    def geri_alindi_isaretle(self, adim_id: int) -> None:
        self._calistir("UPDATE adimlar SET durum='geri_alindi' WHERE id=?", (adim_id,))

    def son_islemler(self, sinir: int = 8) -> list:
        return [dict(r) for r in self._calistir(
            "SELECT arac, argumanlar, cikti, dogrulandi FROM adimlar WHERE durum='tamam' "
            "ORDER BY id DESC LIMIT ?", (sinir,))][::-1]

    # ------------------------------------------------------------- memory
    def hafiza_ekle(self, metin: str, kaynak: str, tur: str = 'tercih') -> int:
        return self._calistir('INSERT INTO hafiza (metin, tur, kaynak, tarih) VALUES (?,?,?,?)',
                              (maskele(metin), tur, kaynak, time.time())).lastrowid

    def hafiza(self, sadece_aktif: bool = True) -> list:
        sql = 'SELECT * FROM hafiza' + (' WHERE aktif=1' if sadece_aktif else '') + ' ORDER BY tarih'
        return [dict(r) for r in self._calistir(sql)]

    def hafiza_unut(self, parca: str) -> int:
        return self._calistir('UPDATE hafiza SET aktif=0 WHERE aktif=1 AND lower(metin) LIKE ?',
                              (f'%{parca.lower()}%',)).rowcount
