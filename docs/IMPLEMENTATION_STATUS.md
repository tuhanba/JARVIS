# JARVIS — Uygulama durumu (kaldığım yer)

Şartname: [JARVIS_MASTER_PLAN.md](JARVIS_MASTER_PLAN.md). Yetenek bazında durum: [FEATURE_MATRIX.md](FEATURE_MATRIX.md).
Geliştirme branch'i: `claude/eloquent-wright-zsg2o5`. Başlangıç: `main` = `1721259` (incelenen SHA ile aynı;
fark yoktu, çalışma ağacı temizdi, `AGENTS.md`/`CLAUDE.md` yok).

## Ortam

Linux bulut konteyneri, Python 3.13, GPU yok, Ollama yok (canlı Ollama testleri `skipped`), mikrofon/hoparlör
yok. Windows masaüstü, UIA, Job Object, SAPI ve gerçek ses bu ortamda **çalıştırılamadı**. Panel için
Playwright + Chromium ile gerçek tarayıcı denemesi yapıldı (onay kartı, reload, 1366/390 px).

## Başlangıç ölçümü

`python -m pytest -q tests`: **30 passed, 3 skipped** (şartnamedeki sonuçla aynı). Not: `ses.py` üst düzeyde
`speech_recognition` import ettiği için bu paket kurulu değilken 24 test import hatasıyla düşüyordu; artık
tembel import ediliyor.

## Aşama A — Çekirdek doğruluk ve güvenilirlik: **tamamlandı (Linux + Windows CI)**

Regresyon testleri önce yazıldı ve eski kodda çalıştırıldı: `tests/test_asama_a.py` → **57 failed, 6 passed**
(davranış hataları doğrudan gözlendi: "şunu yaz: bilgisayarı kapat" kapatma fonksiyonunu çağırdı, `*` izin
kuralı `powershell`'i serbest bıraktı, ikinci başarılı taşıma ilk hatayı örttü, şema hatası `tamamlandi`
verdi, `token: abc` içeren kontrol noktası geçersiz JSON oldu, yeni görev eski görevin iptalini sildi,
kopyalama iptalde yarım dosya bıraktı). Düzeltmeden sonra: **101 passed, 3 skipped** (3 ardışık koşu, ~10 sn).

