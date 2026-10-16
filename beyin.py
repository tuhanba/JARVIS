"""AI brain. Uses a local Ollama model (free, unlimited) and/or the free
Gemini API, and lets the model drive the computer through sistem.py."""
import datetime
import getpass
import json
import os
import platform
import re
import tempfile
import threading

import sistem

TALIMAT = """Sen JARVIS'sin: {kullanici} adlı kullanıcının kişisel, Türkçe konuşan, zeki ve becerikli asistanı.
Kullanıcıya "efendim" diye hitap et.

Yanıt biçimi: Yanıtların sesli okunacak. Kısa ve doğal konuş (genelde 1-3 cümle). Markdown, liste,
emoji, kod bloğu veya adres okuma; kullanıcı açıkça uzun açıklama isterse daha uzun konuşabilirsin.

Yetkin: Kullanıcının bilgisayarında ({isletim}) tam yetkin var. Bir iş istendiğinde anlatmak yerine
araçlarla işi kendin yap. Gerekirse birden fazla aracı art arda kullan (önce bul, sonra yap, sonra kontrol et).
Uygun araç yoksa komut_calistir (PowerShell) veya python_calistir kullan.
- Güncel bilgi (haber, skor, fiyat, kişi, olay, tarih sonrası her şey) gerekiyorsa tahmin etme,
  önce internette_ara kullan, gerekirse web_sayfasi_oku ile ayrıntıya bak.
- Ekranda ne olduğu soruluyorsa ekrani_gor kullan.
- Dosya yolunu bilmiyorsan önce dosya_ara veya dosyalari_listele ile bul.
- Kullanıcı kendisi hakkında kalıcı bir şey söylerse hafizaya_kaydet aracını gerçekten çağır;
  aracı çağırmadan "kaydettim" deme.
- Tehlikeli işlemlerde araçlar kullanıcıdan zaten onay ister; sen ayrıca sorma.
- Bir araç hata verirse başka bir yolla tekrar dene; yine olmazsa nedenini kısaca söyle.

Bağlam: Şu an {zaman}. Ev klasörü: {ev}.
{hafiza}"""


def _talimat() -> str:
    hafiza = sistem.hafizayi_yukle()
    return TALIMAT.format(
        kullanici=getpass.getuser(),
        isletim=f'{platform.system()} {platform.release()}',
        zaman=sistem.saat_tarih(),
        ev=os.path.expanduser('~'),
        hafiza=('Kullanıcının sana daha önce söyledikleri (kalıcı hafıza):\n- ' + '\n- '.join(hafiza)) if hafiza else '',
    )


def _ekran_goruntusu() -> str:
    import pyautogui
    fd, yol = tempfile.mkstemp(suffix='.png')
    os.close(fd)
    goruntu = pyautogui.screenshot()
    goruntu.thumbnail((1600, 1600))
    goruntu.save(yol)
    return yol


class _Ollama:
    ad = 'Ollama'

    def __init__(self) -> None:
        import ollama
        self.model = os.getenv('OLLAMA_MODEL', 'qwen3.5:9b')
        self.istemci = ollama.Client(host=os.getenv('OLLAMA_ADRES', 'http://127.0.0.1:11434'))
        self.istemci.show(self.model)  # raises if the server is down or the model is not pulled
        self.secenekler = {'num_ctx': int(os.getenv('OLLAMA_BAGLAM', '16384'))}
        self.dusun = os.getenv('YZ_DUSUNME', '0') == '1'
        self.gecmis = []
        # Load the model into memory in the background so the first answer is fast.
        threading.Thread(target=lambda: self.istemci.generate(model=self.model, prompt='', keep_alive='30m'),
                         daemon=True).start()

    def _mesajlar(self):
        # Keep the last ~30 messages, but never start in the middle of a tool exchange.
        gecmis = self.gecmis[-30:]
        while gecmis and _rol(gecmis[0]) != 'user':
            gecmis = gecmis[1:]
        return [{'role': 'system', 'content': _talimat()}] + gecmis

    def sor(self, metin: str, araclar: list) -> str:
        harita = {f.__name__: f for f in araclar}
        self.gecmis.append({'role': 'user', 'content': metin})
        for _ in range(10):
            cevap = self.istemci.chat(model=self.model, messages=self._mesajlar(), tools=araclar,
                                      think=self.dusun, options=self.secenekler, keep_alive='30m')
            mesaj = cevap.message
            self.gecmis.append(mesaj)
            if not mesaj.tool_calls:
                return mesaj.content or 'Tamamdır efendim.'
            for cagri in mesaj.tool_calls:
                ad, argumanlar = cagri.function.name, dict(cagri.function.arguments or {})
                sonuc = _calistir(harita.get(ad), ad, argumanlar)
                self.gecmis.append({'role': 'tool', 'content': sonuc, 'tool_name': ad})
        return 'Bu iş beklediğimden uzun sürdü efendim, yarıda bıraktım.'

    def gor(self, soru: str) -> str:
        yol = _ekran_goruntusu()
        try:
            cevap = self.istemci.chat(model=self.model, think=False, options=self.secenekler, messages=[
                {'role': 'user', 'content': soru + ' (Türkçe ve kısa yanıtla.)', 'images': [yol]}])
            return cevap.message.content
        finally:
            os.remove(yol)


