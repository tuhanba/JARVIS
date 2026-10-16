# JARVIS — Yetenek matrisi

Durumlar: `planned` · `implemented` (kod var, otomatik test yok) · `unit-tested` · `integration-tested`
(gerçek araçlar + sahte model, ya da gerçek tarayıcı) · `windows-verified` (kullanıcının Windows
bilgisayarında denendi) · `blocked` (dış bağımlılık/donanım eksik).

Bir modülün bulunması özelliğin çalıştığını kanıtlamaz. Geliştirme ortamı Linux konteyneridir. GitHub
Actions `windows-latest` üzerinde başsız test paketi koşuyor: bu **Windows uyumluluk** kanıtıdır, kullanıcının
masaüstünde doğrulama değildir; bu yüzden hiçbir satır `windows-verified` değildir. `ci-windows` notu, ilgili
testin hosted Windows runner'da geçtiğini gösterir.

Son güncelleme: Aşama A + B + C (kısmi) + J (hatırlatıcı) (bkz. `IMPLEMENTATION_STATUS.md`).

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
| Sahip olunan süreç ağacını sonlandırma — Windows Job Object | integration-tested (ci-windows) | `test_iptal_sahip_olunan_surec_agacini_kapatir` GitHub Actions windows-latest'te geçti |
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

| Yetenek | Durum | Kanıt / not |
|---|---|---|
| Ollama tek sağlayıcı, bulut yedeği yok | integration-tested | `test_ollama_kapali_anlasilir_hata`; canlı testler gerçek Ollama 0.40.5 ile koşuldu (CPU) |
| `/api/show` ile yetenek, nicemleme, bağlam uzunluğu | implemented | `llm.hazirla`, `saglik.model_ayrintisi` |
| İlgili araç seçimi + `arac_katalogu` ile kontrollü genişleme | integration-tested | `tests/test_asama_b.py` seçim testleri; canlı karşılaştırma `IMPLEMENTATION_STATUS.md` |
| Kod profili (`OLLAMA_MODEL_KOD`) çağrı yoluna bağlı | integration-tested | `test_kod_profili_cagri_yoluna_bagli` |
| Gerçek token akışı panele (düşünme gizli) | integration-tested | `test_metin_akisi_bildirilir`, `test_dusunce_etiketleri_akista_gizlenir`; panelde gözle doğrulama yok |
| `think=False`'u dinlemeyen modellerde düşünmenin cevaba sızmaması | integration-tested + canlı | qwen3:4b canlı yoklamada sızma görüldü; `test_think_false_dinlemeyen_model_ayri_alanda_dusunur` |
| Tek model bellekte (süreç geneli) | unit-tested | `test_tek_model_kurali_surec_genelinde` |
| Ölçümler: ilk parça, yükleme, prompt/üretim hızı, sıcak/soğuk | integration-tested | `test_olcumler_kaydedilir`; `/olcumler` |
| Bağlam bütçesi (eski çıktı kısaltma, amaç notu) | integration-tested | `test_baglam_butcesi_eski_ciktilari_kisaltir_kaydi_bozmaz` |
| Referans belleği ("onu taşı") | integration-tested | `test_referanslar_promptta`; canlı `takip` görevi 1.7B ile kaldı |
| Konuşup iş yapmayan modelde sahte başarı yok | integration-tested + canlı | qwen3:1.7b canlı testinde bulundu; `test_arac_cagirmadan_yaptim_demek_basari_sayilmaz` |
| Çok amaçlı cümlede fast-path yerine model | unit-tested | `test_cok_amacli_cumle_modele_gider` |
| Türkçe görev değerlendirmesi (bağımsız son durum, sahte başarı sayacı) | integration-tested | `python -m jarvis_core.degerlendirme`; sonuçlar `IMPLEMENTATION_STATUS.md` |
| Plan/replan (çok adımlı görevlerde açık plan) | planned | Şu an model adım adım ilerliyor; sınırlı düzeltme turu var |
| Konuşma özetleme | planned | Bağlam bütçesi kısaltma yapıyor, özet üretmiyor |

