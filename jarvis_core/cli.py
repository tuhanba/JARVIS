"""Text interface for the task engine.

    python -m jarvis_core

While a task runs you can type "dur" (or press Ctrl+C) to cancel it.
Questions that need a yes/no are answered on the same prompt."""
import queue
import sys
import threading
import time

from .motor import DURDUR, Motor

YARDIM = """Komutlar:
  /gorevler              son görevler          /gorev <id>        görevin adımları
  /devam <id>            yarıda kalanı sürdür  /geri-al           son dosya işlemini geri al
  /izinler               kuralları göster      /izin-ver <araç|*> [klasör]
  /izin-yasakla <araç|*> [klasör]              /izin-sil <no>
  /program-ekle <ad>     programı izinli yap   /hafiza            kalıcı hafıza
  /hatirla <bilgi>       hafızaya ekle         /unut <parça>      hafızadan sil
  /saglik                sistem raporu         /cikis
Görev çalışırken "dur" yazın veya Ctrl+C'ye basın."""


class Arayuz:
    def __init__(self) -> None:
        self.cevaplar = queue.Queue()
        self.onay_bekliyor = threading.Event()
        self.motor = Motor(onay=self._onay, bildir=self._bildir)
        self.is_parcacigi = None

    # ------------------------------------------------------------- callbacks (worker thread)
    def _onay(self, soru: str) -> bool:
        print(f'\n  ? {soru} (evet/hayır)')
        self.onay_bekliyor.set()
        try:
            cevap = self.cevaplar.get(timeout=120)
        except queue.Empty:
            print('  (cevap gelmedi, hayır sayıldı)')
            return False
        finally:
            self.onay_bekliyor.clear()
        return cevap.strip().lower() in ('e', 'evet', 'tamam', 'olur', 'onaylıyorum', 'yes', 'y')

    def _bildir(self, olay: str, veri: dict) -> None:
        if olay == 'arac':
            argumanlar = ', '.join(f'{k}={str(v)[:60]}' for k, v in veri['argumanlar'].items())
            print(f'  > {veri["arac"]}({argumanlar})')
        elif olay == 'arac_sonuc':
            print(f'    {"ok" if veri["basarili"] else "HATA"}: {veri["cikti"][:160]}')

    # ------------------------------------------------------------- tasks
    def _gorev_baslat(self, is_) -> None:
        def calis():
            t0 = time.time()
            sonuc = is_()
            print(f'\nJARVIS [{sonuc.durum}, {time.time() - t0:.1f} sn, görev {sonuc.gorev_id}]: {sonuc.cevap}')
            print('Sen: ', end='', flush=True)
        self.is_parcacigi = threading.Thread(target=calis, daemon=True)
        self.is_parcacigi.start()

    def calisiyor(self) -> bool:
        return bool(self.is_parcacigi and self.is_parcacigi.is_alive())

    # ------------------------------------------------------------- slash commands
    def komut(self, satir: str) -> bool:
        m, depo, izin = self.motor, self.motor.depo, self.motor.izinler
        parca = satir.split(maxsplit=2)
        k = parca[0].lower()
        if k in ('/cikis', '/çıkış', '/q'):
            return False
        if k == '/yardim':
            print(YARDIM)
        elif k == '/gorevler':
            for g in depo.gorevler():
                print(f"  {g['id']}  {time.strftime('%d.%m %H:%M', time.localtime(g['olusturma']))}  "
                      f"{g['durum']:<14} {g['istek'][:60]}")
        elif k == '/gorev' and len(parca) > 1:
            for a in depo.adimlar(parca[1]):
                print(f"  {a['sira']:>2}. {a['arac']} {a['argumanlar'][:80]} -> {a['durum']}"
                      f"{' (doğrulandı)' if a['dogrulandi'] else ''}: {(a['cikti'] or '')[:100]}")
        elif k == '/devam' and len(parca) > 1:
            self._gorev_baslat(lambda: m.devam(parca[1]))
        elif k == '/geri-al':
            from .araclar.dosyalar import son_islemi_geri_al
            from .araclar.temel import Baglam
            print('  ' + son_islemi_geri_al(Baglam(threading.Event(), depo=depo)).cikti)
        elif k == '/izinler':
            print('  İzinli programlar: ' + ', '.join(izin.veri['programlar']))
            for i, r in enumerate(izin.kurallar()):
                print(f"  {i}. {r['karar']:<5} {r['arac']:<20} {r['klasor'] or '(her yer)'}  ({r['eklenme']})")
            if not izin.kurallar():
                print('  Kural yok. Varsayılan: okuma serbest; Belgeler/Masaüstü/İndirilenler/Resimler/Müzik/Videolar '
                      'içine yazma serbest; silme, dış iletişim ve sistem işlemleri onay ister.')
        elif k in ('/izin-ver', '/izin-yasakla') and len(parca) > 1:
            r = izin.kural_ekle(parca[1], parca[2] if len(parca) > 2 else '', 'izin' if k == '/izin-ver' else 'red')
            print(f"  Eklendi: {r['karar']} {r['arac']} {r['klasor'] or '(her yer)'}")
        elif k == '/izin-sil' and len(parca) > 1 and parca[1].isdigit():
            print('  Silindi.' if izin.kural_sil(int(parca[1])) else '  Böyle bir kural yok.')
        elif k == '/program-ekle' and len(parca) > 1:
            izin.program_ekle(parca[1])
            print(f'  {parca[1]} izinli programlara eklendi.')
        elif k == '/hafiza':
            for h in depo.hafiza():
                print(f"  #{h['id']} [{time.strftime('%d.%m.%Y', time.localtime(h['tarih']))}, {h['kaynak']}] {h['metin']}")
        elif k == '/hatirla' and len(parca) > 1:
            depo.hafiza_ekle(satir.split(maxsplit=1)[1], kaynak='kullanıcı (/hatirla)')
            print('  Kaydedildi.')
        elif k == '/unut' and len(parca) > 1:
            print(f"  {depo.hafiza_unut(satir.split(maxsplit=1)[1])} kayıt unutuldu.")
        elif k == '/saglik':
            from .saglik import rapor, yazdir
            yazdir(rapor())
        else:
            print('  Bilinmeyen komut. /yardim yazın.')
        return True

    # ------------------------------------------------------------- main loop
    def calistir(self) -> None:
        print('JARVIS görev motoru. /yardim ile komutlar, "dur" ile iptal.')
        try:
            model = self.motor.llm.hazirla()
            print(f'Model: {model}')
        except Exception as e:
            print(f'UYARI: {e}')
        if self.motor.yarim_kalanlar:
            print(f'Yarıda kalan görevler: {", ".join(self.motor.yarim_kalanlar)}  (sürdürmek için /devam <id>)')
        from .acil import acil_durdurma_kur
        kisayol = acil_durdurma_kur(self.motor.iptal_et)
        if kisayol:
            print(f'Acil durdurma kısayolu: {kisayol}')
        while True:
            try:
                satir = input('Sen: ').strip()
            except EOFError:
                while self.calisiyor():
                    time.sleep(0.2)
                break
            except KeyboardInterrupt:
                if self.calisiyor():
                    self.motor.iptal_et()
                    print('\n  (iptal istendi)')
                    continue
                break
            if not satir:
                continue
            if self.onay_bekliyor.is_set():
                self.cevaplar.put(satir)
                continue
            if self.calisiyor():
                if satir.lower() in DURDUR:
                    self.motor.iptal_et()
                    print('  (iptal istendi)')
                else:
                    print('  Bir görev çalışıyor. Durdurmak için "dur" yazın.')
                continue
            if satir.startswith('/'):
                if not self.komut(satir):
                    break
                continue
            self._gorev_baslat(lambda s=satir: self.motor.calistir(s))
            time.sleep(0.05)


def main() -> None:
    from dotenv import load_dotenv
    from .ayarlar import PROJE
    load_dotenv(PROJE / '.env')
    sys.path.insert(0, str(PROJE))  # legacy modules (sistem.py)
    Arayuz().calistir()


if __name__ == '__main__':
    main()
