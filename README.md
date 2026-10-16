# JARVIS — Türkçe sesli asistan

Türkçe dinler, Türkçe konuşur ve Windows bilgisayarınızda gerçek işler yapar. Yapay zekası
**Ollama** ile sizin bilgisayarınızda çalışır; düşünme/görev kısmı için buluta veri gönderilmez.
Kamera kullanılmaz.

**Çevrimiçi kalan kısımlar (dürüst sınır):** ses tanıma şu an Google'ın çevrimiçi servisini
(`recognize_google`), doğal Türkçe ses ise Microsoft Edge çevrimiçi sesini (`edge-tts`) kullanır;
yani söyledikleriniz ve JARVIS'in cevapları bu servislere gider. İnternet yoksa ses çıkışı yerel
`pyttsx3` sesine düşer. Hava, haber, döviz, web araması ve sayfa okuma doğal olarak internete çıkar.
Tamamen yerel ses hattı (yerel STT/TTS, uyandırma sözcüğü) planlanmıştır; durum için
[docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md).

İstekler bir **görev motorundan** geçer: model bir plan yapar, araçları çağırır, her adımın
sonucunu gözlemler ve doğrular. "Tamamlandı" yalnızca sonuç gerçekten görüldüğünde söylenir
(dosya diskte, uygulama süreç/pencere olarak açık). Her adım `veri/jarvis.db` içine kaydedilir;
yarıda kalan görev yeniden başlatmada sürdürülebilir ve yapılmış işlemler tekrarlanmaz.
Hızlı sesli komutlar ("Chrome'u aç", "sesi aç") modeli beklemez ama aynı yürütücüden, aynı izin,
onay ve kayıt kurallarıyla geçer; panelde görev olarak görünür.

Geliştirme planı ve durum: [docs/JARVIS_MASTER_PLAN.md](docs/JARVIS_MASTER_PLAN.md),
[docs/FEATURE_MATRIX.md](docs/FEATURE_MATRIX.md), [docs/IMPLEMENTATION_STATUS.md](docs/IMPLEMENTATION_STATUS.md).

## Kurulum (Windows)

JARVIS klasöründe adres çubuğuna `cmd` yazıp Enter'a basın ve sırayla çalıştırın:

```
python -m pip install -r requirements.txt
copy .env.example .env
winget install -e --id Ollama.Ollama
ollama pull qwen3.5:9b
python kisayol_olustur.py
```

Son komut masaüstüne **JARVIS** simgesi koyar. Çift tıklayınca JARVIS paneli kendi penceresinde açılır
(Edge uygulama modu, konsol penceresi yok). Windows açılışında başlasın isterseniz:
`python kisayol_olustur.py --baslangic` (kaldırmak için `--kaldir`).

Diğer giriş noktaları: `python -m jarvis_core.saglik` (donanım/Ollama raporu),
`python -m jarvis_core` (konsol), `python jarvis.py` (yalnız ses).

## Panel

- Ortadaki HUD durumu renkle gösterir: camgöbeği hazır, yeşil dinliyor, amber düşünüyor/çalışıyor, kırmızı hata.
- Sol: işlemci, bellek, GPU, VRAM, sıcaklık; Ollama ve model durumu; hızlı komutlar.
- Sağ: aktif görev ve görev akışı (her araç adımı, sonucu ve doğrulama durumu).
- Alt: komut satırı, mikrofon (bas-konuş, Ctrl+Boşluk), uyandırma sözcüğü ("Jarvis ..."), sesli yanıt, **DURDUR** (Esc).
- Onay gereken işlemlerde Evet/Hayır penceresi açılır (E/H tuşları).
- Panel yalnızca bu bilgisayardan (127.0.0.1) ve her açılışta değişen gizli bir anahtarla erişilebilir.

## Güvenlik ve izinler

- Okuma serbest. Belgeler, Masaüstü, İndirilenler, Resimler, Müzik, Videolar içine yazma serbest;
  başka yerlere yazma onay ister.
