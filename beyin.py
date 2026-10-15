"""Gemini-backed brain: answers free-form questions and can drive the
computer through the functions in sistem.py (automatic function calling)."""
import os

import sistem

SISTEM_TALIMATI = """Sen JARVIS'sin: kullanıcının kişisel, Türkçe konuşan sesli asistanı.
Kullanıcıya "efendim" diye hitap et. Yanıtların sesli okunacak: kısa (1-3 cümle), düz metin,
markdown, liste, emoji veya kod bloğu kullanma.
Kullanıcının bilgisayarında (çoğunlukla Windows) tam yetkin var. Bir iş istendiğinde
konuşmak yerine araçları kullanarak işi yap; uygun araç yoksa komut_calistir ile PowerShell
komutu çalıştır. İşi yaptıktan sonra sonucu tek cümleyle söyle.
Tehlikeli işlemlerde (silme, kapatma, sistem ayarı) araçlar kullanıcıdan zaten onay ister;
sen ayrıca sorma. Emin olmadığın bir dosya yolunu önce dosyalari_listele veya dosya_ara ile bul."""


class Beyin:
    def __init__(self) -> None:
        anahtar = os.getenv('GEMINI_API_KEY', '').strip()
        self.aktif = bool(anahtar)
        if not self.aktif:
            return
        from google import genai
        from google.genai import types

        self._istemci = genai.Client(api_key=anahtar)
        self._sohbet = self._istemci.chats.create(
            model=os.getenv('GEMINI_MODEL', 'gemini-flash-latest'),
            config=types.GenerateContentConfig(
                system_instruction=SISTEM_TALIMATI,
                tools=sistem.ARACLAR,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(maximum_remote_calls=8),
            ),
        )

    def sor(self, metin: str) -> str:
        if not self.aktif:
            return 'Yapay zeka kapalı. Kullanmak için .env dosyasına GEMINI_API_KEY yazın.'
        try:
            cevap = self._sohbet.send_message(metin)
        except Exception as e:
            hata = str(e)
            if '429' in hata or 'RESOURCE_EXHAUSTED' in hata:
                return 'Gemini ücretsiz kullanım limiti doldu efendim, biraz sonra tekrar deneyin.'
            if '403' in hata or '401' in hata or 'API key' in hata:
                return 'Gemini API anahtarı geçersiz görünüyor, .env dosyasını kontrol edin.'
            print(f'Gemini hatası: {hata}')
            return 'Yapay zekaya şu an ulaşamıyorum.'
        return (cevap.text or 'Tamamdır efendim.').replace('*', '').strip()
