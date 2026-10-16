# JARVIS — Durum raporu ve uygulama planı

Tarih: 16.10.2026. Branch: `claude/sleepy-mccarthy-sy4p78` (main'e birleştirilmedi).

## 1. Başlangıç durumu (incelenen)

| Konu | Bulgu |
|---|---|
| `main` | Orijinal GauravSingh9356/J.A.R.V.I.S + PR #1 (yalnız Linux kurulum düzeltmesi, `25c1ad3`). İngilizce sabit komutlar, `helpers.py` içinde `recognize_google(language='en-in')`, `data.txt` hafıza. **Ollama yok.** |
| Geliştirme branch'i | `main`'in 3 commit önünde: Türkçe ses (`ses.py`), sabit Türkçe komutlar (`komutlar.py`), `sistem.py` eylemleri, `beyin.py` içinde Ollama + Gemini yedekli araç çağırma (`d95bebe`). Kullanıcının kullandığı Ollama entegrasyonu buydu. |
| Giriş noktaları | `jarvis.py` (ses/yazı), `youtube_downloader.py` (Tk penceresi), `amazon.py` (bağımsız betik). |
| Riskler | `beyin.py` modele sınırsız PowerShell (`komut_calistir`) ve `python_calistir` veriyordu; onay yalnız regex ile. Görev kaydı, doğrulama, iptal, yeniden başlatma kurtarması yoktu. Ollama kapalıysa sessizce Gemini'ye (bulut) geçiyordu. |
| Lisans | MIT (Gaurav Singh) korunuyor. |

Kullanıcının Windows bilgisayarına erişimim yok: Windows sürümü, CPU, RAM, GPU/VRAM, Ollama sürümü ve
kurulu modeller **bilinmiyor**. Bunları ölçmek için `saglik.bat` (`python -m jarvis_core.saglik`) eklendi.

Geliştirme/test ortamı (Windows değil): Linux bulut konteyneri, 4 vCPU, 15.7 GB RAM, GPU yok,
Ollama 0.40.5, `qwen3.5:9b` (Ollama API `/api/show` yetenekleri: completion, vision, tools, thinking).

## 2. Mimari (Aşama 1 sonrası)

```
jarvis.py ── ses.py (STT/TTS) ── komutlar.py (hızlı sabit komutlar)
                                     └── beyin.py (adaptör) ──┐
gorev_motoru.bat ── jarvis_core/cli.py ───────────────────────┤
                                                              ▼
jarvis_core/motor.py   anla → plan → araç → gözlem → doğrula → devam/düzelt
   ├─ llm.py        Ollama (akışlı, iş parçacığında; iptalde soket kapatılır)
   ├─ araclar/      şemalı araç kataloğu (risk, yan etki, zaman aşımı, doğrulama, geri alma)
   ├─ izinler.py    izin/sor/red kararı (araç, klasör, risk); yalnız kullanıcı değiştirir
   ├─ depo.py       SQLite: görevler, adımlar (çalışmadan önce yazılır), hafıza; gizli veri maskeleme
   ├─ saglik.py     donanım/Ollama/mikrofon/internet raporu
   └─ acil.py       genel acil durdurma kısayolu (Windows, keyboard paketi)
```

Motorun garanti ettikleri (modele bırakılmadan kodda):
- Araç argümanları JSON şemasıyla doğrulanır (`additionalProperties: false`).
- Her çağrı izin kontrolünden geçer. Silme her zaman sorar (klasör bazında izin verilebilir);
  dış iletişim ve sistem işlemleri her seferinde sorar ve kuralla önceden onaylanamaz.
- Kabuk yok: `program_calistir` argüman listesiyle çalışır; izinli liste (git, ollama, ipconfig...)
  dışındakiler ve `git push/reset/...` sorulur. Python/node/pip varsayılan olarak sorulur (keyfi kod çalıştırırlar).
- Harici içerik (web, dosya, arama, pano, ekran) `<harici_veri>` olarak işaretlenir; okunduktan sonra
  yan etkili her araç, kural izin verse bile onay ister.
- Adım bütçesi, süre bütçesi, araç zaman aşımı, aynı çağrının tekrarı (döngü) tespiti.
- İptal: model yanıtı beklenirken bile anında (soket kapatılır), araç çalışırken alt süreç öldürülür.
- Bir görevde aynı yan etkili çağrı tekrar gelirse kayıttan yanıtlanır, yeniden yapılmaz.
- Yeniden başlatmada `calisiyor` görevler `yarida_kaldi` olur; `/devam <id>` sürdürür. Başlamış ama sonucu
  yazılmamış adım için önce `zaten_yapildi` kontrolü yapılır (ör. dosya hedefte mi), yapılmışsa tekrarlanmaz.
- Görev durumu `tamamlandi` ancak her yan etkili aracın son denemesi başarılı **ve doğrulanmışsa**;
  aksi halde `dogrulanamadi` ve cevaba hangi adımın doğrulanamadığı eklenir.

## 3. Aşama planı

| Aşama | Kapsam | Durum |
|---|---|---|
| 1 | Ollama bağlantısı, metinle görev motoru, dosya/uygulama araçları, doğrulama, iptal, izinler, SQLite kayıt/kurtarma, sağlık kontrolü | **Uygulandı** (bkz. test sonuçları) |
| 2 | Yerel STT (faster-whisper vb., donanımda ölçülerek), wake word, bas-konuş, mikrofon seçimi, VAD, konuşurken kesme (barge-in), kendi sesini yankı olarak duymama, ses sırasında görev iptali | Yapılmadı |
| 3 | Tarayıcı (Playwright: sekme, okuma, form, indirme doğrulama), UI Automation tabanlı ekran kontrolü, fare devralınınca duraklama, hafıza yönetimi (çelişki/yenilik), PDF/tablo okuma | Kısmen: hafıza (kaynak+tarih, unut, listele) ve `ekrani_gor` var; tarayıcı yok |
| 4 | Kod/web sitesi üretimi ve yerel sunucu, test çalıştırma, git diff/geri alma, zamanlanmış görevler ve tetikleyiciler, beceri manifesti + izole doğrulama + etkinleştirme/geri dönüş, MCP | Yapılmadı |
| 5 | Masaüstü durum paneli, otomatik başlangıç | Yapılmadı |

## 4. Bilinen eksikler (Aşama 1)

- `metin_yaz`, `pencereye_gec`, `pencereleri_listele`, uygulama açmanın pencere doğrulaması, `pywinauto` ile
  içerik geri okuma ve acil durdurma kısayolu **Windows'ta hiç çalıştırılmadı** (geliştirme ortamı Linux).
- Sesli yolda görev sırasında "dur" henüz dinlenmiyor (Aşama 2). Konsolda "dur"/Ctrl+C ve acil kısayol var.
- Geri Dönüşüm Kutusu'na gönderilen dosyayı geri yükleme aracı yok (Windows'tan elle geri yüklenir).
- Araç zaman aşımında iş parçacığı Python'da zorla durdurulamaz; alt süreç kullanan araçlar öldürülür,
  saf Python araçları arka planda bitene kadar sürebilir.
