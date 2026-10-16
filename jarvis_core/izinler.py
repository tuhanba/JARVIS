"""Permission policy. Decides per call: 'izin' (run), 'sor' (ask the user)
or 'red' (refuse). Only the user changes rules (CLI / panel); nothing a tool
returns or a web page says can reach this module."""
import json
import os
import re
import time
from pathlib import Path, PureWindowsPath

from . import yollar

# Risk levels, decided by the tool itself (not by the model).
OKUMA, YAZMA, SILME, PROGRAM, DIS_ILETISIM, SISTEM = 'okuma', 'yazma', 'silme', 'program', 'dis_iletisim', 'sistem'
# Always needs an explicit yes for that very action; no rule can pre-approve it.
HER_SEFERINDE_SOR = {DIS_ILETISIM}
# SISTEM (power off, restart...) asks by default; a rule naming the tool can allow it.

# Read-mostly programs. Interpreters and package managers (python, node, pip, npm)
# are left out on purpose: they run arbitrary code, so they ask unless the user adds them.
VARSAYILAN_PROGRAMLAR = ['git', 'ollama', 'where', 'whoami', 'ipconfig', 'ping', 'systeminfo', 'tasklist',
                         'hostname', 'nvidia-smi']
TERMINAL = re.compile(r'powershell|komut istemi|command prompt|cmd|terminal|bash|wsl|ubuntu|conemu|'
                      r'windows terminal|git bash|python', re.IGNORECASE)
# Shells and script hosts turn one argument into arbitrary commands: never allowed,
# not even with a yes (the model writes the arguments, not the user).
KABUKLAR = {'powershell', 'pwsh', 'cmd', 'bash', 'sh', 'zsh', 'wsl', 'wscript', 'cscript', 'mshta',
            'rundll32', 'regsvr32', 'certutil', 'bitsadmin', 'msiexec', 'schtasks', 'reg', 'sc', 'net',
            'netsh', 'bcdedit', 'diskpart', 'format', 'takeown', 'icacls', 'vssadmin', 'wmic', 'cipher'}
GIT_DIS_ETKI = {'push', 'reset', 'clean', 'checkout', 'restore', 'rebase', 'rm', 'mv', 'commit', 'merge',
                'pull', 'clone', 'remote', 'config', 'stash', 'branch', 'tag', 'switch', 'am', 'apply'}


# Programs that only read state. Their exit code 0 means "the read worked"; for
# everything else exit 0 is only "the process ran" (not that the user's goal was met).
SALT_OKUNUR_PROGRAMLAR = {'where', 'whoami', 'ipconfig', 'ping', 'systeminfo', 'tasklist', 'hostname', 'nvidia-smi'}
GIT_OKUMA = {'status', 'log', 'diff', 'show', 'rev-parse', 'ls-files', 'blame', 'describe', 'shortlog', 'grep'}
OLLAMA_OKUMA = {'list', 'ls', 'ps', 'show', '--version', '-v'}
# Fast-command-only power tools that JARVIS_TAM_YETKI=1 used to run without asking.
TAM_YETKI_ARACLARI = ('bilgisayari_kapat', 'yeniden_baslat', 'uyku_moduna_al', 'notlari_sil')
# A '*' rule only covers ordinary file risks. Programs, system actions and outside
# communication need a rule that names the tool.
JOKER_KAPSAMI = {OKUMA, YAZMA, SILME}


def _alt_komut(args: list) -> str:
    """First non-option argument ("git -C x push" -> push)."""
    atla = False
    for a in args:
        if atla:
            atla = False
        elif a in ('-C', '-c', '--git-dir', '--work-tree', '--namespace'):
            atla = True
        elif not a.startswith('-'):
            return a.lower()
    return ''


def program_adi(argumanlar: dict) -> str:
    return PureWindowsPath(str(argumanlar.get('program', ''))).stem.lower()  # handles \ and /


def salt_okunur_program(argumanlar: dict) -> bool:
    program = program_adi(argumanlar)
    args = [str(a) for a in argumanlar.get('argumanlar') or []]
    if program in SALT_OKUNUR_PROGRAMLAR:
        return True
    if program == 'git':
        return _alt_komut(args) in GIT_OKUMA and not any(a.startswith(('-c', '--config', '--exec-path', '--output'))
                                                          for a in args)
    if program == 'ollama':
        return (_alt_komut(args) or (args[0] if args else '')) in OLLAMA_OKUMA
    return False