| Bulgu | Değişiklik | Dosyalar |
|---|---|---|
| F01 | Ortak Türkçe evet/hayır/belirsiz ayrıştırıcı (olumsuzluk ve tereddüt önce). Panel onayı kimlik + süreyle tek eyleme bağlı; belirsiz cevapta bekler; eski/yanlış kimlik 409. Ses ve CLI aynı ayrıştırıcıyı kullanır. | `jarvis_core/niyet.py`, `panel/sunucu.py`, `ses.py`, `cli.py` |
| F02 | Her çağrı bir amaca (araç + hedefi belirleyen argümanların özeti) bağlı; başarısız amaç ancak aynı amaç başarılınca çözülür. Okuma hataları da amaç. Cevap, model başarı iddia etse bile gerçek sonuca göre düzeltilir. | `jarvis_core/yurutucu.py`, `motor.py` |
| F03 | Bilinmeyen araç / şema hatası `gecersiz` durumlu kayıtlı adım + çözülmemiş amaç; aynı aracın sonraki geçerli başarısı telafi eder. | `yurutucu.py` |
| F04 | Görev kontrol noktası (`gorevler.kontrol_noktasi`): amaçlar, harici içerik işareti ve kaynakları, döngü sayaçları, harcanan süre. Bitmiş görev yeniden açılmaz; eski kayıtlar için güvenlik durumu adımlardan yeniden kurulur. Görev sahibi (pid) + atomik sahiplenme. | `motor.py`, `depo.py` |
| F05 | Maskeleme JSON'dan önce nesne üzerinde (`gizlilik.maskele_nesne`), sözlük anahtarları dahil; çağrı/amaç anahtarları hash. Görev, adım, hata, geri alma verisi ve panel olayları aynı katman. Migration v2 öncesi `jarvis.db.v1.yedek`; parse edilemeyen eski kayıtlar `karantina` tablosuna. | `gizlilik.py`, `depo.py`, `panel/sunucu.py` |
| F06 | Hızlı komut yönlendiricisi yalnız `Niyet` üretir; eylemler `Motor.hizli_calistir` → ortak yürütücü (politika, onay, kayıt, zaman aşımı, iptal). Eski `sistem.py` işlevleri modele kapalı araçlar olarak sarıldı. Saat gibi işler model beklemez. | `komutlar.py`, `araclar/hizli.py`, `motor.py`, `beyin.py`, `panel/sunucu.py` |
| F07 | Görev başına `IptalJetonu` (çağrı başına çocuk jeton); global durdurma tüm aktif görevlere ulaşır, yeni görev hiçbir jetonu temizlemez. Araçların başlattığı süreçler sahiplenilir: POSIX'te süreç grubu, Windows'ta kill-on-close Job Object; iptal/zaman aşımında ağaç kapatılır. Durmayan araç "sonucu belirsiz" olarak raporlanır. Kopyalama parça parça, iptalde yarım çıktı silinir. | `araclar/temel.py`, `yurutucu.py`, `araclar/dosyalar.py` |
| F12 | `program_calistir` çıkış kodu 0 → `succeeded`, hiçbir zaman `verified` değil; salt okunur çağrılar (git status, ipconfig...) okuma sayılır. | `araclar/program.py`, `izinler.py` |
| F13 | Atomik yazma; yedekler `veri/yedek/<tarih>_<uuid>/` + `manifest.json`; geri alma, dosya JARVIS'ten sonra değiştiyse reddeder (hash). | `araclar/dosyalar.py` |
| F19 (kısmi) | Durdurma tam kelimeyle ("durum ne" durdurmaz); dikte her komuttan önce; döviz yalnız kur sorusunda; "son işlemi geri al" ≠ Ctrl+Z. | `niyet.py`, `komutlar.py` |
| F20 | Karar sırası: değişmez sınırlar → kullanıcı yasakları → kullanıcı izinleri (`*` yalnız dosya riskleri) → varsayılanlar. SISTEM riski varsayılan sorar, araç adıyla izin verilebilir. `JARVIS_TAM_YETKI=1` görünür, silinebilir kurallara taşınır. Kural dosyası değişince yeniden okunur. | `izinler.py`, `sistem.py` |
| F17 (kısmi) | Olay kimliği, Last-Event-ID replay, sınırlı kuyruk, `/api/durum` bekleyen onay; sıkı tip doğrulama, 413, Host kontrolü. | `panel/sunucu.py`, `arayuz.html` |
| F18 (kısmi) | Onay kartı dar ekranda taşmıyor (390 px'de EVET erişilebilir). Panelin geri kalanı hâlâ responsive değil. | `arayuz.html` |
| F21 (kısmi) | README: çevrimiçi ses sınırı açık, yanıltıcı eski upstream özellik listesi kaldırıldı, atıf korundu; `THIRD_PARTY_NOTICES.md`. | `README.md` |

### Davranış değişiklikleri (kullanıcının fark edeceği)

- Hızlı komutlar artık görev geçmişinde görünür; sonucu doğrulanamayan işler (ör. ses tuşu) panelde
  "DOĞRULANAMADI" rozetiyle görünür, söylenen cümle "ses açma tuşuna basıldı" gibi yapılanı anlatır.
- Kapatma/yeniden başlatma/uyku onayı artık hızlı komutlarda da merkezi politikadan gelir. `JARVIS_TAM_YETKI=1`
  olan kurulumda ilk açılışta bu dört işlem için izin kuralları oluşur (`/izinler`).
- Terminal penceresi öndeyken dikte yazılmaz.
- Bir görev başarısız amaçla bitince cevap "Görev tam olarak yapılamadı. Yapılamayan: ..." biçimindedir.
- `/devam` yalnız `yarida_kaldi` görevleri sürdürür.

### Kalan bağımlılıklar / açık riskler

- Windows Job Object kodu ve UI ile ilgili hızlı araçlar Windows'ta denenmedi (`windows-verified` yok).
- Credential store (secret referansı) yok; gizli değerler yalnız maskeleniyor.
- Model metnindeki başarı iddiası tespiti sezgisel (Türkçe 1. tekil geçmiş zaman eki); yanlış pozitif yalnız
  cevabı daha temkinli yapar.
- Okuma amaçları araç adına göre gruplanır (aynı aracın sonraki başarılı okuması önceki okuma hatasını
  çözer); bu, keşif aramalarını cezalandırmamak için bilinçli bir uzlaşmadır.

## Aşama B — Ollama zekâ katmanı: **çekirdek tamam**

Canlı ortam: bu konteynere Ollama 0.40.5 (CPU, 4 çekirdek, GPU yok) + `qwen3:1.7b`, `qwen3:4b` kuruldu.
Canlı testler gerçek hataları buldu ve düzeltildi:

1. **Konuşup iş yapmama = sahte başarı.** qwen3:1.7b "Belgeler'e alisveris.txt oluştur" isteğine hiç araç
   çağırmadan "Tamamdır efendim." dedi; motor `tamamlandi` verdi, dosya yoktu. Artık eylem isteyen istekte yan
   etkili hiçbir adım yoksa bir düzeltme turu verilir, yine yoksa `dogrulanamadi` + "hiçbir işlem yapılmadı".
2. **Düşünce sızıntısı.** Bu qwen3:4b sürümü `think=False`'u yok sayıp akıl yürütmesini cevap metnine yazdı
   ("Okay, so I need to figure out...") → panele ve sese gidecekti. Model başına bir kerelik yoklama + `<think>`
   ayıklayıcı eklendi.
3. **İki model aynı anda bellekte.** `OLLAMA_TEK_MODEL` istemci örneğine bağlıydı; süreç geneline taşındı.

Ayrıca: araç seçimi + `arac_katalogu`, kod profili, gerçek token akışı, tur ölçümleri (`/olcumler`), bağlam
bütçesi, referans belleği, çok amaçlı cümle yönlendirmesi, `python -m jarvis_core.degerlendirme`.

Ölçüm notu: qwen3:4b bu CPU'da tur başına 1000+ düşünme token'ı × ~4 tok/sn ≈ 5 dk/tur üretti; değerlendirme
pratik olmadığı için **ölçülmedi**. Gerçek karşılaştırma kullanıcının GPU'lu makinesinde yapılmalı (NEXT_STEPS).

### Türkçe görev değerlendirmesi (qwen3:1.7b, CPU, 11 görev × 2 tekrar)

`python -m jarvis_core.degerlendirme --model qwen3:1.7b --tekrar 2`. Başarı = bağımsız son durum kontrolü
(diskteki dosya, cevap içeriği). Bu donanım ve model kullanıcının hedef donanımı değildir.

| Koşu | Başarı | Sahte başarı | Yanlış sohbet | Ort. görev | İlk parça p50 | Üretim |
|---|---|---|---|---|---|---|
| Araç seçimi kapalı (tüm şemalar), düzeltmelerden önce | 17/22 (%77) | 2* | — | 40.4 sn | 6.3 sn | 7.3 tok/sn |
| Araç seçimi açık, düzeltmelerden önce | 17/22 (%77) | 2* | — | 24.0 sn | 4.8 sn | 10.1 tok/sn |
| Araç seçimi açık + benchmark düzeltmeleri | **18/22 (%82)** | **1** | 2 | **21.6 sn** | 5.4 sn | 10.6 tok/sn |

\* İlk iki koşuda "sahte başarı"nın tamamı sohbet sorusundaki bilgi hatasıydı ("başkent İstanbul"); ölçüt sonra
ayrıldı. Kapalı koşu sırasında başka testler de CPU kullandı; süre farkının bir kısmı buna bağlı olabilir.

Kalan hatalar: `takip` 1/2 (model ikinci istekte yanlış yol verdi), `ara_bul` 1/2 sahte başarı (model dosyayı
buldu ama adını söylemedi — sohbet metninin eksikliğini motor bilemez), `sohbet` 0/2 (bu konteynerde web araması
sonuç vermedi; model aramaya gitti; görev dürüstçe `dogrulanamadi`), `red_durust` bir koşuda `dongu` ile durdu
(yine de silmedi). Hedef (%90 doğrulanmış başarı, 0 sahte başarı) **bu küçük modelle karşılanmadı**; kullanıcının
GPU'lu makinesinde 9B sınıfı modelle ölçülmeli.

## Aşama C — Yerel Türkçe ses: **yazılım tarafı tamam, donanım doğrulaması blocked**

- Varsayılan yerel: faster-whisper (`small`, `tr`, alan sözlüğü) + Piper `tr_TR-dfki-medium`. Çevrimiçi Google/Edge
  yalnız `JARVIS_SES_CEVRIMICI=1`. Türkçe ses yoksa İngilizce ses kullanılmaz, yazı gösterilir.
- **Davranış değişikliği:** eski kurulumlar Google/Edge ile konuşuyordu. Güncellemeden sonra
  `python -m jarvis_core.audio.kur` (kur.bat 4. adım) çalıştırılmadan ses tanıma/çıkışı yoktur; panel ve
  `saglik` bunu ve çözümünü yazar. Eski çevrimiçi davranış için `.env`: `JARVIS_SES_CEVRIMICI=1`.
- Çevrimdışı tur (Piper → whisper small, CPU): "Belgeler klasörüne alışveriş listesi oluştur." birebir; "Saat
  14:30 da toplantı var." doğru; "İndirilenlerdeki faturayı Belgelere taşı." → "belirlere"; "Chrome'u aç." →
  yanlış. Tanıma 1.3–2.9 sn/cümle (CPU, başka iş yükü varken). Sentetik ses gerçek kullanıcı sesi değildir.
- Blocked (mikrofon/hoparlör yok): gerçek mikrofonda doğruluk, wake word, barge-in, yankı, cihaz değişimi
  (T14–T16), sürekli tek mikrofon akışı.

## Aşama E/F/G çekirdekleri

- E: güvenli web okuma (`ag.py`): 2 MB sınır, metin türleri, yönlendirme başına denetim, yerel ağ yalnız
  `/ag-izin` ile. Playwright tarayıcı servisi ve indirme yöneticisi **yapılmadı**.
- F: `belge_oku` (PDF/DOCX/XLSX/CSV/TXT, konum + sha256, sınırlar, bozuk/taranmış belge). OCR ve belge üretimi
  **yapılmadı**.
- G: hafıza v4 (konu bazlı sürüm, FTS5 getirme, unutma indeksten silinir, harici içerikten gelen iddia
  "doğrulanmamış"). Hafıza ekranı ve embedding **yapılmadı**.

## Aşama J — hatırlatıcı (F14): **tamam**

SQLite + UTC, Europe/Istanbul gösterim, kaçırılan politika, iki kopyada çift teslim yok, günlük/haftalık tekrar.
Windows CI, Windows'ta saat dilimi veritabanı olmadığını gösterdi → `tzdata` + sabit ofset yedeği.

## CI

`.github/workflows/test.yml`: ubuntu-latest + windows-latest, başsız test paketi. Windows runner'da Stage A
süreç ağacı testi (Job Object) geçti. Bu, masaüstü/mikrofon doğrulaması değildir.

## Sonraki aşamalar

Sıra şartname §21'e göre: kalan B (plan/replan, özet) → C donanım doğrulaması → D (UIA/OCR ekran) → E
(Playwright, indirme) → F (OCR, rapor üretimi, artifact) → G (hafıza ekranı) → H (kod/site, sandbox) → I
(beceri, MCP) → J (rutinler, tetikleyiciler) → K (React panel, ekranlar) → L (pyproject, kurulum sihirbazı,
paketleme). Ayrıntılı bir sonraki adım: kök dizindeki `NEXT_STEPS.md`.
