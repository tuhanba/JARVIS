"""Run a program with an argument list. There is no shell: no pipes,
redirection or command chaining, and unknown programs need a yes.

Exit code 0 only says the process ran without error. It is reported as
'succeeded', never as 'verified': whether the user's goal was reached (a file
exists, tests passed, a page loads) must be checked separately. Known read-only
invocations (git status, ipconfig...) count as reads."""
import shutil
import sys

from ..izinler import PROGRAM, salt_okunur_program
from .temel import Sonuc, arac, metin, yollar_yardim


@arac('program_calistir', 'Bir komut satırı programını argüman listesiyle çalıştırır (kabuk yok). '
      'Ör. program="git", argumanlar=["status"]. İzinli listede olmayan programlar için kullanıcı onayı istenir.',
      {'program': metin('Program adı, ör. "git", "python", "ipconfig"'),
       'argumanlar': {'type': 'array', 'items': {'type': 'string'}, 'maxItems': 50, 'description': 'Argümanlar'},
       'klasor': metin('Çalışma klasörü (isteğe bağlı)')},
      ['program', 'argumanlar'], risk=PROGRAM, yan_etki=True, yol_argumanlari=('klasor',), zaman_asimi=300)
def program_calistir(baglam, program, argumanlar, klasor=''):
    yol = shutil.which(program) or (shutil.which(program + '.exe') if sys.platform == 'win32' else None)
    if not yol:
        return Sonuc(False, f'"{program}" bulunamadı (kurulu ve PATH\'te mi?).', dogrulandi=False)
    cwd = yollar_yardim(klasor)
    try:
        p = baglam.surec([yol, *argumanlar], zaman_asimi=280, cwd=cwd)
    except TimeoutError as e:
        return Sonuc(False, str(e), dogrulandi=False, hata_turu='zaman_asimi')
    cikti = ((p.stdout or '') + (p.stderr or '')).strip()[:6000] or '(çıktı yok)'
    okuma = salt_okunur_program({'program': program, 'argumanlar': argumanlar})
    return Sonuc(p.returncode == 0, f'çıkış kodu {p.returncode}\n{cikti}', dogrulandi=None,
                 veri={'cikis_kodu': p.returncode, 'salt_okunur': okuma},
                 hata_turu='' if p.returncode == 0 else 'cikis_kodu')
