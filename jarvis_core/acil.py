"""Global emergency-stop hotkey (works even when JARVIS is not focused).
Optional: needs the 'keyboard' package; on Windows it works without admin."""
import os

KISAYOL = os.getenv('JARVIS_ACIL_KISAYOL', 'ctrl+alt+end')


def acil_durdurma_kur(iptal_fonksiyonu):
    try:
        import keyboard
        keyboard.add_hotkey(KISAYOL, iptal_fonksiyonu)
        return KISAYOL
    except Exception:
        # Not installed, or no permission (Linux needs root): the CLI still has "dur" / Ctrl+C.
        return None
