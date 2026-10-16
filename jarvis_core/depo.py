"""SQLite store for tasks, steps (tool calls) and long-term memory.

Every tool call is written *before* it runs (durum='basladi') and updated
after, so a crash leaves enough information to decide on restart whether a
side effect already happened.

Schema versions (PRAGMA user_version):
  1  original tables
  2  task checkpoint / input source / owner, step action ids and goal keys,
     quarantine for records that can no longer be parsed.
  3  per-turn model measurements (olcumler).
  4  memory: topic key (konu) for versioning, truth state (dogruluk), FTS index.
The file is copied to jarvis.db.v<N>.yedek before a migration runs.

Connection ownership: one connection per Depo, shared across threads behind
a lock; every statement is its own short transaction (autocommit)."""
import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from .gizlilik import maskele, maskele_nesne  # noqa: F401  (maskele re-exported for old imports)

SURUM = 4

SEMA_V1 = """
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

GOREV_V2 = [('kontrol_noktasi', "TEXT DEFAULT '{}'"), ('kaynak', "TEXT DEFAULT 'model'"), ('sahip', 'TEXT')]
HAFIZA_V4 = [('konu', 'TEXT'), ('dogruluk', "TEXT DEFAULT 'kullanici'")]
ADIM_V2 = [('eylem_id', 'TEXT'), ('amac', 'TEXT'), ('deneme', 'INTEGER DEFAULT 1'), ('hata_turu', 'TEXT'),
           ('veri', 'TEXT'), ('sonuc_durumu', 'TEXT')]
OLCUMLER = """CREATE TABLE IF NOT EXISTS olcumler (
    id INTEGER PRIMARY KEY AUTOINCREMENT, gorev_id TEXT, tur INTEGER, model TEXT, is_turu TEXT, arac_sayisi INTEGER,
    toplam_sn REAL, ilk_parca_sn REAL, yukleme_sn REAL, prompt_sn REAL, uretim_sn REAL, prompt_token INTEGER,
    uretim_token INTEGER, soguk INTEGER, tarih REAL NOT NULL)"""
KARANTINA = """CREATE TABLE IF NOT EXISTS karantina (
    id INTEGER PRIMARY KEY AUTOINCREMENT, tablo TEXT NOT NULL, kayit_id TEXT NOT NULL, alan TEXT NOT NULL,
    veri TEXT, sebep TEXT NOT NULL, tarih REAL NOT NULL)"""

# Task states that are final: they are never reopened by "devam".
BITMIS = {'tamamlandi', 'dogrulanamadi', 'iptal', 'butce_asildi', 'dongu', 'hata', 'bozuk_kayit', 'reddedildi'}


def anahtar_uret(arac: str, argumanlar: dict) -> str:
    return hashlib.sha256((arac + json.dumps(argumanlar, sort_keys=True, ensure_ascii=False)).encode()).hexdigest()[:24]


def _json(nesne) -> str:
    return json.dumps(maskele_nesne(nesne), ensure_ascii=False)


def sahip_kimligi() -> str:
    """Identifies this running JARVIS: pid (to detect a dead owner) plus a random part."""
    return f'{os.getpid()}:{uuid.uuid4().hex[:8]}'


def _sahip_yasiyor(sahip: str) -> bool:
    try:
        pid = int((sahip or '').split(':')[0])
    except ValueError:
        return False
    if pid == os.getpid():
        return True
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        return False


class Depo:
    def __init__(self, yol: Path) -> None:
        self.yol = Path(yol)
        self._kilit = threading.Lock()
        onceden_vardi = self.yol.exists() and self.yol.stat().st_size > 0
        self._db = sqlite3.connect(str(self.yol), check_same_thread=False, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute('PRAGMA journal_mode=WAL')
        self._db.execute('PRAGMA busy_timeout=5000')
        self.fts = False
        self._gocur(onceden_vardi)
        if not self.fts:
            try:
                self._db.execute('SELECT 1 FROM hafiza_fts LIMIT 1')
                self.fts = True
            except sqlite3.OperationalError:
                pass

    # ------------------------------------------------------------- migrations
    def _gocur(self, onceden_vardi: bool) -> None:
        surum = self._db.execute('PRAGMA user_version').fetchone()[0]
        if surum >= SURUM:
            return
        tablolar = {r[0] for r in self._db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if onceden_vardi and 'gorevler' in tablolar:
            self._db.execute('PRAGMA wal_checkpoint(FULL)')
            shutil.copy2(self.yol, self.yol.with_name(f'{self.yol.name}.v{max(surum, 1)}.yedek'))
        self._db.executescript(SEMA_V1)
        for tablo, kolonlar in (('gorevler', GOREV_V2), ('adimlar', ADIM_V2), ('hafiza', HAFIZA_V4)):
            mevcut = {r[1] for r in self._db.execute(f'PRAGMA table_info({tablo})')}
            for ad, tur in kolonlar:
                if ad not in mevcut:
                    self._db.execute(f'ALTER TABLE {tablo} ADD COLUMN {ad} {tur}')
        self._db.execute(KARANTINA)
        self._db.execute(OLCUMLER)
        try:
            self._db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS hafiza_fts USING fts5(metin, content='hafiza', "
                             "content_rowid='id', tokenize='unicode61 remove_diacritics 2')")
            self._db.execute("INSERT INTO hafiza_fts(hafiza_fts) VALUES('rebuild')")
            self.fts = True
        except sqlite3.OperationalError:
            self.fts = False
        self._db.execute('CREATE INDEX IF NOT EXISTS adim_eylem ON adimlar(gorev_id, amac)')
        self._karantinaya_al()
        self._db.execute(f'PRAGMA user_version={SURUM}')

    def _karantinaya_al(self) -> None:
        """Old checkpoints masked after JSON encoding can be broken JSON: move them aside."""
        for r in self._db.execute('SELECT id, durum, mesajlar FROM gorevler').fetchall():
            try:
                json.loads(r['mesajlar'] or '[]')
            except ValueError:
                self._db.execute('INSERT INTO karantina (tablo, kayit_id, alan, veri, sebep, tarih) VALUES (?,?,?,?,?,?)',
                                 ('gorevler', r['id'], 'mesajlar', r['mesajlar'], 'geçersiz JSON', time.time()))
                yeni_durum = 'bozuk_kayit' if r['durum'] in ('calisiyor', 'yarida_kaldi') else r['durum']
                self._db.execute("UPDATE gorevler SET mesajlar='[]', durum=? WHERE id=?", (yeni_durum, r['id']))

    def karantina(self) -> list:
        return [dict(r) for r in self._calistir('SELECT * FROM karantina ORDER BY id')]

    def _calistir(self, sql: str, params=()):
        with self._kilit:
            return self._db.execute(sql, params)

    def calistir_ham(self, sql: str, params=()):
        """For tests and maintenance tools only."""
        return self._calistir(sql, params)

    # ------------------------------------------------------------- tasks
    def gorev_olustur(self, istek: str, model: str, kaynak: str = 'model', sahip: str = None) -> str:
        gid = uuid.uuid4().hex[:8]
        simdi = time.time()
        self._calistir('INSERT INTO gorevler (id, istek, durum, olusturma, guncelleme, model, kaynak, sahip) '
                       'VALUES (?,?,?,?,?,?,?,?)',
                       (gid, maskele(istek), 'calisiyor', simdi, simdi, model, kaynak, sahip))
        return gid

    def gorev_guncelle(self, gid: str, **alanlar) -> None:
        alanlar['guncelleme'] = time.time()
        for k in ('mesajlar', 'kontrol_noktasi'):
            if k in alanlar:
                alanlar[k] = _json(alanlar[k])
        for k in ('sonuc', 'hata', 'istek'):
            if k in alanlar:
                alanlar[k] = maskele(alanlar[k])
        sutunlar = ', '.join(f'{k}=?' for k in alanlar)
        self._calistir(f'UPDATE gorevler SET {sutunlar} WHERE id=?', (*alanlar.values(), gid))

    def gorev(self, gid: str):
        satir = self._calistir('SELECT * FROM gorevler WHERE id=?', (gid,)).fetchone()
        return dict(satir) if satir else None

    def gorevler(self, sinir: int = 20) -> list:
        return [dict(r) for r in self._calistir(
            'SELECT id, istek, durum, olusturma, guncelleme, sonuc, kaynak FROM gorevler '
            'ORDER BY olusturma DESC LIMIT ?', (sinir,))]

    def gorev_sayisi(self) -> int:
        return self._calistir('SELECT count(*) FROM gorevler').fetchone()[0]

    def yarim_kalanlari_isaretle(self) -> list:
        """On startup: 'calisiyor' tasks whose owner process is gone were cut off by a crash.
        Tasks still owned by another live JARVIS are left alone."""
        ids = []
        for r in self._calistir("SELECT id, sahip FROM gorevler WHERE durum='calisiyor'").fetchall():
            if r['sahip'] and _sahip_yasiyor(r['sahip']) and int(r['sahip'].split(':')[0]) != os.getpid():
                continue
            self.gorev_guncelle(r['id'], durum='yarida_kaldi')
            ids.append(r['id'])
        return ids

    def gorevi_sahiplen(self, gid: str, sahip: str) -> bool:
        """Atomically take over a cut-off task; False if someone else already did."""
        cur = self._calistir("UPDATE gorevler SET durum='calisiyor', sahip=?, guncelleme=? "
                             "WHERE id=? AND durum='yarida_kaldi'", (sahip, time.time(), gid))
        return cur.rowcount == 1

    # ------------------------------------------------------------- steps
    def adim_baslat(self, gid: str, sira: int, arac: str, argumanlar: dict, eylem_id: str = None,
                    amac: str = None, deneme: int = 1) -> int:
        cur = self._calistir(
            'INSERT INTO adimlar (gorev_id, sira, arac, argumanlar, anahtar, durum, baslangic, eylem_id, amac, deneme) '
            'VALUES (?,?,?,?,?,?,?,?,?,?)',
            (gid, sira, arac, _json(argumanlar), anahtar_uret(arac, argumanlar), 'basladi', time.time(),
             eylem_id or uuid.uuid4().hex[:12], amac, deneme))
        return cur.lastrowid

    def adim_bitir(self, adim_id: int, durum: str, cikti: str, dogrulandi=None, geri_al=None,
                   hata_turu: str = None, veri: dict = None, sonuc_durumu: str = None) -> None:
        self._calistir('UPDATE adimlar SET durum=?, cikti=?, dogrulandi=?, geri_al=?, bitis=?, hata_turu=?, veri=?, '
                       'sonuc_durumu=? WHERE id=?',
                       (durum, maskele(cikti), None if dogrulandi is None else int(dogrulandi),
                        _json(geri_al) if geri_al else None, time.time(), hata_turu,
                        _json(veri) if veri else None, sonuc_durumu, adim_id))

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

    # ------------------------------------------------------------- measurements
    def olcum_ekle(self, gid: str, tur: int, olcum: dict, is_turu: str = '', arac_sayisi: int = 0) -> None:
        self._calistir('INSERT INTO olcumler (gorev_id, tur, model, is_turu, arac_sayisi, toplam_sn, ilk_parca_sn, '
                       'yukleme_sn, prompt_sn, uretim_sn, prompt_token, uretim_token, soguk, tarih) '
                       'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (gid, tur, olcum.get('model'), is_turu, arac_sayisi, olcum.get('toplam_sn'),
                        olcum.get('ilk_parca_sn'), olcum.get('yukleme_sn'), olcum.get('prompt_sn'),
                        olcum.get('uretim_sn'), olcum.get('prompt_token'), olcum.get('uretim_token'),
                        int(bool(olcum.get('soguk'))), time.time()))

    def olcum_ozeti(self, sinir: int = 200) -> list:
        """Averages per model, warm and cold starts reported separately."""
        return [dict(r) for r in self._calistir(
            'SELECT model, soguk, count(*) AS tur_sayisi, avg(toplam_sn) AS ort_toplam, avg(ilk_parca_sn) AS ort_ilk, '
            'avg(yukleme_sn) AS ort_yukleme, sum(uretim_token) / nullif(sum(uretim_sn), 0) AS token_hizi, '
            'sum(prompt_token) / nullif(sum(prompt_sn), 0) AS prompt_hizi, avg(arac_sayisi) AS ort_arac '
            'FROM (SELECT * FROM olcumler ORDER BY id DESC LIMIT ?) GROUP BY model, soguk', (sinir,))]

    # ------------------------------------------------------------- memory
    # Layers: tur = tercih | kisisel | proje | deneyim. A record with the same `konu` (topic key,
    # e.g. "kullanıcının adı") supersedes the older one, which stays in history but is no longer
    # active. dogruluk: 'kullanici' (the user said it) or 'dogrulanmadi' (came from web/file
    # content) -- untrusted claims are never stored as user facts.
    def hafiza_ekle(self, metin: str, kaynak: str, tur: str = 'tercih', konu: str = None,
                    dogruluk: str = 'kullanici') -> int:
        metin = maskele(metin)
        with self._kilit:
            kimlik = self._db.execute('INSERT INTO hafiza (metin, tur, kaynak, tarih, konu, dogruluk) '
                                      'VALUES (?,?,?,?,?,?)',
                                      (metin, tur, kaynak, time.time(), (konu or '').strip().lower() or None,
                                       dogruluk)).lastrowid
            if konu:
                self._db.execute('UPDATE hafiza SET aktif=0, yerine_gecen=? WHERE aktif=1 AND konu=? AND id<>?',
                                 (kimlik, konu.strip().lower(), kimlik))
            if self.fts:
                self._db.execute('INSERT INTO hafiza_fts(rowid, metin) VALUES (?,?)', (kimlik, metin))
        return kimlik

    def hafiza(self, sadece_aktif: bool = True) -> list:
        sql = 'SELECT * FROM hafiza' + (' WHERE aktif=1' if sadece_aktif else '') + ' ORDER BY tarih'
        return [dict(r) for r in self._calistir(sql)]

    def hafiza_ara(self, sorgu: str, sinir: int = 8) -> list:
        """Active records relevant to `sorgu` (FTS5 bm25), best first."""
        kelimeler = [k for k in __import__('re').findall(r'\w{3,}', (sorgu or '').lower())][:12]
        if not kelimeler:
            return []
        if self.fts:
            ifade = ' OR '.join(f'"{k}"*' for k in kelimeler)
            try:
                return [dict(r) for r in self._calistir(
                    'SELECT h.* FROM hafiza_fts f JOIN hafiza h ON h.id=f.rowid WHERE hafiza_fts MATCH ? '
                    'AND h.aktif=1 ORDER BY bm25(hafiza_fts) LIMIT ?', (ifade, sinir))]
            except sqlite3.OperationalError:
                pass
        kosul = ' OR '.join('lower(metin) LIKE ?' for _ in kelimeler)
        return [dict(r) for r in self._calistir(f'SELECT * FROM hafiza WHERE aktif=1 AND ({kosul}) LIMIT ?',
                                                 (*[f'%{k}%' for k in kelimeler], sinir))]

    def hafiza_unut(self, parca: str) -> int:
        """Forget: inactive in prompts and search; the text is removed from the search index.
        (Older database backups made before this may still contain it.)"""
        with self._kilit:
            ids = [r[0] for r in self._db.execute('SELECT id FROM hafiza WHERE aktif=1 AND lower(metin) LIKE ?',
                                                  (f'%{parca.lower()}%',))]
            for i in ids:
                if self.fts:
                    eski = self._db.execute('SELECT metin FROM hafiza WHERE id=?', (i,)).fetchone()[0]
                    self._db.execute("INSERT INTO hafiza_fts(hafiza_fts, rowid, metin) VALUES('delete', ?, ?)",
                                     (i, eski))
                self._db.execute("UPDATE hafiza SET aktif=0, metin='[unutuldu]' WHERE id=?", (i,))
        return len(ids)
