"""JARVIS — Turkish voice assistant.

    python jarvis.py         # listen on the microphone
    python jarvis.py --yaz   # type commands instead
"""
import datetime
import os
import sys

PROJE = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJE)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(PROJE, '.env'))

import komutlar  # noqa: E402
import ses  # noqa: E402
from beyin import Beyin  # noqa: E402


def selamla() -> None:
    saat = datetime.datetime.now().hour
    if 5 <= saat < 12:
        selam = 'Günaydın efendim.'
    elif 12 <= saat < 18:
        selam = 'İyi günler efendim.'
    elif 18 <= saat < 23:
        selam = 'İyi akşamlar efendim.'
    else:
        selam = 'İyi geceler efendim.'
    ses.konus(f'{selam} Ben JARVIS. Size nasıl yardımcı olabilirim?')


def main() -> None:
    if '--yaz' in sys.argv:
        ses.yazi_modunu_ac()
    elif not ses.mikrofon_var():
        print('Mikrofon bulunamadı, yazı moduna geçiliyor.')
        ses.yazi_modunu_ac()

    beyin = Beyin()
    if beyin.aktif:
        print(f'Yapay zeka: {beyin.ad}')
    else:
        print('Not: yapay zeka kapalı, yalnız hazır komutlar çalışır. Sorunu görmek için: python -m jarvis_core.saglik')
    from jarvis_core.acil import acil_durdurma_kur
    kisayol = acil_durdurma_kur(beyin.iptal)
    if kisayol:
        print(f'Acil durdurma: {kisayol}')

    from jarvis_core.zamanlayici import Zamanlayici
    Zamanlayici(beyin.depo, teslim=lambda k: ses.konus(k['metin_soz']), sahip=beyin.motor.sahip).baslat()

    selamla()
    while True:
        metin = ses.dinle()
        try:
            devam = komutlar.isle(metin, beyin)
        except Exception as e:
            print(f'Hata: {e!r}')
            ses.konus('Bunu yaparken bir hata oluştu efendim.')
            devam = True
        if not devam:
            break


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nGörüşürüz.')
