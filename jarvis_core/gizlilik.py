"""One redaction layer for everything JARVIS persists or shows: task
checkpoints, step logs, errors, undo metadata and panel events.

Masking runs on Python objects *before* JSON encoding, so it can never
break the JSON (the old regex ran on the encoded string and ate quotes)."""
import re

GIZLI_ANAHTAR = re.compile(r'(?i)^(parola|şifre|sifre|password|passwd|pwd|token|api[_-]?key|secret|anahtar|'
                           r'authorization|cookie|pin)$')
_GIZLI = [
    # "şifre: abc", "token=abc", 'api_key: "x y"'  (quoted values masked whole)
    (re.compile(r'(?i)\b(parola|şifre|sifre|password|passwd|pwd|token|api[_-]?key|secret|anahtar)'
                r'(\s*[:=]\s*|\s+)("[^"]*"|\'[^\']*\'|[^\s,;]+)'), r'\1\2****'),
    (re.compile(r'\b(sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AIza[0-9A-Za-z_-]{20,}|'
                r'xox[abp]-[A-Za-z0-9-]{10,})'), '****'),
]
MASKE = '****'


def maskele(metin):
    """Mask secrets inside one string (non-strings pass through)."""
    if not isinstance(metin, str):
        return metin
    for desen, yerine in _GIZLI:
        metin = desen.sub(yerine, metin)
    return metin


def maskele_nesne(nesne):
    """Recursively mask strings; values under secret-looking keys are replaced whole."""
    if isinstance(nesne, str):
        return maskele(nesne)
    if isinstance(nesne, dict):
        return {maskele(k): (MASKE if isinstance(k, str) and GIZLI_ANAHTAR.match(k) and v not in (None, '')
                             else maskele_nesne(v)) for k, v in nesne.items()}
    if isinstance(nesne, (list, tuple)):
        return [maskele_nesne(x) for x in nesne]
    return nesne
