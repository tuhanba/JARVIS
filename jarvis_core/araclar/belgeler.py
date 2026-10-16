"""Read documents (PDF, Word, Excel, CSV, text, HTML) and write reports
(.docx, .md, .txt, .html). Document text is untrusted data."""
import csv
import io
import re
from pathlib import Path

from .. import yollar
from ..izinler import OKUMA, YAZMA
from .dosyalar import _disk_hatasi, _yedekle
from .temel import Sonuc, arac, metin

SINIR = 12000


def _pdf(p: Path, bas: int, adet: int):
    from pypdf import PdfReader
    okuyucu = PdfReader(str(p))
    if okuyucu.is_encrypted:
        try:
            okuyucu.decrypt('')
        except Exception:
            return None, 'PDF parola korumalı; okuyamıyorum.'
    toplam = len(okuyucu.pages)
    parcalar = []
    for i in range(bas - 1, min(toplam, bas - 1 + adet)):
        parcalar.append(f'--- Sayfa {i + 1} ---\n{(okuyucu.pages[i].extract_text() or "").strip()}')
    metin_ = '\n'.join(parcalar)
    if not re.sub(r'--- Sayfa \d+ ---|\s', '', metin_):
        return metin_, f'{toplam} sayfa; metin çıkmadı (taranmış/görüntü PDF olabilir).'
    return metin_, f'{toplam} sayfa, {bas}-{min(toplam, bas - 1 + adet)}. sayfalar okundu.'


def _docx(p: Path):
    import docx
    belge = docx.Document(str(p))
    satirlar = [par.text for par in belge.paragraphs if par.text.strip()]
    for tablo in belge.tables:
        for satir in tablo.rows:
            satirlar.append(' | '.join(h.text.strip() for h in satir.cells))
    return '\n'.join(satirlar), f'{len(belge.paragraphs)} paragraf, {len(belge.tables)} tablo.'


def _xlsx(p: Path):
    import openpyxl
    kitap = openpyxl.load_workbook(str(p), read_only=True, data_only=True)
    parcalar = []
    for sayfa in kitap.worksheets:
        parcalar.append(f'--- Sayfa: {sayfa.title} ---')
        for i, satir in enumerate(sayfa.iter_rows(values_only=True)):
            if i >= 200:
                parcalar.append('... (ilk 200 satır)')
                break
            if any(h is not None for h in satir):
                parcalar.append(' | '.join('' if h is None else str(h) for h in satir))
    return '\n'.join(parcalar), f'{len(kitap.worksheets)} çalışma sayfası.'


def _csv(p: Path):
    ham = p.read_text(encoding='utf-8-sig', errors='replace')
    try:
        lehce = csv.Sniffer().sniff(ham[:4000], delimiters=',;\t|')
    except csv.Error:
        lehce = csv.excel
    satirlar = list(csv.reader(io.StringIO(ham), lehce))
    return '\n'.join(' | '.join(s) for s in satirlar[:300]), f'{len(satirlar)} satır.'


def _html(p: Path):
    from bs4 import BeautifulSoup
    sayfa = BeautifulSoup(p.read_text(encoding='utf-8', errors='replace'), 'html.parser')
    for e in sayfa(['script', 'style', 'noscript']):
        e.decompose()
    return re.sub(r'\n\s*\n+', '\n', sayfa.get_text('\n')).strip(), 'HTML sayfası.'


@arac('belge_oku', 'PDF, Word (.docx), Excel (.xlsx), CSV, metin veya HTML belgesinin içeriğini okur. '
      'Uzun PDF\'lerde sayfa aralığı verilebilir.',
      {'yol': metin('Belgenin yolu, ör. "Belgeler/rapor.pdf"'),
       'ilk_sayfa': {'type': 'integer', 'minimum': 1, 'description': 'PDF için başlangıç sayfası (varsayılan 1)'},
       'sayfa_sayisi': {'type': 'integer', 'minimum': 1, 'maximum': 50, 'description': 'PDF için okunacak sayfa sayısı (varsayılan 20)'}},
      ['yol'], risk=OKUMA, yan_etki=False, zaman_asimi=120, guvenilmez_cikti=True)
