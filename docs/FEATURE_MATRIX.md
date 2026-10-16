# JARVIS — Yetenek matrisi

Durumlar: `planned` · `implemented` (kod var, otomatik test yok) · `unit-tested` · `integration-tested`
(gerçek araçlar + sahte model, ya da gerçek tarayıcı) · `windows-verified` (kullanıcının Windows
bilgisayarında denendi) · `blocked` (dış bağımlılık/donanım eksik).

Bir modülün bulunması özelliğin çalıştığını kanıtlamaz. Bu ortam Linux konteyneridir: **hiçbir satır
`windows-verified` değildir**; Windows'a özgü kod (Job Object, UI Automation, SAPI, known folders)
burada çalıştırılamadı.

Son güncelleme: Aşama A sonu (bkz. `IMPLEMENTATION_STATUS.md`).

## Çekirdek (Aşama A)

| Yetenek | Durum | Kanıt / not |
|---|---|---|
| Onay ayrıştırıcı: evet / hayır / belirsiz, olumsuzluk ve tereddüt önce (F01, T01) | integration-tested | `tests/test_asama_a.py` onay testleri, `tests/test_panel.py::test_yapma_onay_sayilmaz`, `ses.onayla`, CLI |
| Onay tek eyleme bağlı (id + süre), eski/çift cevap başka işlemi onaylayamaz | integration-tested | `test_eski_onay_kimligi_yeni_islemi_onaylayamaz`; gerçek Chromium'da kart + EVET (scratchpad e2e) |
| Amaç bazlı görev sonucu; ikinci başarı ilk hatayı örtmez (F02, T02) | integration-tested | `test_ikinci_basari_ilk_hatayi_ortmez`, `test_ayni_amac_telafi_edilirse_tamamlanir` |
| Şema dışı / uydurma araç çağrısı kayıtlı başarısız adım (F03, T03) | integration-tested | `test_sema_hatasi_kayitli_basarisiz_adimdir`, `test_uydurma_arac_sahte_tamamlandi_uretmez` |
| Model "yaptım" deyip amaç başarısızsa cevap gerçeğe göre düzeltilir | unit-tested | `yurutucu.sonuc_ozeti`; F02 testi cevabı kontrol eder |
| Kontrol noktası: amaçlar, harici içerik işareti, kaynaklar, bütçe (F04, T04) | integration-tested | `test_devamda_harici_icerik_isareti_korunur` |
| Bitmiş görev `devam` ile yeniden açılmaz | integration-tested | `test_bitmis_gorev_devamla_tamamlandiya_donmez` |
| Aynı görevi iki JARVIS örneği devralamaz (sahip + atomik sahiplenme) | unit-tested | `test_iki_kopya_ayni_gorevi_devralamaz`; canlı iki süreç testi yapılmadı |
| Nesne düzeyinde gizli bilgi maskeleme, geçerli JSON (F05, T05) | integration-tested | `test_gizli_bilgili_kontrol_noktasi_gecerli_json`, `test_gizli_anahtar_adli_alan_maskelenir` |
| Bozuk eski kayıtların karantinası + migration öncesi DB yedeği | integration-tested | `test_bozuk_eski_kayit_karantinaya_alinir` |
| OS credential store ile secret referansı | planned | Şu an gizli değerler hiç saklanmıyor (maskeleniyor); geri çağrılabilir secret yok |
| Hızlı komutlar ortak yürütücüden geçer (F06, T06) | integration-tested | `test_hizli_komut_ortak_yurutucuden_gecer`, `test_hizli_komut_politikaya_tabidir`, panel `test_hizli_komut_gorev_kaydi_olusturur` |
| Görev başına iptal jetonu; yeni görev eski iptali silmez (F07) | integration-tested | `test_yeni_gorev_eski_gorevin_iptalini_silmez` |
| Sahip olunan süreç ağacını sonlandırma — POSIX süreç grubu (T07) | integration-tested | `test_iptal_sahip_olunan_surec_agacini_kapatir` (Linux) |
| Sahip olunan süreç ağacını sonlandırma — Windows Job Object | implemented | `temel._windows_is_nesnesi`; Windows'ta çalıştırılmadı |
| İptal edilebilir parça parça kopyalama, yarım dosya kalmaz (T08) | integration-tested | `test_kopyalama_iptalinde_yarim_dosya_kalmaz` |
| Durmayan araç için "sonucu belirsiz" (unknown_effect), "durdu" denmez | implemented | `Yurutucu._zamanli_calistir`; özel test yok |
| Monotonic görev/araç süresi, toplu çağrıda her çağrı öncesi bütçe | integration-tested | `test_adim_butcesi`, `test_zaman_asimi` |
| Süreç başarısı ≠ hedef doğrulaması (F12) | unit-tested | `test_program_cikis_kodu_hedef_dogrulamasi_degildir` |
| Atomik yazma (staging + fsync + replace) (F13) | unit-tested | `test_yazma_atomiktir_gecici_dosya_kalmaz` |
| Benzersiz yedek kimliği + manifest; aynı saniye iki yedek (T09) | unit-tested | `test_ayni_saniyede_iki_uzerine_yazma_iki_ayri_yedek` |
| Kullanıcı sonradan değiştirdiyse kör geri alma yok | unit-tested | `test_kullanici_degistirdiyse_kor_geri_alma_yok` |
| Değişmez sınırlar kullanıcı kuralından önce; `*` kabuk/terminali kapsamaz (F20) | unit-tested | `test_joker_kural_kabuk_ve_terminal_sinirini_gecemez` |
| `JARVIS_TAM_YETKI` görünür kurallara taşınır | unit-tested | `test_tam_yetki_ortam_degiskeni_gorunur_kurala_tasinir` |
| Görev ortasında geri alınan yetki sonraki adımda geçerli (T42) | unit-tested | `test_kullanici_yetkiyi_gorev_ortasinda_geri_alirsa` |
| Meşru tekrar (ses artır ×2) engellenmez, aynı dosya yazımı tekrarlanmaz (T10) | unit-tested | `tekrarlanabilir` alanı; `test_ayni_islem_tekrarlanmaz`. Yeniden başlatma + retry senaryosu kısmi |
| "Dolar geçen dosya" döviz değil, "durum ne" durdurma değil (F19, T11) | integration-tested | `test_dolar_gecen_dosya_doviz_degildir`, `test_durum_sorusu_gorevi_durdurmaz` |
| Dikte güç komutuna dönüşmez (T12) | unit-tested | `test_dikte_guc_komutuna_donusmez` |
| "geri al" (Ctrl+Z) ile "son işlemi geri al" ayrımı | implemented | `komutlar._yerel_komut`; özel test yok |

