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

## Aşama A — Çekirdek doğruluk ve güvenilirlik: **tamamlandı (Linux'ta)**

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

## Sonraki aşamalar

Sıra şartname §21'e göre: B (Ollama zekâ/performans) → C (ses) → D/E/F → G → H → I/J → K/L.
Ayrıntılı bir sonraki adım: kök dizindeki `NEXT_STEPS.md`.