def belge_oku(baglam, yol, ilk_sayfa=1, sayfa_sayisi=20):
    p = yollar.coz(yol)
    if not p.is_file():
        return Sonuc(False, f'Belge bulunamadı: {p}')
    uzanti = p.suffix.lower()
    try:
        if uzanti == '.pdf':
            icerik, bilgi = _pdf(p, ilk_sayfa, sayfa_sayisi)
            if icerik is None:
                return Sonuc(False, bilgi)
        elif uzanti == '.docx':
            icerik, bilgi = _docx(p)
        elif uzanti in ('.xlsx', '.xlsm'):
            icerik, bilgi = _xlsx(p)
        elif uzanti in ('.csv', '.tsv'):
            icerik, bilgi = _csv(p)
        elif uzanti in ('.html', '.htm'):
            icerik, bilgi = _html(p)
        elif uzanti in ('.doc', '.xls', '.ppt', '.pptx'):
            return Sonuc(False, f'{uzanti} biçimini okuyamıyorum; .docx / .xlsx / .pdf olarak kaydedilirse okuyabilirim.')
        else:
            icerik, bilgi = p.read_text(encoding='utf-8', errors='replace'), 'Metin dosyası.'
    except Exception as e:
        return Sonuc(False, f'Belge okunamadı ({e.__class__.__name__}): {e}')
    kesildi = len(icerik) > SINIR
    return Sonuc(True, f'[{p.name}: {bilgi}{" İlk " + str(SINIR) + " karakter." if kesildi else ""}]\n{icerik[:SINIR]}',
                 veri={'yol': str(p), 'karakter': len(icerik)})


def _docx_yaz(p: Path, baslik: str, icerik: str) -> None:
    import docx
    belge = docx.Document()
    if baslik:
        belge.add_heading(baslik, level=0)
    for satir in icerik.splitlines():
        s = satir.rstrip()
        if not s:
            continue
        if s.startswith('### '):
            belge.add_heading(s[4:], level=3)
        elif s.startswith('## '):
            belge.add_heading(s[3:], level=2)
        elif s.startswith('# '):
            belge.add_heading(s[2:], level=1)
        elif re.match(r'^\s*[-*•] ', s):
            belge.add_paragraph(re.sub(r'^\s*[-*•] ', '', s), style='List Bullet')
        elif re.match(r'^\s*\d+[.)] ', s):
            belge.add_paragraph(re.sub(r'^\s*\d+[.)] ', '', s), style='List Number')
        else:
            belge.add_paragraph(s.replace('**', ''))
    belge.save(str(p))


@arac('rapor_yaz', 'Bir rapor/belge oluşturur. Uzantıya göre Word (.docx), Markdown (.md), HTML (.html) veya metin (.txt) '
      'yazar. İçerikte "# Başlık", "## Alt başlık" ve "- madde" kullanılabilir.',
      {'yol': metin('Dosya yolu, ör. "Belgeler/PDF Özet Raporu.docx"'),
       'baslik': metin('Rapor başlığı'),
       'icerik': metin('Raporun içeriği'),
       'uzerine_yaz': {'type': 'boolean', 'description': 'Dosya varsa üzerine yazılsın mı (eski hali yedeklenir)'}},
      ['yol', 'baslik', 'icerik'], risk=YAZMA, yan_etki=True, yol_argumanlari=('yol',), zaman_asimi=60,
      harici_sonrasi_serbest=lambda a: not a.get('uzerine_yaz'))
def rapor_yaz(baglam, yol, baslik, icerik, uzerine_yaz=False):
    p = yollar.coz(yol)
    if not p.suffix:
        p = p.with_suffix('.docx')
    yedek = None
    try:
        if p.exists():
            if not uzerine_yaz:
                return Sonuc(False, f'{p} zaten var. Başka bir ad verin veya uzerine_yaz=true kullanın.', dogrulandi=False)
            yedek = _yedekle(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        uzanti = p.suffix.lower()
        if uzanti == '.docx':
            _docx_yaz(p, baslik, icerik)
            dogru = baslik in _docx(p)[0] if baslik else p.stat().st_size > 0
        elif uzanti in ('.html', '.htm'):
            import html
            govde = ''.join(f'<p>{html.escape(s)}</p>' for s in icerik.splitlines() if s.strip())
            p.write_text(f'<!doctype html><meta charset="utf-8"><title>{html.escape(baslik)}</title>'
                         f'<h1>{html.escape(baslik)}</h1>{govde}', encoding='utf-8')
            dogru = baslik in p.read_text(encoding='utf-8')
        else:
            p.write_text((f'# {baslik}\n\n' if baslik and uzanti == '.md' else (baslik + '\n\n' if baslik else ''))
                         + icerik, encoding='utf-8')
            dogru = icerik[:40] in p.read_text(encoding='utf-8')
    except OSError as e:
        return _disk_hatasi(e)
    geri = ({'tur': 'yedekten_yukle', 'yedek': str(yedek), 'hedef': str(p)} if yedek else {'tur': 'cop_kutusuna', 'yol': str(p)})
    return Sonuc(dogru, f'Rapor kaydedildi: {p} ({p.stat().st_size // 1024} KB).', dogrulandi=dogru,
                 veri={'yol': str(p)}, geri_al=geri)