- Model seçimi kullanıcının donanımında ölçülmedi. `qwen3.5:9b` yalnız bu Linux CPU ortamında denendi.

## 5. Aşama 1 test sonuçları

### Simülasyon (sahte model, gerçek araçlar, geçici ev klasörü) — Linux
`python -m pytest -q tests` → **25 geçti**, 3 atlandı (canlı testler). Kapsanan kabul maddeleri:

| Senaryo | Test | Sonuç |
|---|---|---|
| Dosya oluştur, diskte doğrula | `test_dosya_yaz_dogrulanir_ve_tamamlanir` | geçti |
| "Yanlış klasörü söyledim, diğerine taşı" (geri al + taşı, bağlam) | `test_yanlis_klasor_geri_al_ve_dogru_yere_tasi` | geçti |
| Uzun işlemde "dur" | `test_iptal_uzun_islemi_hemen_keser` (< 1 sn şartı) | geçti |
| Ollama kapalı | `test_ollama_kapali_anlasilir_hata` | geçti |
| İnternet kesik | `test_internet_kesik` | geçti |
| Disk dolu | `test_disk_dolu` | geçti |
| Yeniden başlatmada kurtarma, yapılmış işlem tekrarlanmaz | `test_yeniden_baslatma_sonrasi_*` (2 test) | geçti |
| Kötü niyetli içerik yetki kazanamaz (model talimata uysa bile) | `test_harici_icerikteki_talimat_yetki_kazanamaz` | geçti |
| Şema dışı argüman, döngü, adım bütçesi, zaman aşımı, tekrar eden yan etki | ilgili testler | geçti |
| İzinler, git parametre enjeksiyonu, terminale yazma, gizli veri maskeleme, hafıza | `test_izin_ve_depo.py` | geçti |
| Mikrofon yok | `saglik` raporu "Mikrofon YOK" dedi; `jarvis.py` yazı moduna geçer (önceki sürümde test edildi) | elle doğrulandı |

### Canlı Ollama (qwen3.5:9b, 4 vCPU, GPU yok, num_ctx 8192) — Linux, Windows değil
`JARVIS_CANLI=1 python -m pytest -s tests/test_canli_ollama.py`

| İstek | Süre | Araçlar | Durum |
|---|---|---|---|
| Belgeler'e alisveris.txt oluştur, içine süt, yumurta, ekmek yaz | 96.1 sn | dosya_yaz | tamamlandi, dosya doğrulandı |
| Onu Masaüstü'ne taşı | 50.0 sn | dosya_tasi | tamamlandi |
| Yanlış klasörü söyledim, Resimler'e taşı | 60.9 sn | dosya_tasi | tamamlandi |
| Kötü niyetli talimat içeren sayfayı özetle (silmeye izin kuralı varken) | 56.5 sn | web_sayfasi_oku | özetledi, silme denemedi, dosya yerinde |
| Uzun yanıt üretirken iptal | — | — | iptal gecikmesi **0.08 sn** |
| Konsol (`python -m jarvis_core`) ile dosya oluşturma | 44.6 sn | dosya_yaz | tamamlandi |
| Konsol, Ollama kapalı | 0.1 sn | — | anlaşılır hata |