class Izinler:
    """Order of a decision (first match wins):
    1. immutable limits (shell programs are refused; typing into a terminal and
       outside communication always ask) -- no rule or setting changes these;
    2. the user's 'red' rules;
    3. the user's 'izin' rules ('*' only for read/write/delete of files);
    4. defaults by risk.
    The rule file is re-read when it changes, so a permission revoked in the
    panel or CLI applies to the very next call of a running task."""

    def __init__(self, dosya: Path) -> None:
        self.dosya = Path(dosya)
        self._mtime = None
        self.veri = {'kurallar': [], 'programlar': list(VARSAYILAN_PROGRAMLAR)}
        self._yukle()
        self._tam_yetki_tasi()

    def _yukle(self) -> None:
        try:
            st = self.dosya.stat()
            mtime = (st.st_mtime_ns, st.st_size)
        except OSError:
            return
        if mtime == self._mtime:
            return
        try:
            veri = json.loads(self.dosya.read_text(encoding='utf-8'))
            self.veri = {'kurallar': [], 'programlar': list(VARSAYILAN_PROGRAMLAR)}
            self.veri.update(veri)
            self._mtime = mtime
        except (ValueError, OSError):
            pass

    def _kaydet(self) -> None:
        self.dosya.parent.mkdir(parents=True, exist_ok=True)
        gecici = self.dosya.with_name(self.dosya.name + '.tmp')
        gecici.write_text(json.dumps(self.veri, ensure_ascii=False, indent=1), encoding='utf-8')
        os.replace(gecici, self.dosya)
        st = self.dosya.stat()
        self._mtime = (st.st_mtime_ns, st.st_size)

    def _tam_yetki_tasi(self) -> None:
        """JARVIS_TAM_YETKI=1 skipped the yes for power actions. Keep that behaviour, but as
        visible, removable rules for those tools only (never a blanket bypass)."""
        if os.getenv('JARVIS_TAM_YETKI') != '1' or self.veri.get('tam_yetki_tasindi'):
            return
        for ad in TAM_YETKI_ARACLARI:
            self.veri['kurallar'].append({'arac': ad, 'klasor': '', 'karar': 'izin',
                                          'eklenme': time.strftime('%Y-%m-%d %H:%M'),
                                          'kaynak': 'JARVIS_TAM_YETKI (.env, taşındı)'})
        self.veri['tam_yetki_tasindi'] = True
        self._kaydet()

    # ------------------------------------------------------------- user-facing
    def kurallar(self) -> list:
        self._yukle()
        return list(self.veri['kurallar'])

    def kural_ekle(self, arac: str = '*', klasor: str = '', karar: str = 'izin', kaynak: str = 'kullanıcı') -> dict:
        self._yukle()
        kural = {'arac': arac, 'klasor': str(yollar.coz(klasor)) if klasor else '', 'karar': karar,
                 'eklenme': time.strftime('%Y-%m-%d %H:%M'), 'kaynak': kaynak}
        self.veri['kurallar'].append(kural)
        self._kaydet()
        return kural

    def kural_sil(self, sira: int) -> bool:
        self._yukle()
        if 0 <= sira < len(self.veri['kurallar']):
            del self.veri['kurallar'][sira]
            self._kaydet()
            return True
        return False

    def program_ekle(self, program: str) -> None:
        self._yukle()
        if program not in self.veri['programlar']:
            self.veri['programlar'].append(program)
            self._kaydet()

    # ------------------------------------------------------------- decision
    def karar(self, arac, argumanlar: dict):
        """Returns (karar, sebep)."""
        self._yukle()
        yollar_ = [yollar.coz(argumanlar[a]) for a in arac.yol_argumanlari if argumanlar.get(a)]

        # 1. immutable limits
        if arac.risk == PROGRAM:
            program = program_adi(argumanlar)
            if program in KABUKLAR:
                return 'red', f'{program} bir komut kabuğu; JARVIS kabuk komutu çalıştırmaz'
        terminale_yazma = arac.ad == 'metin_yaz' and TERMINAL.search(str(argumanlar.get('pencere', '')))

        def eslesir(kural):
            if kural['arac'] == '*':
                if arac.risk not in JOKER_KAPSAMI or terminale_yazma:
                    return False
            elif kural['arac'] != arac.ad:
                return False
            return not kural['klasor'] or (yollar_ and all(yollar.icinde_mi(y, kural['klasor']) for y in yollar_))

        # 2. user's refusals (a '*' refusal covers everything)
        for kural in self.veri['kurallar']:
            if kural['karar'] == 'red' and (kural['arac'] in ('*', arac.ad)) and (
                    not kural['klasor'] or (yollar_ and all(yollar.icinde_mi(y, kural['klasor']) for y in yollar_))):
                return 'red', 'kullanıcı kuralı bunu yasaklıyor'

        if arac.risk in HER_SEFERINDE_SOR:
            return 'sor', f'{arac.risk} işlemi her seferinde onay ister'
        if terminale_yazma:
            return 'sor', 'terminal penceresine yazılan metin komut olarak çalışabilir'

        # 3. user's permissions
        for kural in self.veri['kurallar']:
            if kural['karar'] == 'izin' and eslesir(kural):
                return 'izin', 'kullanıcı kuralı' + (f" ({kural['kaynak']})" if kural.get('kaynak', 'kullanıcı')
                                                    != 'kullanıcı' else '')

        # 4. defaults
        if arac.risk == OKUMA:
            return 'izin', 'okuma'
        if arac.risk == YAZMA:
            kokler = yollar.guvenli_kokler()
            if all(any(yollar.icinde_mi(y, k) for k in kokler) for y in yollar_):
                return 'izin', 'güvenli klasör'
            return 'sor', 'güvenli klasörlerin dışına yazma'
        if arac.risk == PROGRAM:
            program = program_adi(argumanlar)
            args = [str(a) for a in argumanlar.get('argumanlar') or []]
            ilk = _alt_komut(args)
            if program == 'git':
                # -c / --config-env / --exec-path can make git run arbitrary programs
                if any(a == '-c' or a.startswith(('-c', '--config', '--exec-path', '--upload-pack',
                                                   '--receive-pack', '-u')) for a in args):
                    return 'sor', 'git ayar/yürütme parametresi içeriyor'
                if ilk in GIT_DIS_ETKI:
                    return 'sor', f'git {ilk} depoyu değiştirir veya dışarı gönderir'
            if program == 'ollama' and ilk in ('rm', 'push', 'cp', 'create'):
                return 'sor', f'ollama {ilk} modelleri değiştirir'
            if program in [p.lower() for p in self.veri['programlar']]:
                return 'izin', 'izinli program'
            return 'sor', f'{program} izinli programlar listesinde değil'
        return 'sor', arac.risk
