"""Screen understanding through an Ollama vision model. The answer describes
what is on screen, so it is treated as untrusted data (a page on screen can
contain injected instructions)."""
import os
import tempfile

from ..ayarlar import Ayarlar
from ..izinler import OKUMA
from .temel import Sonuc, arac, metin


@arac('ekrani_gor', 'Ekranın görüntüsünü alır ve görsel modelle ekrandaki şey hakkındaki soruyu yanıtlar.',
      {'soru': metin('Ekranla ilgili soru, ör. "Ekranda hangi hata yazıyor?"')}, ['soru'],
      risk=OKUMA, yan_etki=False, zaman_asimi=240, guvenilmez_cikti=True)
def ekrani_gor(baglam, soru):
    import ollama
    import pyautogui
    a = Ayarlar()
    model = a.model('gorsel')
    istemci = ollama.Client(host=a.ollama_adres, timeout=a.llm_zaman_asimi)
    try:
        if 'vision' not in (istemci.show(model).capabilities or []):
            return Sonuc(False, f'{model} görsel anlamayı desteklemiyor; .env içinde OLLAMA_MODEL_GORSEL ayarlayın.')
    except Exception as e:
        return Sonuc(False, f'Görsel model kullanılamıyor: {e}')
    try:
        goruntu = pyautogui.screenshot()
    except Exception as e:
        return Sonuc(False, f'Ekran görüntüsü alınamadı: {e}')
    goruntu.thumbnail((1600, 1600))
    fd, yol = tempfile.mkstemp(suffix='.png')
    os.close(fd)
    try:
        goruntu.save(yol)
        baglam.kontrol()
        cevap = istemci.chat(model=model, think=False, options={'num_ctx': a.baglam}, messages=[
            {'role': 'user', 'content': f'{soru} Türkçe ve kısa yanıtla.', 'images': [yol]}])
        return Sonuc(True, cevap.message.content)
    finally:
        os.remove(yol)