## Ses (Aşama C)

| Yetenek | Durum | Kanıt / not |
|---|---|---|
| Yerel varsayılan, çevrimiçi yalnız `JARVIS_SES_CEVRIMICI=1` (F08) | unit-tested | `test_cevrimici_ses_yalniz_acik_izinle` |
| Yerel STT faster-whisper (çok dilli, `tr`, `.en` reddi) | integration-tested | Piper→whisper çevrimdışı tur (`test_cevrimdisi_tts_stt_turu`, modeller varken) |
| Yerel Türkçe TTS (Piper tr_TR-dfki-medium) | integration-tested | Sentez + tanıma turu; hoparlörden dinlenmedi |
| İngilizce sesi Türkçe diye sunmama | unit-tested | `test_turkce_olmayan_ses_turkce_diye_sunulmaz` |
| Türkçe seslendirme metni (sayı, saat, %, birim, yol, URL) | unit-tested | `test_seslendirme_metni`, `test_sayi_oku` |
| VAD + konuşma sonu, ön kayıt, sınırlı tampon | unit-tested | sentetik ses testleri; gerçek mikrofon yok |
| Ses durumu panelde ve sağlık raporunda | implemented | `ses_durumu` olayı; tarayıcıda gözle bakılmadı |
| Gerçek mikrofonla Türkçe tanıma doğruluğu | blocked | Mikrofon yok; sentetik seste "Chrome'u aç" yanlış tanındı |
| Wake word (yerel), barge-in, yankı, cihaz değişimi (F09, T14–T16) | planned / blocked | Donanım gerekiyor; mevcut uyandırma hâlâ STT sonrası regex |
| Tek mikrofon akışı (sürekli capture) | planned | `ses.dinle` hâlâ istek başına mikrofon açıyor |

## Diğer aşamalar

| Alan | Durum | Not |
|---|---|---|
| Kalıcı hatırlatıcı: UTC kayıt, yerel gösterim, kaçırılan politika, çift teslim yok, tekrar (F14, T34) | integration-tested | `tests/test_asama_c.py` hatırlatma testleri |
| Rutinler, dosya/uygulama tetikleyicileri, proaktif mod (Aşama J geri kalanı) | planned | |
| Ekran: UIA + OCR + vision döngüsü (Aşama D) | planned | `ekrani_gor`, pencere araçları mevcut (önceki sürüm) |
| Güvenli web okuma: bayt sınırı, içerik türü, yönlendirme başına denetim, yerel ağ izni (T27) | integration-tested | `tests/test_ag.py` (sonsuz yanıt, 169.254.169.254'e yönlendirme, ikili içerik) |
| Playwright tarayıcı servisi (sekme, DOM, form), indirme yöneticisi (Aşama E, F15) | planned | |
| Belge okuma PDF/DOCX/XLSX/CSV, konum + sha256, boyut/satır/çıktı sınırı, bozuk belge (Aşama F) | integration-tested | `tests/test_belgeler.py`; taranmış PDF "OCR gerekli" der |
| OCR, belge üretimi (XLSX/DOCX/PDF rapor), artifact registry | planned | |
| Hafıza: konu bazlı sürüm (supersede), FTS5 ile ilgili kayıt, unutma indeksten de silinir, harici içerikten gelen iddia "doğrulanmamış" (T28) | integration-tested | `tests/test_hafiza.py` |
| Hafıza ekranı, embedding ile hibrit arama, proje/oturum katmanları | planned | |
| Kod/site üretimi, sandbox (Aşama H) | planned | |
| Beceriler, MCP, entegrasyonlar (Aşama I) | planned | |
| Kurulum sihirbazı, pyproject, CI, paketleme (Aşama L, F21) | planned | README eski upstream metni temizlendi, `THIRD_PARTY_NOTICES.md` eklendi |
