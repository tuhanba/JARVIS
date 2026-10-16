# NEXT_STEPS — devam noktası

Branch: `claude/eloquent-wright-zsg2o5` (main: `1721259`). HEAD için `git log -1`.
Plan: `docs/JARVIS_MASTER_PLAN.md` · Durum: `docs/IMPLEMENTATION_STATUS.md` · Matris: `docs/FEATURE_MATRIX.md`

## Tamamlanan ID'ler

- Bulgular: F01, F02, F03, F04, F05 (secret store hariç), F06, F07, F12, F13, F14, F20; kısmi: F08, F10, F11,
  F16, F17, F18 (yalnız onay kartı), F19, F21.
- Kabul testleri (otomatik, Linux; çoğu Windows CI'da da): T01, T02, T03, T04, T05, T06, T07, T08, T09, T11,
  T12, T27 (web + belge), T28, T34, T36, T37, T42; kısmi: T10, T13 (yerel ses + Ollama, internetsiz tur), T18.

## Test komutları

```
python -m pip install -r requirements-test.txt
python -m pytest -q tests                                     # başsız paket (Linux/Windows)
JARVIS_CANLI=1 OLLAMA_MODEL=<model> python -m pytest -s tests/test_canli_ollama.py
JARVIS_SES_MODEL_VERI=<veri dizini> python -m pytest -q tests/test_asama_c.py -k cevrimdisi
python -m jarvis_core.degerlendirme --model <model> --tekrar 3  # Türkçe görev seti, sahte başarı sayacı
```

## Kullanıcının Windows'ta yapması gerekenler (kopyalanabilir)

```
cd JARVIS
git pull
python -m pip install -r requirements.txt
python -m jarvis_core.audio.kur
python -m jarvis_core.saglik
python -m jarvis_core.degerlendirme --tekrar 3
```

Sonra `veri\degerlendirme\*.json` dosyasını ve `saglik` çıktısını paylaşın: GPU/VRAM, model yetenekleri,
gerçek başarı oranı ve sahte başarı sayısı buradan ölçülecek. Mikrofonla "Chrome'u aç", "İndirilenlerdeki
faturayı Belgelere taşı" deyip tanınan metni not edin (gerçek ses doğruluğu ölçülmedi).

## Açık hatalar / riskler

- `qwen3:1.7b` takip görevini ("onu Belgeler'e taşı") geçemedi; küçük model sınırı mı, prompt mu belli değil.
- Panelin geri kalanı dar ekranda taşıyor (F18); yalnız onay kartı düzeltildi.
- Web okumada DNS çözümü ile bağlantı arasında yeniden bağlama (rebinding) penceresi var (ag.py).
- Ses: mevcut uyandırma sözcüğü STT sonrası regex; gerçek yerel wake word ve barge-in yok.
- Model metnindeki başarı iddiası tespiti sezgisel.

## Bir sonraki net adım

Aşama B'nin kalanı: çok adımlı isteklerde açık plan (adım + sonuç şartı) ve başarısızlıktan sonra sınırlı
replan; ardından Aşama D için Windows UIA gözlem/eylem/doğrulama döngüsü (`desktop/`), pencere hedefi kaybolunca
yanlış pencereye yazmama testi (T19) — bu kısım Windows'ta doğrulanmalı.
