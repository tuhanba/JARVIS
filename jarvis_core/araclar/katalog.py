"""Tool discovery: the model sees only the tools picked for a request
(arac_secimi.py); this lists the rest. After it is called the engine sends
the whole catalogue for the remainder of the task."""
from ..izinler import OKUMA
from .temel import KAYIT, Sonuc, arac


@arac('arac_katalogu', 'Kullanabileceğin TÜM araçların listesini verir. Gereken araç elindeki listede yoksa önce '
      'bunu çağır; sonraki adımda hepsi kullanılabilir olur.', {}, [], risk=OKUMA, yan_etki=False)
def arac_katalogu(baglam):
    satirlar = [f'- {a.ad}: {a.aciklama.split(". ")[0]}' for a in KAYIT.values()
                if a.modele_acik and a.ad != 'arac_katalogu']
    return Sonuc(True, 'Bütün araçlar artık kullanılabilir:\n' + '\n'.join(satirlar))
