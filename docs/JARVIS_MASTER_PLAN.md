# JARVIS — Kod incelemesi ve Claude Code uygulama şartnamesi

> Bu dosya kullanıcının verdiği şartnamenin değiştirilmemiş kopyasıdır (16.10.2026). Bölüm 1–4'teki
> bulgular `1721259` commit'ine aittir; düzeltilenlerin durumu `docs/IMPLEMENTATION_STATUS.md` ve
> `docs/FEATURE_MATRIX.md` içindedir.

Hazırlanma: 16 Ekim 2026 • Kullanıcı: Batuhan • Hedef: Windows 11, Türkçe, Ollama merkezli kişisel bilgisayar asistanı.

Bu dosyayı Claude Code'a bütün olarak ver. Bölüm 1–4 mevcut durum kanıtıdır; bölüm 5 ve sonrası uygulama talimatıdır. İncelenen sürümden sonra yapılan değişiklikleri önce kontrol et; eski bulguları körlemesine yeniden uygulama.

## 1. İncelemenin kapsamı ve sonucu

Ana depo: https://github.com/tuhanba/JARVIS

İncelenen `main` commit: `17212597c0c22618b0c8d558acaf2fc88a881d7a` — PR #3 birleşmesi.

README ile yetinilmedi: görev motoru, Ollama istemcisi, veri deposu, izin sistemi, bütün araç modülleri, ses hattı, hızlı komut yönlendirmesi, sistem işlevleri, panel sunucusu/HTML kaynağı, testler ve mevcut durum dokümanı incelendi. Kod değiştirilmedi, GitHub'a yazılmadı.

Bu repo basit bir sesli komut demosundan ileride: 29 kayıtlı araç, SQLite görev/adım kayıtları, bazı işlemlerde doğrulama ve geri alma, Ollama tool calling, yerel panel, sistem telemetrisi ve kurulum kısayolu mevcut. Bunları koruyup sağlamlaştırmak gerekir.

En büyük eksiklik, özellik sayısından önce **bütün giriş yollarının aynı yürütme, kayıt, iptal ve doğrulama kurallarına bağlanmaması**. Yeni araçlar bu ayrılığı büyütmemeli.

Doğrulama ortamı Linux/Python 3.12 idi. Gerekli test bağımlılıkları sağlandıktan sonra `python -m pytest -q tests --tb=short`: **30 passed, 3 skipped**, 2 bağımlılık deprecation uyarısı. Atlananlar canlı Ollama testleri. Windows masaüstü, mikrofon, hoparlör, gerçek model, ekran kartı ve yeni üretilecek özellikler test edilmedi. Panelin HTML/CSS/JS kaynağı incelendi; bu incelemede görsel tarayıcı QA yapılmadı. Mevcut rapordaki eski canlı test sonuçları bu çalışmanın ölçümü değildir.

## 2. Kodda bulunan sorunlar

Öncelikler: P0 = yetki/yanlış işlem/yanlış başarı; P1 = güvenilirlik ve temel kabiliyet; P2 = ürün geliştirme. Satırlar yalnız yukarıdaki commit için geçerlidir.

| ID | Öncelik | Kanıt ve bulgu | Gereken düzeltme |
|---|---|---|---|
| F01 | P0 | `jarvis_core/panel/sunucu.py:143–152`: onay için substring `yap`, `onay`, `olur` aranıyor. Gerçek `Panel.komut('yapma')` kontrolünde onay **True** oldu. `ses.py:120–129` da olumlu eşleşmeyi olumsuzdan önce yapıyor. | Ortak Türkçe evet/hayır/belirsiz ayrıştırıcı; olumsuzluk önceliği; eyleme bağlı approval ID; belirsiz cevapta yürütmeme. |
| F02 | P0 | `motor.py:182–189, 249–250`: son durum araç adıyla tutuluyor. Aynı görevde ilk `dosya_tasi` başarısız, ikinci farklı dosya taşıması başarılı olduğunda görev **tamamlandi**, adımlar ise `hata,tamam` oldu. | Her amaç/eylem ayrı ID; başarısız amaç ancak aynı amaç gerçekten telafi edilince çözülmüş olsun. |
| F03 | P0 | `motor.py:203–212`: bilinmeyen araç/şema hatası erken dönüyor, final sonucu engellemiyor. Geçersiz ek parametreli `dosya_yaz` çağrısı sonrasında görev **tamamlandi** oldu. | Doğrulama hatasını da yapılandırılmış başarısız adım olarak kaydet; amaç yerine gelmeden başarı verme. |
| F04 | P0 | `motor.py:135–138`: devamda `kirli=False`, `son={}` sıfırlanıyor. `dogrulanamadi` görevini `devam` ile yeniden açıp yalnız final yanıt alınca **tamamlandi** oldu. Harici içerik işareti de yeniden kurulmadığı için devamda politika kaybı riski var. | Checkpoint içine amaçlar, doğrulamalar, harici veri kökeni, izin kapsamı ve çağrı kimliklerini koy; terminal görevi sebepsiz yeniden açma. |
| F05 | P0 | `depo.py:75–79`: JSON serileştikten sonra regex maskeleme yapılıyor. `şifre: abc` ve `token: abc` içeren basit mesajlarda `json.loads` başarısız; normal mesajda başarılı. | Nesne üzerinde özyinelemeli maskele, sonra JSON üret. Kurtarma için gerekli gizli değerleri silinmiş metinden çalıştırma; secret referansı kullan. Eski bozuk kayıtları karantinaya al. |
| F06 | P0 | `panel/sunucu.py:168–184` ve `komutlar.py`: hızlı komutlar doğrudan `sistem.py` çağırıyor, metin dönerse `tamamlandi` yazıyor. Görev motorunun kayıt/izin/doğrulama yolu uygulanmıyor. Bazı eski işlemlerin kendi onayı var, fakat politika ortak değil. | Deterministik hızlı router yalnız intent üretsin; eylemler ortak executor üzerinden geçsin. Saat gibi hızlı işler model beklemesin. |
| F07 | P0 | `motor.py:275–301`: zaman aşımı thread'i durdurmuyor; iptalde 2 sn bekleyip çıkıyor. `Baglam.surec` yalnız doğrudan çocuğu öldürüyor. Dosya kopyalama gibi çağrılar iptal kontrolü yapmadan çalışabiliyor. | Görev başına iptal tokenı; kooperatif chunk işlemleri; izole worker; Windows Job Object/process-tree sonlandırma. UI'da durdu demeden fiili sonlanmayı doğrula. Job Object tek başına dosya/ağ sandbox'ı değildir. |
| F08 | P1 | `ses.py`: `recognize_google` ve `edge_tts` var. README'deki genel “buluta veri gönderilmez” iddiası ses için doğru değil. | Varsayılan yerel STT/TTS; çevrimiçi ses yalnız kullanıcı seçerse; gerçek veri akışını UI ve README'de açık göster. |
| F09 | P1 | Panel wake word tespiti, konuşma STT'ye gittikten sonra regex ile yapılıyor. `_surekli_dongu` TTS sırasında dinlemeyi kapatıyor. | Gerçek yerel wake word, tek mikrofon sahibi, VAD, yankı azaltma ve barge-in. |
| F10 | P1 | `motor.py` bütün araç şemalarını her isteğe gönderiyor; oturum yalnız son 4 istek/cevap çifti. `OLLAMA_MODEL_KOD` ayarı var fakat ana motor `sohbet` çağrısında kod iş türü seçmiyor. `ekrani_gor` ayrı istemci kullanıyor. | Araç seçimi, yapılandırılmış konuşma bağlamı, kod/görsel/genel model yönlendirmesi, ortak VRAM/model yaşam döngüsü. |
| F11 | P1 | Ağdan token akışı alınsa da `llm.py` içeriği biriktirip tur sonunda döndürüyor. Paneldeki yazı efekti gerçek token akışı değil. | Kullanıcıya görünen metin delta olayları; araç argümanlarını tamamlanmadan yürütmeme; cümle bazlı TTS. |
| F12 | P1 | `program_calistir` çıkış kodu 0 olduğunda `dogrulandi=True` veriyor. Bu, kullanıcının hedefinin gerçekleştiği anlamına gelmez. | Süreç başarısı ile görev sonucu doğrulamasını ayır; dosya/URL/test/uygulama postcondition kullan. |
| F13 | P1 | `dosyalar.py:_yedekle` saniye + dosya adı kullanıyor; aynı saniyede aynı adlı dosyaların yedeği çakışabilir. Yazma atomik değil. Bazı kurtarma kontrolleri yalnız varlık/yokluk bakıyor. | Benzersiz backup ID, atomik yazma, önce/sonra hash, hedef manifesti, çakışma kontrolü ve güvenilir undo. |
| F14 | P1 | `sistem.py:hatirlatici_kur` yalnız `threading.Timer`; süreç kapanınca kayboluyor. | SQLite tabanlı kalıcı scheduler; saat dilimi, kaçan tetikleme ve tekrar çalıştırma politikası. |
| F15 | P1 | `bilgi.py:web_sayfasi_oku` HTML metni okuyor; tarayıcı sekmesi/form/indirme yönetimi yok. `youtube_downloader.py` ayrı Tk akışı; hızlı komut yalnız pencere açıyor. | Playwright oturum servisi; kayıtlı araçlar üzerinden indirme yönetimi ve tamamlanma doğrulaması. |
| F16 | P1 | Hafıza düz metin kayıtlarından oluşuyor; son 30 kayıt prompt'a ekleniyor. `yerine_gecen` sütunu var ama çelişki çözümü uygulanmıyor. PDF/DOCX/XLSX içerik okuyucu yok; `dosya_oku` UTF-8 metinle sınırlı. | Kaynaklı hafıza retrieval, çelişki/sürüm yönetimi, belge işleme hattı ve alıntı konumları. |
| F17 | P1 | Panel geçmiş listesi sınırlı; `/api/durum` onayı her zaman `None` döndürüyor; SSE olay ID/replay yok; kuyruk sınırsız. Yarım kalanlar gösteriliyor fakat panel devam endpoint'i yok. | Yeniden bağlanmada snapshot + event cursor, kalıcı aktif onay, görev detay/continue/pause API, bounded queue. |
| F18 | P2 | `arayuz.html` tek dosyada CSS/JS; 330px + merkez + 400px üç kolon, global `overflow:hidden`; responsive media query ve reduced-motion desteği bulunmadı. | Modüler responsive arayüz; küçük ekranda erişilebilir gezinme; azaltılmış animasyon; gerçek görev/çıktı ekranları. |
| F19 | P1 | `komutlar.py` geniş substring eşleştirmeleri çok amaçlı cümleyi erken yakalayabilir; “geri al” doğrudan Ctrl+Z. Panelde durdurma için substring kullanımı “durum” gibi metinleri kesme riski taşıyor. | Token/intent tabanlı negatiflik ve çoklu niyet; “görevi geri al” ile aktif uygulamada undo ayrımı. |
| F20 | P1 | `izinler.py` kullanıcı izin kuralını bazı program kontrollerinden önce değerlendiriyor; wildcard kural terminal kısıtlarını geçebilir. Eski `JARVIS_TAM_YETKI` yalnız eski sistem yolunu etkiliyor. | Değişmez sınırlar ile kullanıcı yetki kapsamını açık ayır; tüm yollar tek policy engine kullansın; tam yetki ayarı tutarlı ve görünür olsun. |
| F21 | P2 | README altında upstream'in eski İngilizce özellikleri/rozetleri var. `docs/DURUM_VE_PLAN.md` başında branch'in birleşmediği, tabloda panelin yapılmadığı yazıyor; ileride panel anlatılıyor. CI workflow, paketleme projesi ve sürüm kilidi bu ağaçta yok. | Güncel yetenek matrisi, tek kurulum yolu, bağımlılık kilidi, Windows/Linux CI, release ve temiz dokümantasyon. Orijinal atıfları koru. |