class _Gemini:
    ad = 'Gemini'

    def __init__(self) -> None:
        anahtar = os.getenv('GEMINI_API_KEY', '').strip()
        if not anahtar:
            raise RuntimeError('GEMINI_API_KEY yok')
        from google import genai
        from google.genai import types
        self.types = types
        self.model = os.getenv('GEMINI_MODEL', 'gemini-flash-latest')
        self.istemci = genai.Client(api_key=anahtar)
        self.sohbet = None

    def sor(self, metin: str, araclar: list) -> str:
        if self.sohbet is None:
            self.sohbet = self.istemci.chats.create(model=self.model, config=self.types.GenerateContentConfig(
                system_instruction=_talimat(), tools=araclar,
                automatic_function_calling=self.types.AutomaticFunctionCallingConfig(maximum_remote_calls=10)))
        return self.sohbet.send_message(metin).text or 'Tamamdır efendim.'

    def gor(self, soru: str) -> str:
        yol = _ekran_goruntusu()
        try:
            with open(yol, 'rb') as f:
                resim = self.types.Part.from_bytes(data=f.read(), mime_type='image/png')
            return self.istemci.models.generate_content(
                model=self.model, contents=[resim, soru + ' (Türkçe ve kısa yanıtla.)']).text
        finally:
            os.remove(yol)


def _rol(mesaj) -> str:
    return mesaj['role'] if isinstance(mesaj, dict) else mesaj.role


def _calistir(fonksiyon, ad: str, argumanlar: dict) -> str:
    if fonksiyon is None:
        return f'"{ad}" diye bir araç yok.'
    print(f'  [araç] {ad}({json.dumps(argumanlar, ensure_ascii=False)[:120]})')
    try:
        return str(fonksiyon(**argumanlar))[:6000]
    except Exception as e:
        return f'Hata: {e!r}'


def _seslendirilebilir(metin: str) -> str:
    """Strip markdown symbols and emoji, which TTS would read aloud."""
    metin = re.sub(r'[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]', '', metin)
    return re.sub(r' {2,}', ' ', re.sub(r'[*#`_]+', '', metin)).strip()


def _hata_metni(hata: Exception) -> str:
    metin = str(hata)
    if '429' in metin or 'RESOURCE_EXHAUSTED' in metin:
        return 'Gemini ücretsiz kullanım limiti doldu efendim.'
    if '401' in metin or '403' in metin or 'API key' in metin:
        return 'Gemini API anahtarı geçersiz görünüyor, .env dosyasını kontrol edin.'
    return 'Yapay zekaya şu an ulaşamıyorum efendim.'


class Beyin:
    def __init__(self) -> None:
        tercih = os.getenv('YZ_SAGLAYICI', 'otomatik').lower()
        sira = {'ollama': [_Ollama], 'gemini': [_Gemini]}.get(tercih, [_Ollama, _Gemini])
        self.arkalar = []
        for sinif in sira:
            try:
                self.arkalar.append(sinif())
            except Exception as e:
                print(f'{sinif.ad} kullanılamıyor: {e}')
        self.aktif = bool(self.arkalar)
        self.araclar = sistem.ARACLAR + [self._ekrani_gor_araci()]

    @property
    def ad(self) -> str:
        return ' + '.join(f'{a.ad} ({a.model})' for a in self.arkalar) or 'yok'

    def _ekrani_gor_araci(self):
        beyin = self

        def ekrani_gor(soru: str) -> str:
            """Ekranın görüntüsünü alır ve ekranda ne olduğunu görerek soruyu yanıtlar.

            Args:
                soru: Ekranla ilgili soru, ör. 'Ekranda ne var?' veya 'Bu hata mesajı ne diyor?'
            """
            return beyin.ekrani_gor(soru)
        return ekrani_gor

    def sor(self, metin: str) -> str:
        if not self.aktif:
            return 'Yapay zeka kapalı efendim. Ollama kurun ya da .env dosyasına GEMINI_API_KEY yazın.'
        hata = None
        for arka in self.arkalar:  # first one that answers wins (Ollama, then Gemini)
            try:
                return _seslendirilebilir(arka.sor(metin, self.araclar))
            except Exception as e:
                print(f'{arka.ad} hatası: {e}')
                hata = e
        return _hata_metni(hata)

    def ekrani_gor(self, soru: str) -> str:
        for arka in self.arkalar:
            try:
                return arka.gor(soru)
            except Exception as e:
                print(f'{arka.ad} ekranı göremedi: {e}')
        return 'Ekranı göremedim efendim (modelin görme desteği olmayabilir).'
