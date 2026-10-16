"""Permission policy. Decides per call: 'izin' (run), 'sor' (ask the user)
or 'red' (refuse). Only the user changes rules (CLI / panel); nothing a tool
returns or a web page says can reach this module."""
import json
import re
import time
from pathlib import Path, PureWindowsPath

from . import yollar

# Risk levels, decided by the tool itself (not by the model).
OKUMA, YAZMA, SILME, PROGRAM, DIS_ILETISIM, SISTEM = 'okuma', 'yazma', 'silme', 'program', 'dis_iletisim', 'sistem'
# These always need an explicit yes for that very action; rules cannot pre-approve them.
HER_SEFERINDE_SOR = {DIS_ILETISIM, SISTEM}

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


class Izinler:
    def __init__(self, dosya: Path) -> None:
        self.dosya = Path(dosya)
        self.veri = {'kurallar': [], 'programlar': list(VARSAYILAN_PROGRAMLAR)}
        if self.dosya.exists():
            try:
                self.veri.update(json.loads(self.dosya.read_text(encoding='utf-8')))
            except ValueError:
                pass

    def _kaydet(self) -> None:
        self.dosya.parent.mkdir(parents=True, exist_ok=True)
        self.dosya.write_text(json.dumps(self.veri, ensure_ascii=False, indent=1), encoding='utf-8')

    # ------------------------------------------------------------- user-facing
    def kurallar(self) -> list:
        return list(self.veri['kurallar'])

    def kural_ekle(self, arac: str = '*', klasor: str = '', karar: str = 'izin') -> dict:
        kural = {'arac': arac, 'klasor': str(yollar.coz(klasor)) if klasor else '', 'karar': karar,
                 'eklenme': time.strftime('%Y-%m-%d %H:%M')}
        self.veri['kurallar'].append(kural)
        self._kaydet()
        return kural

    def kural_sil(self, sira: int) -> bool:
        if 0 <= sira < len(self.veri['kurallar']):
            del self.veri['kurallar'][sira]
            self._kaydet()
            return True
        return False

    def program_ekle(self, program: str) -> None:
        if program not in self.veri['programlar']:
            self.veri['programlar'].append(program)
            self._kaydet()

    # ------------------------------------------------------------- decision
    def karar(self, arac, argumanlar: dict):
        """Returns (karar, sebep)."""
        yollar_ = [yollar.coz(argumanlar[a]) for a in arac.yol_argumanlari if argumanlar.get(a)]

        def eslesir(kural):
            if kural['arac'] not in ('*', arac.ad):
                return False
            return not kural['klasor'] or (yollar_ and all(yollar.icinde_mi(y, kural['klasor']) for y in yollar_))

        for kural in self.veri['kurallar']:
            if kural['karar'] == 'red' and eslesir(kural):
                return 'red', 'kullanıcı kuralı bunu yasaklıyor'

        if arac.risk in HER_SEFERINDE_SOR:
            return 'sor', f'{arac.risk} işlemi her seferinde onay ister'

        for kural in self.veri['kurallar']:
            if kural['karar'] == 'izin' and eslesir(kural):
                return 'izin', 'kullanıcı kuralı'

        if arac.risk == OKUMA:
            return 'izin', 'okuma'
        if arac.ad == 'metin_yaz' and TERMINAL.search(str(argumanlar.get('pencere', ''))):
            return 'sor', 'terminal penceresine yazılan metin komut olarak çalışabilir'
        if arac.risk == YAZMA:
            kokler = yollar.guvenli_kokler()
            if all(any(yollar.icinde_mi(y, k) for k in kokler) for y in yollar_):
                return 'izin', 'güvenli klasör'
            return 'sor', 'güvenli klasörlerin dışına yazma'
        if arac.risk == PROGRAM:
            program = PureWindowsPath(str(argumanlar.get('program', ''))).stem.lower()  # handles \ and /
            if program in KABUKLAR:
                return 'red', f'{program} bir komut kabuğu; JARVIS kabuk komutu çalıştırmaz'
            args = [str(a) for a in argumanlar.get('argumanlar') or []]
            # first non-option argument is the subcommand ("git -C x push" -> push)
            ilk, atla = '', False
            for a in args:
                if atla:
                    atla = False
                elif a in ('-C', '-c', '--git-dir', '--work-tree', '--namespace'):
                    atla = True
                elif not a.startswith('-'):
                    ilk = a.lower()
                    break
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