Ek kontrol sonuçları, ürün kodunu değiştirmeden geçici dizinlerde ve sahte LLM ile üretildi. Bunlar Windows E2E testi değildir. Bulguların tekrar üretimleri uygulama sırasında gerçek regresyon testlerine dönüştürülmelidir.

## 3. Referans projeler: alınacak kabiliyetler

Referanslar kurularak uçtan uca çalıştırılmadı. Aşağıdaki değerlendirme README, mimari belgeler ve seçilmiş gerçek kaynak dosyalarının incelemesidir; tüm ürünlerin kalite garantisi değildir.

| Proje ve incelenen commit | Kaynakta görülen örnekler | Bizim projeye aktarılacak yaklaşım |
|---|---|---|
| [Dodaios / eski PersonalJarvis](https://github.com/Dodaios/Dodaios), `ae629b4b13c1b625b311eb905488cf9599fbe236` | `jarvis/core/protocols.py`, `jarvis/missions/isolation/job_object.py`, `jarvis/core/self_mod/writer.py`, `docs/LLM-CONTEXT.md` | Değiştirilebilir sağlayıcı sözleşmeleri, görev/worker ayrımı, process-tree yönetimi, atomik ayar değişimi ve rollback; görev paneli, eklenti, rutin ve yerel wiki fikirleri. Bulut sağlayıcı bağımlılıklarını taşımayacağız. |
| [Axx33284/jarvis](https://github.com/Axx33284/jarvis), `6b56a4e3fa87fa783fd15cdc1bdf540719f7aa8d` | `jarvis/audio/voice.py`, `core/machine_map.py`, `core/skills.py`, `tools/hearing.py` | Tek mikrofon akışı, cihaz seçimi, bilgisayar haritası, sistem sesini isteğe bağlı duyma, tekrar kullanılabilir beceri fikri. Kodda ses yankı iptalinin olmadığı açıkça belirtiliyor; bunu hazır çözüm sayma. Regex taraması + Python çalıştırmayı güçlü sandbox sanma. |
| [AgenticSeek](https://github.com/Fosowl/agenticSeek), `b46bcca482218643236999221720586e7f410e04` | `sources/agents/planner_agent.py`, `sources/browser.py`, `config.ini` | Görevi web/kod/dosya alt işlerine bölme, sonuçlara göre planı güncelleme, tarayıcı durumunu yönetme. Bizde Playwright ile özgün uygulama; ekran/pencere tek sahipli. Ses README'de geliştirme aşamasında. |
| [isair/jarvis](https://github.com/isair/jarvis), `8907131170bdda561cde9edc7593ad068144d3aa` | `src/jarvis/tools/selection.py`, `tools/external/mcp_runtime.py`, `listening/echo_detection.py`, memory ve eval dizinleri | İlgili araçları seçme, MCP oturumunu çağrılar arasında yaşatma, aynı sunucuya seri çağrı, Unicode-aware ses işlemesi, hafıza/kurulum/dikte ekranları ve davranış değerlendirmeleri. Türkçeye özgü yeniden uygulama gerekir. |

Kod aktarım kararı: kullanıcı deposunda MIT; Dodaios'ta Apache-2.0; AgenticSeek'te GPL-3.0; isair'de özel non-commercial lisans metni görüldü. Axx ağacında LICENSE bulunmadı. Bu nedenle “özellikleri al” talimatı bütün kaynakları kopyalayıp MIT diye yayımlamak değildir. Varsayılan yaklaşım fikirleri bağımsız uygulamak; kopyalanacak herhangi bir bileşen için lisans/atıf/uyumluluk incelemesi ve `THIRD_PARTY_NOTICES` kaydı yapmak. Model ağırlıklarının lisanslarını da ayrı kaydet. Yıldız sayısını kalite ölçümü yerine kullanma.

## 4. Özellik açığı haritası

| Alan | Şu an | Hedef |
|---|---|---|
| Türkçe sohbet ve Ollama | Var | Araç seçimi, daha iyi bağlam, gerçek streaming, ölçülmüş model yönlendirme |
| Ses | Çevrimiçi STT/TTS ağırlıklı | Offline STT/TTS, VAD, gerçek wake word, barge-in, cihaz yönetimi |
| Görev motoru | Var, sağlamlaştırılmalı | Amaç bazlı plan, kanıtlı başarı, kuyruk, durable recovery, gerçek iptal |
| Dosyalar | Temel CRUD/undo | Atomik toplu işlem, belge işleme, arşiv, indeks, çatışma yönetimi |
| Ekran | Görsel soru, pencere/yazı araçları | UIA + OCR + vision, gözlem-eylem-doğrulama döngüsü, kullanıcı devralma |
| Tarayıcı | Site açma/HTML okuma | Sekme, DOM, form, oturum, indirme/yükleme, işlem doğrulama |
| Video/medya | Ayrı indirici pencere | Sesle yönetilen kuyruk, ilerleme, iptal, altyazı/transkript/dönüştürme |
| Kod ve site üretimi | Genel dosya/program araçları | Repo/worktree, patch/test, preview, build, sürüm, deploy adaptörü |
| Hafıza | Düz kayıtlar | Kaynaklı kişisel/proje/oturum hafızası, retrieval, düzenleme ve unutma |
| Öğrenme | Temel hafıza | Başarılı işten beceri taslağı, test, sürümleme, geri dönüş |
| Otomasyon | Geçici timer | Takvim + dosya/uygulama tetikleyicileri, kalıcı rutinler |
| Entegrasyon | MCP yok | MCP ve servis adaptörleri, bağlantı/izin/secret yönetimi |
| Arayüz | Tek HUD ekranı | Komuta merkezi, görev geçmişi, dosya/çıktı, hafıza, rutin, beceri ve ayarlar |
| Dağıtım | Python ve kısayol | Setup wizard, temiz Windows kurulum, tray, sürüm yükseltme/rollback |

---

## 5. CLAUDE CODE'A UYGULAMA TALİMATI

Sen bu deponun kıdemli mimarı ve uygulayıcı mühendisisin. Kullanıcının amacı, kendi Windows bilgisayarında Türkçe sesle yönetilen, Ollama ile düşünen, gerçek görevleri bitiren ve yeni yeteneklerle genişleyen JARVIS'i geliştirmektir. Bu dokümanın kalanını uygulama şartnamesi kabul et. Yalnız plan, örnek kod veya mock ekran üretip bitirme; çalışan özellikleri aşamalar halinde teslim et.

### 5.1 Sabit ürün kararları

1. Ana LLM sağlayıcısı **Ollama**. Çalışmak için OpenAI/Claude/Gemini API anahtarı zorunlu olmasın. Sessiz cloud fallback ekleme. Claude Code bu projeyi geliştiren araçtır; ürünün çalışma zamanı zorunlu bağımlılığı değildir.
2. Öncelikli platform Windows 11, dil Türkçe. Kod ve komut adlarında mevcut proje ile tutarlı ol; kullanıcıya hata/yardım/kurulum metinleri Türkçe. Türkçe karakterli kullanıcı adı, yol, dosya ve uygulama başlıkları çalışmalı.
3. Kullanıcının günlük işi sesle tamamlanmalı. Sıradan, yetkili, geri alınabilir işler için sürekli onay isteme. Yetkiyi kullanıcı bir kez araç/klasör/uygulama/domain/görev kapsamında verebilsin; iptal edebilsin.
4. “Tam yetki” bütün kontrolleri kaldıran boolean olmasın. Yetkili çalışma alanı ve eylem kapsamı genişletilebilsin; bu kapsam model tarafından değiştirilemesin. Windows UAC ve başka uygulamaların erişim kontrolleri atlanmasın. Gerekli yükseltmeler sınırlı yardımcı süreç üzerinden, kullanıcıya açık biçimde yapılsın.
5. Asistanın cevabı sesli kısa, panelde gerektiğinde ayrıntılı olabilir. Sonucu, kullanılan kaynağı ve oluşturulan dosyayı gösterebilsin. Sahte başarı, uydurulmuş yüzde ilerleme ve çalışmayan buton yok.
6. Mevcut çalışır özellikler ve kullanıcı verileri korunacak. Kamera mevcut kapsamda yok; sessizce kamera ekleme. İlerideki kamera desteği ayrı, kapalı ve isteğe bağlı bir eklenti olabilir.
7. Önce çekirdeği doğrula, sonra kabiliyet ekle. “En zeki” iddiası model adına değil, Türkçe görev başarı oranına, gecikmeye ve hata toparlamaya dayansın.

### 5.2 Çalışmaya başlangıç ve devam protokolü

- Mevcut HEAD, branch, dirty dosyalar ve varsa `AGENTS.md`/`CLAUDE.md` talimatlarını oku. İncelenen SHA ile farkı çıkar. Kullanıcının değişikliklerini silme; ayrı geliştirme branch'i kullan.
- README, `docs/DURUM_VE_PLAN.md`, mevcut testler ve bu rapordaki dosyaları doğrula. Düzelmiş bulguyu tekrar açma.
- `docs/JARVIS_MASTER_PLAN.md` içinde bu şartnameyi; `docs/FEATURE_MATRIX.md` içinde her kabiliyetin durumunu; `docs/IMPLEMENTATION_STATUS.md` içinde kaldığın yeri tut.
- Durumlar: `planned`, `implemented`, `unit-tested`, `integration-tested`, `windows-verified`, `blocked`. Bir modülün bulunması, özelliğin çalıştığını kanıtlamaz.
- Her aşama sonunda küçük commit, doğrulama özeti, ilgili test sonucu, değişen davranış ve kalan bağımlılıkları kaydet. Sonraki hazır aşamaya geç; her rutin mühendislik seçimini kullanıcıya sorma.
- Harici hesap veya gerçek donanım gerektiren aşamada diğer işleri tamamla; eksik testi `blocked/not-run` olarak bırak, geçti sayma. Zorunlu kullanıcı adımını kopyalanabilir Windows yönergesiyle ver.
- Konuşma/oturum sınırında `NEXT_STEPS.md` oluştur: HEAD, tamamlanan IDs, test komutları, açık hatalar ve bir sonraki net adım. Kapsamı sessizce azaltma.

## 6. Ortak mimari ve çekirdek sözleşmeleri

Başlangıçta dağıtık servisler kurma. Tek kullanıcı için modüler Python uygulaması, SQLite ve gerektiğinde izole worker yeterlidir. Panel ve ses aynı uygulama servislerini kullanmalı.

Akış: giriş → konuşma/niyet çözümleme → görev planı → yetki değerlendirme → executor → gözlem/doğrulama → kalıcı event/result → panel ve ses yanıtı.

Yeni modül isimleri öneridir; mevcut yapıya uyarlayabilirsin. Aynı işi yapan ikinci bir çekirdek bırakma.

| Mevcut nokta | Hedef sorumluluk |
|---|---|
| `komutlar.py`, `sistem.py` | Hızlı intent parser ve platform adapter. Eylem doğrudan çalışmaz; executor çağrısına dönüşür. |
| `jarvis_core/motor.py` | Plan/replan, görev durum makinesi, ortak yürütme. Karmaşıklaştıkça `runtime/` altına ayrıştır. |
| `jarvis_core/araclar/temel.py` | ToolSpec, ToolResult, ActionRequest, observation/verifier sözleşmeleri |
| `jarvis_core/depo.py` | Schema migration, görev/eylem/event/artifact kayıtları; uzun transaction yok |
| `jarvis_core/izinler.py` | Merkezi policy, kullanıcı yetki profilleri, eyleme bağlı onay |
| `jarvis_core/llm.py`, `ayarlar.py` | Ollama adaptörü, typed settings, model yönlendirme, streaming, context budget |
| `ses.py` | Geriye uyumlu giriş; uygulama `audio/` servislerine taşınır |
| `araclar/uygulamalar.py`, `ekran.py` | `desktop/` oturum ve gözlem servisleri |
| `araclar/bilgi.py` | Web araştırma araçları; etkileşimli işler için `browser/` |
| `panel/sunucu.py`, `arayuz.html` | Typed API + event akışı + modüler frontend |
| Yeni `memory/`, `scheduler/`, `skills/`, `integrations/`, `coding/`, `downloads/` | İlgili alanın servisleri; hepsi merkezi executor kullanır |

Her eylemde en az: `task_id`, `action_id`, `attempt_id`, `parent_action_id`, araç ve sürümü, doğrulanmış argüman, kaynak türü, yetki kapsamı, deadline, cancellation token, kaynak kilitleri, idempotency yaklaşımı, önkoşul, postcondition, artifact/undo referansı bulunmalı.

ToolResult: işlem başarısı ile hedef doğrulamasını ayrı tut. `succeeded`, `verified`, `partial`, `failed`, `cancelled`, `unknown_effect` durumlarını açık modelle. Stdout, çıkış kodu, kanıt, dosya/URL ve hata kategorisini taşı. Üst katman bu veriyi kaybetmesin; mevcut `Sonuc.veri` gibi alanlar kayıt/UI'ya ulaşsın.

SQLite migration sürümü, transaction ve connection sahipliği belirle. İşlem tamamlandı olayı ancak kayıt başarılı olduktan sonra yayımlansın. Restartta aktif görevi kimin sahiplendiği belli olsun; iki JARVIS instance'ı aynı görevi yürütmesin.

“Exactly once” dış dünyada garanti edilemez. Sonucu belirsiz yan etkiyi tekrar çalıştırmadan gözlemle; doğrulanamıyorsa `unknown_effect` ve kullanıcıya net durum ver. Bir görev içinde aynı argümanlı her çağrıyı sonsuza dek aynı işlem sanma: ikinci tıklama, ikinci ses artırma veya farklı amaç için tekrar meşru olabilir. Dedup kimliği mantıksal eyleme bağlansın.

Kaynak kilitleri: masaüstü/fare/klavye tek sahibi; bir tarayıcı oturumu içindeki mutasyonlar seri; aynı dosya/proje yazmaları kilitli. Bağımsız okumalar paralel olabilir. Tek GPU'da birden fazla ağır modeli zorunlu paralel açma.

## 7. Aşama A — Önce doğruluk ve çalışma güvenilirliği

F01–F07 ile F12–F13 ve F20'yi önce ele al. Kabul testleri ilgili hatayı eski kodda göstermeli, düzeltmeden sonra geçmeli.

- Onay parser'ı `evet`, `hayır`, `belirsiz` dönsün. `yapma`, `onaylamıyorum`, `olur mu bilmiyorum`, `evet değil`, `hayır yapma` olumlu sayılmasın. Süresi geçen/onayı alınmış/değiştirilmiş eyleme eski approval uygulanamasın.
- Farklı araç çağrılarını amaç kimliğiyle izle. Bir başarısız okuma bile gerekli bilgiye erişimi engelliyorsa görev başarı sayılmasın. Sohbet amaçları için yan etki şartı aranmasın; dosya oluşturma amacı için gerçek dosya kanıtı aransın.
- Kullanıcıya “Yaptım (ama başarısız)” gibi çelişkili cevap verme. Model metni ile gerçek durum ayrışırsa kullanıcı yanıtını gerçek sonuca göre düzelt.
- Her görev/worker kendi iptal nesnesine sahip olsun; yeni görev başlarken eski thread'in iptal bayrağı temizlenmesin. Global durdurma aktif görevleri ve onların çocuk süreçlerini kapsasın; ilgisiz kullanıcı programlarını öldürmesin.
- Tool deadline ve toplam görev deadline monotonic saatle kontrol edilsin; tek batch içindeki her çağrıdan önce bütçe denetlensin. Uzun ağ isteği, ekran modeli, subprocess ve dosya akışı iptal yoluna bağlı olsun.
- Dosya yazma staging + fsync/atomic replace; backup adı UUID/action ID; undo öncesi mevcut hash ile beklenen sürüm karşılaştırılsın. Kullanıcının sonradan değiştirdiği dosyanın üstüne kör rollback yapma.
- Redaction JSON stringine uygulanmasın. Log, görev geçmişi, istisna, undo metadata ve artifact preview aynı redaction katmanını kullansın. Secret değerleri prompt veya log yerine OS credential store referanslarıyla yönetilsin.
- Aynı izin politikası panel, CLI, ses, scheduler, skill ve MCP için geçerli olsun. Mevcut `JARVIS_TAM_YETKI` migrate edilsin; eski davranış sessizce değişmesin.

## 8. Aşama B — Ollama zekâ ve performans katmanı

- Model yeteneklerini `/api/show` ile kontrol et; model adı üzerinden varsayım yapma. Kullanıcının gerçek CPU/RAM/GPU/VRAM, Ollama sürümü, model quantization ve context kapasitesini sağlık ekranında ölç.
- Genel sohbet, araç yürütme, kod, görsel ve embedding profilleri oluştur. Profiller farklı yerel model kullanabilir; bellek yetmezse sırayla yükle. Kod profilinin gerçekten çağrı yoluna bağlandığını test et.
- Fast-path basit kesin komutlarda LLM turu istemesin. Belirsiz/çok amaçlı cümlede routing LLM'ye dönsün. “Dolar geçen dosyayı bul” döviz kuru sorgusu olmasın.
- İlgili araç seçimi: az sayıda uygun şema + gerektiğinde araç keşfi. Türkçe Unicode normalizasyonu, ekler, uygulama takma adları ve follow-up bağlamı. Seçim başarısızsa kontrollü katalog genişletme.
- Konuşma belleğinde son referans verilen dosya, uygulama, sekme, proje, kişi, onay ve aktif amaç tutulmalı. “Onu diğer klasöre taşı” çözülebilmeli; iki aday varsa tek net soru.
- Plan yalnız gerçekten çok adımlı işte üretilecek. Plan görev bağımlılıklarını ve sonuç şartlarını içersin; başarısızlıktan sonra sınırlı replan. Modelin kendi değerlendirmesi bağımsız dosya/DOM/test kanıtının yerine geçmesin.
- Token budget, tool-output kısaltma, belge parçalama ve konuşma özetleme uygula. Özet, kanıt bağlantısı ve unresolved amaçları kaybetmesin. Tüm dosyayı prompt'a yığma.
- Streaming text delta panel ve konuşma servislerine gitsin. Reasoning/thinking alanlarını kullanıcıya veya TTS'ye basma. Tool argümanı tamamlanıp doğrulanmadan işlem başlatma.
- Ölçümler: queue time, model load, prompt eval, TTFT, üretim süresi/token hızı, tool süresi, ilk ses, toplam görev süresi, retry ve başarı oranı. Sıcak/soğuk çalıştırmaları ayrı raporla.
- Model karşılaştırmasını aynı Türkçe görev setinde yap. Büyük model her durumda daha iyi varsayılmasın; 3–5 yerel aday donanıma uygunsa değerlendirilsin. Kullanıcının modelini izinsiz kaldırma veya büyük indirmeyi gizleme.

## 9. Aşama C — Türkçe yerel ses deneyimi

- `STTProvider`, `TTSProvider`, `WakeWordProvider`, `TurnDetector`, `AudioDeviceManager` arayüzleri. Varsayılan STT çok dilli faster-whisper gibi yerel sağlayıcı; `.en` modeli Türkçe varsayılanı olmasın.
- TTS için Türkçe desteklediği gerçek ses örneğiyle doğrulanan yerel model; destekli SAPI/pyttsx3 fallback. Online Edge sesi yalnız kullanıcı seçerse. Yerel Türkçe ses yoksa bunu dürüstçe göster, İngilizce sesi Türkçe diye sunma.
- Tek mikrofon capture stream; input/output cihaz seçimi, sample-rate dönüşümü, VAD, konuşma sonu algılama, kısa pre-roll ve bounded buffer. Cihaz çıkarılıp takılınca toparlanma.
- Gerçek yerel wake word + kişisel telaffuz alias'ları; sessiz bekleme sırasında bütün ortam konuşmasını buluta yollama. Bas-konuş ve uyandırma modları ayrı olsun.
- Barge-in: kullanıcı konuşunca TTS dursun; “dur” eylemi iptal etsin, “bir de...” mevcut göreve yeni yönlendirme olarak işlenebilsin. Yankı filtresi kullanıcının konuşmasını silmesin. Hoparlör ve kulaklık ayrı test edilsin.
- Sesli onay ve dikteyi ayrı niyet modlarında işle. “Şunu yaz: bilgisayarı kapat” metin diktesi olmalı; power eylemine dönüşmemeli.
- Türkçe sayılar, saat, dosya uzantısı, URL, kısaltmalar ve teknik sözcükler için metin hazırlama. Panel özgün metni, ses sadeleştirilmiş metni kullansın.
- Aktif mikrofon, TTS sağlayıcısı ve kayıt durumu görünür olsun. Ham ses varsayılan olarak kalıcı saklanmasın; kullanıcı kontrollü tanılama örnekleri ayrı.
- Opsiyonel konuşmacı profili yanlış tetiklemeyi azaltabilir; ses tanıma tek başına güvenilir kimlik doğrulama sayılmasın.

## 10. Aşama D — Ekranı anlayan bilgisayar kontrolü

- Uygulama, executable, sürüm, Start Menu, pencere, monitör, DPI, bilinen klasör, çalışma alanı ve kurulu runtime haritası. İsteğe bağlı indeks, incremental yenileme, bozuk alias temizleme.
- Kontrol sırası: resmi uygulama/API aracı → Windows UI Automation → OCR/görsel hedefleme. Koordinat rastgele uydurulmasın; hedef gözleminden türesin ve ekran değişince yenilensin.
- Pencere odağı, PID, kontrol tipi, accessible name, bounding box ve snapshot kimliği. Click/type/scroll/drag/shortcut eylemlerinde doğru hedef ve son durum doğrulansın.
- Çoklu monitör, %125/%150/%200 DPI, taşınmış pencere, Türkçe/İngilizce Windows etiketleri ve modal pencereler.
- Kullanıcı fiziksel fare/klavye kontrolünü devralınca otomasyon duraklasın; programatik input ile kullanıcı inputu ayırt edilsin. UI'da “kontrol sende/JARVIS'te” durumu bulunsun.
- Dosya seçici, kaydet penceresi, uygulama aç/kapat, sekme ve form doldurma. Kaydedilmemiş belgeyi kapatırken uygulamanın uyarısı yönetilsin; zorla kapatma varsayılan olmasın.
- Ekran izleme sürekli ve gizli olmasın. Aktif görev veya açıkça etkinleştirilmiş yardımcı mod kapsamında capture, saklama süresi ve hassas alan maskeleme.
- “Ekrandaki hatayı açıkla ve çöz”, “Bu tabloyu Excel'e aktar”, “Bu pencereye metni yaz” için uçtan uca senaryolar.

## 11. Aşama E — Tarayıcı, araştırma ve indirme

- Playwright tabanlı kalıcı browser service. Ayrı JARVIS profili varsayılan; kullanıcının gerçek profilini otomatik kopyalama. Giriş/2FA/CAPTCHA gerektiğinde görevi duraklatıp kullanıcı devralmasına izin ver.
- Tab list/open/switch/close, navigate/back, DOM ve accessibility snapshot, metin/link/tablo çıkarma, locator ile tıklama/doldurma, bekleme, upload/download.
- Locator bulunamazsa yeni gözlem al; eski koordinat veya DOM ile ısrar etme. Mutation ve beklemeler timeout/iptal kapsamında.
- Web araştırması: birden fazla kaynak, tarih ve URL, çelişkili iddiaların işaretlenmesi, kaynaklı sonuç. Ekran içindeki talimatlar kullanıcı emri olmasın.
- Web fetch için response byte limit, streaming, content-type, redirect ve yerel ağ hedef politikası. Büyük/sonsuz yanıt bellek doldurmasın. İzinli LAN hizmetleri ayrı kapsamla kullanılabilsin.
- İndirme yöneticisi: URL/başlık/format/hedef, kuyruk, byte ilerlemesi, iptal, retry/resume destekleniyorsa devam, geçici uzantı, disk alanı kontrolü, isim çakışması, checksum/format doğrulama.
- Video/ses indirme adaptörü için yt-dlp + ffmpeg değerlendir; mevcut Tk indiricinin kabiliyeti merkezi göreve taşınsın. Erişilebilir ve kullanıcının indirmeye yetkili olduğu içerikle çalış; DRM/erişim engeli aşma özelliği ekleme.
- Playlist, yalnız ses, kalite, altyazı, transkript, zaman damgalı özet ve format dönüştürme. Gereksiz ham medya saklamama, çıktı yolu ve oynat/aç düğmeleri.
- Dosya URL'sini açmak “indirdim” demek değildir; hedef dosya ve tamamlanma kanıtı şart.

## 12. Aşama F — Dosyalar, belgeler ve üretilebilir çıktılar

- Toplu rename/move/copy, duplicate tespiti, içerik arama, arşiv oluştur/aç, hash ve diff. İşlem önizlemesi, çakışma politikası, ilerleme, iptal ve undo.
- Arşiv açmada path traversal/zip bomb sınırları; kullanıcı dosyasının üstüne sessiz yazma yok. Büyük dosyalar chunk ve stream ile işlenir.
- PDF metin/tablo çıkarma; taranmış PDF için OCR; DOCX/XLSX/CSV/MD/TXT içerik okuma. Sayfa/hücre/paragraf konumu ve kaynak hash'i korunur.
- PDF/DOCX/XLSX rapor ve tablo üretimi; XLSX formülleri, tarih/sayı biçimleri; belge düzenleme ve çıktı preview. “Dosya oluştu” ile “doğru içerik oluştu” ayrı doğrulansın.
- File/artifact registry: task_id, path, MIME, boyut, hash, sürüm, preview, kaynak, son açılma. Panelde bul/indir/aç/karşılaştır/geri dön.
- Örnek: “İndirilenlerdeki bu ayın faturalarını bul, tarih ve toplamlarını tabloya çıkar, Belgeler/Faturalar'a kaydet.” Kaynak belgeye geri gidilebilir olmalı.

## 13. Aşama G — Kalıcı hafıza ve kişisel bağlam

- Ayrı katmanlar: son konuşma, kalıcı kullanıcı tercihi, proje bilgisi, görev deneyimi ve belge indeksi. Kaynak, zaman, doğruluk durumu, entity, project_id, version/supersedes ve retention taşısın.
- Başlangıçta SQLite FTS + metadata yeterli; gerekli yerde yerel Ollama embedding ile hibrit arama. Ağır graph DB zorunlu değil.
- Aynı kullanıcı bilgisinin yeni sürümü eskisini supersede etsin. Web'den çıkan bir iddia kullanıcı tercihi gibi kaydedilmesin. Çelişkili önemli bilgi doğrulatılsın.
- Hafıza ekranında ara, ekle, düzelt, unut, dışa aktar. Unutulan bilgi prompt, embedding, özet ve cache'ten de kalkmalı; eski backup kapsamı kullanıcıya belirtilmeli.
- İndeksleme yalnız seçili klasörlerde; dosya silinince/taşınınca güncelle; secret ve credential dizinlerini varsayılan dışarıda tut.
- “Geçen hafta yaptığımız siteyi aç”, “Bana kısa konuş”, “Bunu Aurvex projesine kaydet” bağlamı çözülebilsin. Mevcut hafıza kayıtları migration ile korunsun.
- Otomatik öğrenme önce başarılı prosedür ve tercih hafızasıdır; kontrolsüz fine-tuning veya modelin kendi iddiasını doğru veri sayması değildir. Fine-tuning ancak ayrı değerlendirme/rollback süreciyle ileri aşama opsiyonu.

## 14. Aşama H — Kod yazma ve web sitesi üretme

JARVIS hem kendi yönetim arayüzüne sahip olacak hem de kullanıcının isteğiyle başka uygulama/web siteleri üretebilecek. Bunlar ayrı modüllerdir.

- `coding/` proje servisi: create/import repo, dosya ağacı, search/read, patch, formatter/linter/test/build, git diff ve commit hazırlığı, log ve artifact.
- Her geliştirme görevi ayrı workspace/worktree; var olan kullanıcı değişikliklerini koru. Shell/script gerektiğinde sınırlı çalışma alanı, explicit argv/script dosyası, timeout, output limit, environment allowlist ve child-process ownership kullan.
- Üretilen keyfi kod yalnız regex denetimiyle güvenli sayılmaz. Güvenilmeyen kodu işletim sistemi/container sandbox'ında çalıştır; host GUI otomasyon yetkisini bu koddan ayır. Windows Sandbox/WSL/container bulunamıyorsa kabiliyeti doğru göster, koruma varmış gibi davranma.
- Gereken bağımlılıklar, port, runtime ve dosya izinlerini preflight ile kontrol et. Her task için sonsuz paket kurulum döngüsü yok.
- Web üretimi: brief → kapsam → tasarım → uygulama → yerel preview → test/build → teslim. Mevcut projede teknoloji yığınını koru; yeni basit projede React/TypeScript/Vite gibi hafif, test edilebilir temel seçilebilir.
- Playwright ile responsive, console, form, navigation ve screenshot doğrulaması. Önizleme sunucusu JARVIS kontrol API'sinden ayrı origin/portta çalışsın ve JARVIS tokenına erişmesin.
- Site düzenleme konuşması: “Başlığı değiştir”, “Rengi koyulaştır”, “Mobil menüyü düzelt”, “Önceki sürüme dön” ilgili projeye uygulansın.
- Yayınlama: ayrı deploy adapter; hedef hesap/proje, yayınlanacak commit/build ve maliyet bilgisi belli olsun. Önceden verilen yetki kapsamıyla çalış; yeni dış etki için gereken onayı somut preview hazır olduktan sonra iste. Sahte URL üretme.
- Varsayılan kodlama Ollama ile yapılır. Kullanıcının ayrıca bağladığı CLI ajanları opsiyonel adaptördür; ürün onlarsız çalışmalı.
- Kendini geliştirme: kullanıcı “şu beceriyi ekle” dediğinde özellik talebi → branch → patch → test → diff → etkinleştirme. Çalışan çekirdeği test etmeden kendi kendine değiştirme.

## 15. Aşama I — Beceriler, MCP ve entegrasyonlar

- Versiyonlu skill manifest: ID, açıklama, Türkçe örnekler, parametre şeması, gerekli araçlar/yetkiler, desteklenen platform, dependency/model gereksinimi, timeout, testler, lisans/kaynak ve sürüm.
- Yaşam döngüsü: draft → validated → enabled → disabled/rollback. Başarılı bir görevi “bunu rutin olarak öğren” ile parametrik beceriye dönüştür. Sabit kişisel yolları kodun içine gömme.
- Yerleşik beceriler: dosya düzenleme, araştırma raporu, medya indir/transkript, uygulama iş akışı, site üretimi, proje bakım ve sabah özeti.
- Skill runner bütün yan etkileri executor üzerinden geçirsin. Plugin değişince araç kataloğunu yenile; uyumsuz şemayı etkinleştirme. Bir bozuk eklenti tüm asistanı çökertmesin.
- MCP client: stdio ve desteklenen HTTP transport, handshake/capability negotiation, schema import, namespacing, timeout/cancel, persistent session, reconnect, tool-list değişimi ve audit. Aynı stateful sunucuya mutasyonları seri gönder.
- MCP'nin “read-only” etiketi tek başına izin garantisi değildir; merkezi policy risk sınıflaması uygula. Secret env değerlerini loga basma. Doğrudan internete açık JARVIS komut sunucusu oluşturma.
- Bağlantılar ekranı: sağlıklı/bozuk/yetki bekliyor durumları, credential store, bağlantıyı kesme, test düğmesi ve gereken kapsamlar.
- İsteğe bağlı adaptör listesi: GitHub; Gmail/Outlook; Google/Microsoft Calendar; Drive/OneDrive; Telegram; Spotify; Home Assistant; Obsidian/Markdown. Her birinin gerçek kurulum, yetkilendirme, okuma/yazma ve hata testi olmalı. Hesap yoksa kart “kurulu değil/bağlı değil” gösterir, işlev çalışıyor gibi davranmaz.
- Mesajlarda alıcı kimliği çözümü, taslak, gönderim idempotency ve teslim durumu. Gönderme/silme/paylaşma yetkisi kullanıcının açık kapsamına bağlı olsun; belirsiz kişiye tahminle gönderme.
- İsteğe bağlı telefon/uzak panel: güvenli pairing, TLS/VPN, revoke ve session timeout; yerel localhost anahtarını genel web'e taşıma. Ekran kontrolü devralma ve ses kanalı ayrı yetkiler.
- İsteğe bağlı Home Assistant cihaz/sahne yönetimi aynı görev sistemiyle çalışsın. Kritik cihazlarda ilgili eylem kapsamı açık tanımlansın.

## 16. Aşama J — Kalıcı otomasyon ve proaktif yardım

- Scheduler verileri DB'de; timezone `Europe/Istanbul` kullanıcı ayarı olarak, UTC kayıt + yerel sunum. Tek sefer, tekrar, cron ve doğal dil planlaması; “yarın 9” kaydedilen kesin tarih/saatle kullanıcıya gösterilir.
- Missed-run: atla/tek kez telafi/yeniden planla; duplicate önleme, concurrency sınırı ve retry backoff. Restartta aynı mesaj/indirme iki kez olmasın.
- File watcher, uygulama açılması, indirme tamamlanması, saat ve izinli kaynak değişimi tetikleyicileri. Debounce, döngü önleme, tetikleyici sahibi ve audit.
- Rutin editörü: adımlar, koşullar, parametre, çıktı klasörü, yetki, etkin/pasif ve çalışma geçmişi. Kullanıcı doğal dille oluşturabilsin ve panelde düzenleyebilsin.
- Proaktif mod opsiyonel: sessiz saatler, oyun/odak modu, bildirim sıklığı, kullanıcı meşguliyetinde erteleme. Her gördüğünü görev sanmasın.
- Örnekler: her sabah takvim/hava özeti; haftalık indirme klasörü düzenleme önerisi; proje test raporu; dosya geldiğinde özetleme. Kullanıcı yetkisi dışında dış mesaj gönderme veya gerçek para işlemi oluşturma.
- Batuhan için opsiyonel proje becerileri: havuz bakım kayıtlarından haftalık rapor ve Aurvex log/test raporu özeti. Bunlar alan verisi araçlarıdır; kimyasal doz veya canlı trade otomasyonu çekirdeğe varsayılan eklenmez.

## 17. Aşama K — JARVIS komuta merkezi ve görsel kalite

Mevcut koyu/camgöbeği HUD kimliğini koru. Merkezde dev animasyon yüzünden iş sonuçları kaybolmasın. Gösterişli mod ve sade çalışma modu sun.

Frontend için React + TypeScript + Vite; Python API için FastAPI önerilir. İlk aşamada mevcut server korunabilir, fakat yeni ekranlarla birlikte tek API sözleşmesine kademeli geçiş yap. Eski ve yeni sunucu iki ayrı yürütme yolu oluşturmasın. Masaüstü kabuğu olarak Edge app modunu fallback tut; pywebview/WebView2 veya uygun paketleme çözümünü ölçerek seç.

| Ekran | Gerçek işlev |
|---|---|
| Ana komuta ekranı | Ses/yazı, aktif görev, gerçek ilerleme, hızlı işler, dosya sürükle-bırak, duraklat/devam/iptal |
| Görevler | Kuyruk, geçmiş, filtre, amaç/adım timeline, deneme/kanıt/hata, güvenli devam ve undo |
| Çalışma alanları | Proje ve dosyalar, artifact preview, git diff, site preview, build/test çıktısı |
| Hafıza | Kaynaklı kayıtlar, proje/kişisel ayrımı, ara/düzelt/unut/export |
| Beceriler | Mevcut kabiliyetler, gereksinimler, kur/etkinleştir/test/sürüm/rollback |
| Otomasyon | Takvim, rutin editörü, tetikleyiciler ve çalıştırma geçmişi |
| Bağlantılar | MCP/servisler, hesap kapsamı ve sağlık durumu |
| Model merkezi | Kurulu Ollama modelleri, yetenekler, yüklenen model, ölçümler ve profil seçimi |
| Ses ayarları | Mikrofon/hoparlör seçimi, seviye testi, wake word, TTS örneği ve offline durumu |
| Yetkiler | Kapsam bazlı trusted-workspace profilleri, onay geçmişi, izin iptali |
| Sağlık | CPU/RAM/VRAM, bağlantılar, hatalar, tanılama, güncelleme ve backup |

- Tek event modeli: event_id, task_id, action_id, timestamp, type ve payload. Reconnect'te snapshot + son event cursor; yinelenen event UI'da yinelenmesin.
- Panel yenilendiğinde aktif görev ve pending approval kaybolmasın. Approval kartı hangi dosya/uygulama/kişi/işleme ait olduğunu göstersin.
- Görev durumları Türkçe anlaşılır: Sırada, Dinliyor, Planlıyor, Çalışıyor, Senden bilgi bekliyor, Duraklatıldı, Doğrulanıyor, Tamamlandı, Kısmen tamamlandı, İptal edildi, Başarısız.
- API typed request validation, tutarlı error envelope, token rotation, session, host/origin kontrolleri, request size/time limit. String `"false"` bool `True` diye kabul edilmesin.
- Responsive: 1440/1366/1024/768/390 px kontrolleri; en az %200 zoom, keyboard focus, Escape davranışı, screen reader etiketleri, contrast ve reduced motion. Formda yazarken kısayollar metni bozmamalı.
- `innerHTML` yerine güvenli render; içerik ve kaynak linkleri sanitize. Artifact preview izolasyonu; rastgele HTML JARVIS API yetkisi almasın.
- Gerçek mikrofon seviyesiyle dalga; kapalı/görünmez panelde gereksiz animasyon/telemetri azalt. Sahte “zeka seviyesi” göstergesi ekleme.
- Küçük tray/popup modu, minimize-to-tray seçeneği, global push-to-talk, sistem başlangıcı ve tek instance.
- Public tanıtım sitesi istenirse yalnız doküman/demo/indirme sitesi olsun. Yetkili yerel komuta paneli internete açık landing page ile birleştirilmesin.

## 18. Aşama L — Kurulum, bakım ve sürümleme

- Temiz Windows kurulum sihirbazı: Python/runtime, Ollama erişimi, model yetenekleri, disk/bellek, mikrofon, yerel TTS ve hotkey testi. Gereken indirmelerin boyutu ve hedefi görünür.
- `pyproject.toml`, desteklenen Python sürümü, kilitli bağımlılıklar ve `core/audio/desktop/browser/dev` extras. Eski CPython 3.8 PyAudio wheel'i güncel kurulum yolu sanma.
- Win32 bağımlılıkları lazy import; Linux headless testleri Windows GUI bağımlılığı yüzünden çökmemeli.
- SQLite migration öncesi backup, sürüm uyumluluğu, geri dönüş planı, kullanıcı veri dizininin uygulama kodundan ayrılması.
- Hata logları döndürülsün; tanılama export'u secret/audio/screenshot içerip içermediğini göstererek üretilebilsin. Log tutulması “her şeyi kaydet” anlamına gelmesin.
- Sağlık gözetmeni çöken bağımlılığı sınırlı retry ile toparlasın; restart loop ve iki importer/instance benzeri çoğalma olmasın.
- Paketlenmiş Windows release için clean install, update, uninstall ve yeniden açılış testi. Güncelleme kullanıcı dosyasını/izinlerini silmesin; hash/imza doğrulama ve rollback.
- GitHub Actions: Linux core tests, Windows uyum testleri, frontend typecheck/build, deterministic browser fixture testleri; gerçek mikrofon/GUI gerekiyorsa uygun interactive Windows runner veya manuel kapı. Hosted Windows runner'ın her masaüstü senaryosunu doğruladığını varsayma.
- README yalnız doğrulanmış kabiliyetleri vaat etsin; gerçek offline/online sınırını yaz. Eski upstream atıfları lisans/notices altında korunurken yanıltıcı eski özellik metni temizlensin.

## 19. Kabul testleri: “çalışıyor” demenin şartı

Aşağıdaki senaryolar birim + entegrasyon + Windows/live olarak ayrılmalı. Mock test, canlı cihaz testinin yerine geçmez. Kapsamlı her özelliğin en az bir kullanıcı senaryosu, olumsuz yol ve restart/iptal davranışı olmalı.

| ID | Senaryo | Geçme şartı |
|---|---|---|
| T01 | Onayda “yapma/onaylamıyorum/hayır yapma” | Hiçbir yan etki yok; negative/ambiguous doğru |
| T02 | Aynı araç, biri başarısız iki farklı dosya işi | İkinci başarı ilk hatayı örtmez |
| T03 | Şema dışı argüman veya uydurma araç | Kayıtlı hata; sahte completed yok |
| T04 | Harici talimat içeren dosyayı okuduktan sonra crash/resume | Kaynak kökeni ve yetki kapsamı korunur |
| T05 | Gizli metinli konuşma checkpoint | Valid JSON, maskeleme, güvenilir recovery |
| T06 | Hızlı “Chrome'u aç”, model ile eşdeğer komut | Aynı executor/audit/policy, gözlenen sonuç |
| T07 | Uzun alt süreç ve torun süreç çalışırken durdur | Sahip olunan süreç ağacı kapanır; sonradan yan etki yok |
| T08 | Büyük dosya kopyalama sırasında iptal | Kısmi çıktı doğru işaretlenir/temizlenir; kaynak sağlam |
| T09 | Aynı saniye aynı adlı dosyalara iki overwrite | İki ayrı yedek, doğru undo |
| T10 | İzinli işte retry; aynı eylem için restart | Yinelenen yan etki yok; meşru ikinci eylem engellenmez |
| T11 | “Dolar geçen dosyayı bul” / “durum ne” | Yanlış döviz/stop komutu yok |
| T12 | “Şunu yaz: bilgisayarı kapat” | Yalnız metin yazılır |
| T13 | İnternet kapalı Türkçe sesli dosya oluşturma | Yerel ses + Ollama ile tamam; çevrimiçi fallback yok |
| T14 | Jarvis konuşurken “dur” | TTS ve ilgili görev durur; ölçülen gecikme raporlu |
| T15 | Hoparlör TTS yankısı, 30 dk dinleme | Kendi kendine komut yürütmez; yanlış tetik sayısı kayıtlı |
| T16 | Mikrofon çıkar/tak, cihaz değiştir | UI doğru durum; uygulama çökmez |
| T17 | Türkçe karakterli path ve OneDrive bilinen klasörü | Dosya doğru yerde, hash/içerik doğrulanmış |
| T18 | “Onu diğer klasöre taşı” | Doğru referans; belirsizse tek soru |
| T19 | UIA hedefi kaybolur/odak değişir | Yanlış pencereye yazmaz; yeniden gözlem |
| T20 | Kullanıcı mouse'u devralır | Otomasyon duraklar, kontrol göstergesi güncel |
| T21 | 2 monitör + yüksek DPI | Görsel hedef ve koordinat dönüşümü doğru |
| T22 | Yerel test web formunu doldur/submit | DOM postcondition; duplicate submit yok |
| T23 | Browser login/2FA gerekiyor | Kullanıcı devralma; kaldığı yerden doğru devam |
| T24 | Büyük indirme, ağ kesilmesi, iptal | Progress gerçek; yarım dosya tam sayılmaz |
| T25 | Video → ses + altyazı + özet | Üç çıktı açılabilir; kaynak/zaman damgası var |
| T26 | PDF faturaları → XLSX | Kaynak sayfa/hücre ilişkisi ve tutarlı değerler |
| T27 | Bozuk belge/arşiv veya çok büyük response | Kaynak limitleri; anlaşılır hata; çökme yok |
| T28 | Hafızada eski tercih → yeni tercih → unut | Çelişki çözülür; unutulan retrieval'da yok |
| T29 | Yeni site oluştur, preview, mobil düzeltme | Build/test geçer, gerçek preview ve değişiklik |
| T30 | Mevcut dirty repo'da kod düzelt | Kullanıcı değişikliği korunur, diff/test kanıtlı |
| T31 | Kod worker crash veya sandbox yok | Çocuk süreç kontrolü; sahte izolasyon/başarı yok |
| T32 | Beceri oluştur/test/enable/rollback | Sürüm ve yetki kayıtlı, eski sürüme dönüş mümkün |
| T33 | MCP kopar veya tool schema değişir | Yeniden bağlantı; stale schema yürütülmez |
| T34 | Uygulama yeniden başlarken rutin zamanı geçer | Missed-run politikasına göre tek sonuç |
| T35 | Watcher kendi çıktısını görür | Sonsuz tetikleme yok |
| T36 | Panel reload/SSE reconnect sırasında pending approval | Kart ve görev doğru geri gelir; duplicate yok |
| T37 | Yetkisiz origin/token ve geçersiz API payload | Yan etki olmadan reddedilir |
| T38 | Site preview içine kötü niyetli JS | JARVIS kontrol API'sine yetkili erişim yok |
| T39 | Temiz Windows kurulum/update/rollback | Veri ve ayarlar korunur, kısayol/tray çalışır |
| T40 | 390px ekran, %200 zoom, klavye, reduced-motion | Ana görev ve durdurma/onay kontrolleri erişilebilir |
| T41 | Ollama kapalı, model eksik veya VRAM yetersiz | Açık çözüm; cloud'a kaçış ve sonsuz retry yok |
| T42 | Kullanıcı yetkiyi görev ortasında geri alır | Sonraki eylem güncel policy ile durur |

## 20. Ölçüm ve kalite kapıları

Önerilen mühendislik hedefleri aşağıdadır; ölçülmüş mevcut performans değildir. Donanım bilinmeden “her cihazda 1 saniye” vaadi verme.

- UI input/ack p95 <250 ms; modelden bağımsız basit komutlarda gereksiz LLM gecikmesi sıfır.
- Stop UI teyidi <250 ms; ilgili kontrollü işin fiili bitişi p95 <1 sn hedef. İş sonlandırılamıyorsa “durduruluyor/sonuç belirsiz” durumu göster, durdu diye raporlama.
- Sesli komut sonundan ilk anlamlı yanıt sesine kadar warm p50/p95 ölç; hedef donanıma göre örneğin <2.5 sn belirlenebilir. “Dinliyorum” sesi görev cevabı performansı yerine sayılmaz.
- İlk 50 Türkçe uçtan uca görev setinde hedef >=%90 doğrulanmış başarı; başarı sayısını hangi model/donanım/kaç tekrar ile ölçtüğünü yaz. Kritik yanlış mutasyon ve sahte başarı hedefi 0.
- Test seti yalnız kolay tek komutlardan oluşmasın: çok adım, olumsuzluk, follow-up, yanlış hedef, ağ kesintisi, restart, düşük bellek ve belirsiz kullanıcı isteği içersin.
- En az 30 dakikalık idle/ses smoke ve uzun görev sırasında RAM/VRAM trendi; 8 saat soak testi Windows doğrulama aşamasında. Büyük memory leak veya sürekli büyüyen queue olmamalı.
- Paket kurulumu ve modellerin ilk indirilmesi, günlük açılış performansından ayrı ölçülsün.

## 21. Teslim sırası ve tamamlanma tanımı

Önce A (çekirdek doğruluk), ardından B (Ollama) ve C (ses). Sonra D/E/F (bilgisayar, tarayıcı, dosyalar), G (hafıza), H (kod/site), I/J (beceri/entegrasyon/rutin), K/L (tam ürünleştirme). K için API/event temeli erken kurulabilir; bütün ekranların cilası çekirdekten önce gelmesin.

Her aşamanın teslimi:

1. Kullanıcı girişinden gerçek sonuca çalışan dikey özellik; yalnız backend sınıfı veya dekoratif UI değil.
2. Mevcut davranışı koruyan migration/adapter ve gerekli regresyon testi.
3. Başarı/başarısızlık/iptal/restart davranışı ve ölçüm kanıtı.
4. Dokümanda implemented/tested/windows-verified ayrımı.
5. Kullanıcının Windows'ta çalıştıracağı kısa ve net adımlar; mümkün olduğunca setup wizard üzerinden.

Bir özelliğin “tamam” sayılması için UI veya ses girişi → intent → gerçek araç → gözlem → kalıcı kayıt → kullanıcı sonucu zinciri çalışmalıdır. Entegrasyon hesabı, donanım veya bağımlılık eksikse adı ve eksik adım açıkça listelenmelidir. Mock veri, placeholder button, boş adapter veya test edilmemiş başarı iddiası kabul edilmez.

**Şimdi güncel repo durumunu doğrula, F01–F07 regresyonlarını oluştur ve Aşama A'yı uygulamaya başla. Yalnız bu planı yeniden anlatıp durma. Sonraki uygulanabilir aşamalara bu dosya ve durum kayıtları üzerinden devam et.**
