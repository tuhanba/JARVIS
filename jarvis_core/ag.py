"""Safe HTTP fetching for tools that read the web.

- streams the body and stops at a byte limit (a huge or endless response
  cannot fill memory);
- accepts only text-like content types;
- follows redirects by hand (at most 5) and checks every hop;
- refuses loopback / private / link-local targets unless the user allowed
  that host (`/ag-izin <host>`): a web page must not be able to point JARVIS
  at the router, a local admin panel or JARVIS's own control API."""
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import requests

AZAMI_BAYT = 2 * 1024 * 1024
METIN_TURLERI = ('text/', 'application/xhtml', 'application/json', 'application/xml', 'application/rss',
                 'application/atom')


class AgHatasi(Exception):
    """Message is shown to the model/user as is."""


def _yerel_mi(host: str) -> bool:
    try:
        adresler = {a[4][0] for a in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        raise AgHatasi(f'{host} adresi çözülemedi (internet bağlantısı?).')
    for a in adresler:
        ip = ipaddress.ip_address(a.split('%')[0])
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast \
                or ip.is_unspecified:
            return True
    return False


def getir(url: str, izinli_hostlar=(), azami_bayt: int = AZAMI_BAYT, zaman_asimi: float = 15, iptal=None):
    """Returns (text, final_url, content_type). Raises AgHatasi with a Turkish explanation."""
    for _ in range(6):
        u = urlparse(url)
        if u.scheme not in ('http', 'https') or not u.hostname:
            raise AgHatasi(f'Yalnız http/https adresleri okunur: {url}')
        if u.hostname not in izinli_hostlar and _yerel_mi(u.hostname):
            raise AgHatasi(f'{u.hostname} yerel ağ/bu bilgisayar adresi; izin verilmeden okunmaz '
                           f'(izin: /ag-izin {u.hostname}).')
        try:
            r = requests.get(url, stream=True, timeout=zaman_asimi, allow_redirects=False,
                             headers={'User-Agent': 'Mozilla/5.0 JARVIS'})
        except requests.RequestException as e:
            raise AgHatasi(f'Sayfa açılamadı: {e}')
        with r:
            if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
                url = urljoin(url, r.headers.get('Location', ''))
                continue
            if r.status_code >= 400:
                raise AgHatasi(f'Sayfa açılamadı: HTTP {r.status_code}')
            tur = (r.headers.get('Content-Type') or '').lower()
            if tur and not tur.startswith(METIN_TURLERI):
                raise AgHatasi(f'Bu adres metin değil ({tur.split(";")[0]}); indirme için indirme aracını kullanın.')
            beyan = int(r.headers.get('Content-Length') or 0)
            if beyan > azami_bayt:
                raise AgHatasi(f'Sayfa çok büyük ({beyan // 1024} KB > {azami_bayt // 1024} KB sınırı).')
            parcalar, toplam, kesildi = [], 0, False
            for parca in r.iter_content(65536):
                if iptal is not None and iptal.is_set():
                    from .araclar.temel import Iptal
                    raise Iptal()
                toplam += len(parca)
                if toplam > azami_bayt:
                    parcalar.append(parca[:azami_bayt - (toplam - len(parca))])
                    kesildi = True
                    break
                parcalar.append(parca)
            govde = b''.join(parcalar)
            kodlama = r.encoding or r.apparent_encoding or 'utf-8'
            metin = govde.decode(kodlama, errors='replace')
            if kesildi:
                metin += f'\n[… {azami_bayt // 1024} KB sınırında kesildi]'
            return metin, url, tur
    raise AgHatasi('Çok fazla yönlendirme.')