## Panel / API

| Yetenek | Durum | Kanıt / not |
|---|---|---|
| Token + Origin + Host (DNS rebinding) kontrolü | integration-tested | `test_erisim_denetimi`, `test_yabanci_host_ve_buyuk_istek_reddedilir` |
| Sıkı tip doğrulama (`"false"` ≠ True), 413 boyut sınırı (T37) | integration-tested | `test_metin_false_onay_degildir` |
| Bekleyen onay `/api/durum` + reload'da geri gelir (T36) | integration-tested | panel testi + gerçek Chromium reload (1366 ve 390 px) |
| Olay kimliği, Last-Event-ID replay, yinelenen olay filtresi, sınırlı kuyruk (F17) | integration-tested | `test_yeniden_yuklemede_bekleyen_onay_geri_gelir` |
| Görev detay / devam / duraklat API | planned | CLI'da `/gorev`, `/devam` var; panelde yok |
| Onay kartı dar ekranda kullanılabilir | integration-tested | 390 px Chromium ekran görüntüsü |
| Panelin geri kalanı responsive / reduced-motion / %200 zoom (F18, T40) | planned | 390 px'de üç kolon taşıyor (gözlendi) |
| React/TypeScript yeni arayüz, ekranlar (Görevler, Hafıza, Yetkiler...) | planned | Aşama K |

## Ollama ve zekâ (Aşama B)

| Yetenek | Durum | Not |
|---|---|---|
| Ollama tek sağlayıcı, bulut yedeği yok | integration-tested | `test_ollama_kapali_anlasilir_hata`; canlı testler Ollama yoksa atlanır |
| `/api/show` ile yetenek kontrolü (tools) | implemented | `llm.hazirla` |
| Fast-path (modelsiz) basit komutlar | integration-tested | panel testleri |
| Kod/görsel/genel model profili çağrı yoluna bağlı (F10) | planned | `OLLAMA_MODEL_KOD` henüz kullanılmıyor |
| İlgili araç seçimi (az şema) | planned | Her istekte modele açık tüm araçlar gidiyor |
| Gerçek token akışı panele/TTS'e (F11) | planned | |
| Konuşma referans belleği ("onu taşı") | planned | Son işlemler prompt'ta; yapılandırılmış referans yok |
| Ölçümler (TTFT, token hızı, araç süresi) | planned | |

## Ses (Aşama C)

| Yetenek | Durum | Not |
|---|---|---|
| Çevrimiçi STT (Google) + Edge TTS + pyttsx3 yedek | implemented | Önceki sürümden; README'de çevrimiçi olduğu açıkça yazıyor (F08) |
| Yerel STT (faster-whisper), yerel TTS, VAD, wake word, barge-in (F09) | planned | Donanım/mikrofon gerektirir; Windows doğrulaması gerekli |
| Ses paketleri tembel import (headless çalışır) | unit-tested | `ses.py`; testler `speech_recognition` olmadan da ses modülünü yükler |

## Diğer aşamalar

| Alan | Durum | Not |
|---|---|---|
| Kalıcı zamanlayıcı / hatırlatıcı (F14, Aşama J) | planned | `hatirlatici_kur` hâlâ `threading.Timer` (süreç kapanınca kaybolur); yürütücüye bağlı |
| Ekran: UIA + OCR + vision döngüsü (Aşama D) | planned | `ekrani_gor`, pencere araçları mevcut (önceki sürüm) |
| Playwright tarayıcı servisi, indirme yöneticisi (Aşama E, F15) | planned | |
| Belge okuma PDF/DOCX/XLSX, artifact registry (Aşama F, F16) | planned | |
| Kaynaklı hafıza, supersede, FTS (Aşama G, F16) | planned | Hafıza kayıtları kaynak + tarih taşıyor (önceki sürüm) |
| Kod/site üretimi, sandbox (Aşama H) | planned | |
| Beceriler, MCP, entegrasyonlar (Aşama I) | planned | |
| Kurulum sihirbazı, pyproject, CI, paketleme (Aşama L, F21) | planned | README eski upstream metni temizlendi, `THIRD_PARTY_NOTICES.md` eklendi |