- Silme (Geri Dönüşüm Kutusu'na) her zaman onay ister; isterseniz klasör bazında izin verebilirsiniz
  (`/izin-ver cop_kutusuna_gonder İndirilenler`). Dışarıya mesaj her seferinde sorulur; kapatma/yeniden
  başlatma gibi sistem işlemleri varsayılan olarak sorulur, yalnız o aracı adıyla izinli yaparsanız sormaz
  (`/izin-ver bilgisayari_kapat`).
- Değişmez sınırlar: kabuk (PowerShell/cmd...) hiç çalışmaz, terminal penceresine yazma her seferinde sorar,
  `*` kuralı yalnız dosya okuma/yazma/silmeyi kapsar. Programlar argüman listesiyle çalışır; izinli liste
  dışındakiler sorulur. Bir izni panelde/konsolda kaldırdığınızda çalışan görevin bir sonraki adımında geçerli olur.
- Onay cevabında olumsuzluk ve tereddüt önce gelir: "yapma", "onaylamıyorum", "olur mu bilmiyorum" evet
  sayılmaz; belirsiz cevapta JARVIS işlem yapmaz, yeniden sorar. Paneldeki onay kartı tek bir işleme bağlıdır.
- Web sayfası, dosya veya arama sonucundaki talimatlar komut sayılmaz; bunlar okunduktan sonra yapılan
  her değişiklik ayrıca onay ister.
- Parola/token benzeri metinler kayıtlarda, görev geçmişinde ve panel olaylarında maskelenir.
- Acil durdurma: **Ctrl+Alt+End** (görev çalışırken "dur" da olur). Durdurma, görevin başlattığı
  programları ve onların alt süreçlerini de kapatır; ilgisiz programlarınıza dokunmaz.
- Üzerine yazılan dosyanın yedeği `veri/yedek/` altına benzersiz adla alınır; "son işlemi geri al",
  dosyayı JARVIS'ten sonra siz değiştirdiyseniz üzerine yazmaz.

## Örnek komutlar

| Ne | Örnek |
|---|---|
| Saat / tarih | "saat kaç", "bugün günlerden ne" |
| Hava, haber, döviz | "Ankara'da hava nasıl", "haberleri oku", "dolar kaç" |
| Uygulama | "Chrome'u aç", "not defterini aç", "Spotify'ı kapat" |
| Site / arama | "instagram aç", "Google'da python dersleri ara", "YouTube'da Tarkan çal" |
| Ses / ekran | "sesi aç", "sesi kıs", "parlaklığı 40 yap", "ekran görüntüsü al" |
| Not / hatırlatma | "not al süt al", "notlarımı oku", "10 dakika sonra çayı hatırlat" |
| Dosyalar | "masaüstü klasörünü aç", "indirilenler neler var" |
| Klavye | "şunu yaz Merhaba", "kopyala", "yapıştır", "pencere değiştir" |
| Bilgisayar | "bilgisayarı kilitle", "bilgisayarı kapat", "yeniden başlat", "uyku modu" |
| Yapay zeka | "masaüstümdeki pdf dosyalarını bul", "dün Fenerbahçe maçı kaç bitti", "ekranda ne var", |
| | "indirilenlerdeki resimleri Resimler klasörüne taşı", "benim doğum günüm 3 Mayıs, unutma" |
| Çıkış | "görüşürüz" |

Silme, kapatma gibi işlemlerden önce JARVIS "evet" onayı ister.
Eski `JARVIS_TAM_YETKI=1` ayarı artık her kontrolü kaldırmaz: ilk açılışta yalnız kapatma, yeniden başlatma,
uyku ve notları silme için görünür izin kurallarına çevrilir (`/izinler` ile görüp `/izin-sil` ile
kaldırabilirsiniz). Dikte ("şunu yaz: ...") hiçbir zaman komut olarak çalıştırılmaz.

---

## Kaynak ve lisans

Bu proje [GauravSingh9356/J.A.R.V.I.S](https://github.com/GauravSingh9356/J.A.R.V.I.S) (MIT, © 2020
GauravSingh9356) üzerine kurulmuştur; özgün lisans `LICENSE` dosyasında korunur. Özgün projenin İngilizce
özellik listesi (e-posta gönderme, İngilizce komutlar, PyAudio 3.8 wheel kurulumu vb.) bu sürümün
yeteneklerini yansıtmadığı için buradan kaldırıldı; geçmiş için özgün depoya bakın. Üçüncü taraf
bileşenler ve referans projeler: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