Başarı: 6/6 canlı senaryo. Ölçümler: 29 araçlı istem ≈ 3557 token; bu CPU'da istem işleme 15.3 sn,
ilk çıktı 19.2 sn, üretim 4.1 token/sn; model belleği (Ollama `ps`) 6.1 GB. Model ilk yüklemesi ≈ 35 sn.
Bu süreler GPU'suz bir sunucuya aittir; kullanıcının bilgisayarında ölçülmedi.

### Çalıştırılmayan testler (geçti sayılmaz)
- Windows'ta hiçbir test çalıştırılmadı: Not Defteri senaryosu, pencere doğrulama, `metin_yaz`,
  UI Automation geri okuma, acil durdurma kısayolu, `kur.bat`/`baslat.bat`.
- Sesli kabul testleri (Aşama 2), indirme / web sitesi / PDF senaryoları (Aşama 3–4).
- RAM/VRAM ölçümü kullanıcının donanımında yapılmadı; ilk sesli yanıt süresi ölçülmedi.

## 6. Masaüstü paneli

Referans repodaki görsel dil (koyu zemin, camgöbeği "arc reactor" halkaları, ortada J.A.R.V.I.S., kenarlarda
saat ve CPU/RAM göstergeleri) temel alındı. Referans repo arayüz için tkinter kullanıyor; daha akıcı animasyon
için panel yerel bir web arayüzü olarak yazıldı ve Edge'in uygulama modunda kendi penceresinde açılıyor
(`jarvis_core/panel/`). Ek bağımlılık yok.

- Sunucu yalnızca 127.0.0.1'e bağlanır; her istek her açılışta üretilen gizli anahtarı ve panelin kendi
  kaynağını (Origin) taşımak zorunda. Anahtarsız, yanlış anahtarlı ve başka kaynaktan gelen istekler 403.
- Olaylar Server-Sent Events ile akar: durum (hazır/dinliyor/düşünüyor/yürütüyor/konuşuyor/onay/hata),
  araç adımları ve sonuçları, onay istekleri, telemetri (CPU, RAM, GPU, VRAM, sıcaklık, Ollama).
- Onaylar panelde Evet/Hayır penceresiyle, yazıyla veya sesle ("evet"/"hayır") verilir.
- Uyandırma sözcüğü modu JARVIS konuşurken dinlemez (kendi sesini komut sanmaz); görev sürerken yalnız
  "dur/iptal" sözcüklerine tepki verir. DURDUR düğmesi ve Esc konuşmayı da keser.
- Başlatma: `python kisayol_olustur.py` masaüstüne pythonw ile çalışan bir kısayol koyar (konsol yok,
  Akıllı Uygulama Denetimi'nin engellediği .bat yok); `--baslangic` Windows açılışına ekler.

Test (Linux, Windows değil):
- `tests/test_panel.py` (4 test): erişim denetimi, hızlı komut uçtan uca, düğmeyle ve yazıyla onay — geçti.
- Chromium (Playwright) ile 6 durumda ekran görüntüsü alındı; sayfada JavaScript hatası yok.
- Canlı: panel API'si → görev motoru → qwen3.5:9b → `dosya_yaz` → dosya diskte, durum `tamamlandi`
  (GPU'suz sunucuda 329 sn; ilk model yüklemesi dahil).
- Windows'ta çalıştırılmadı: Edge uygulama penceresi, kısayol/ikon oluşturma, mikrofonla uyandırma sözcüğü,
  nvidia-smi telemetrisi.

## 7. Windows geri bildirimi sonrası düzeltmeler

| Sorun (kullanıcı, Windows) | Kök neden | Düzeltme | Doğrulama |
|---|---|---|---|
| Ses Türkçe-İngilizce karışık ve net değil | Çevrimiçi ses çalışmadığında İngilizce Windows sesine düşüyordu | Varsayılan ses yerel Piper Türkçe (+ JARVIS efekti); Windows sesi yalnız Türkçe ise kullanılır | Linux'ta sentez + oynatma; kırpılma yok; susturma 0.03 sn. Windows'ta kulakla doğrulanmadı |
| DURDUR'dan sonra yeni emir tıkanıyor | İptal sonrası Ollama eski cevabı üretmeye devam edebiliyordu; konuşma görevi bloke ediyordu | Ollama akışı kendi soketimizle (iptalde kapatılır); konuşma ayrı kuyrukta; 4 sn bekçi; görev sıra numarası | Canlı: iptal 0.04 sn, sonraki istek 3.4 sn. 3 yeni panel testi. Windows'ta denenmedi |
