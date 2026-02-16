"""
Handler per "Simon Says".

Il gioco mostra una sequenza di pulsanti che si illuminano, poi il
giocatore deve riprodurla. Il bot legge la sequenza tramite analisi
colore frame-per-frame e poi clicca i pulsanti nello stesso ordine.
"""
import time as _time
try:
    import pyautogui as _pag
except Exception:
    _pag = None
from .input_mouse import _click_hold

def _h_simon_says(az, cx, cy, cw, ch, hwnd, durata, attesa):
    import mss as _mss
    import numpy as _np
    disp_pts = [(cx + int(p[0] * cw), cy + int(p[1] * ch)) for p in az['display']]
    keyp_pts = [(cx + int(p[0] * cw), cy + int(p[1] * ch)) for p in az['keypad']]
    with _mss.mss() as sct:
        monitor = {'top': cy, 'left': cx, 'width': cw, 'height': ch}
        base_img = _np.array(sct.grab(monitor))
        base_colors = [base_img[p[1] - cy, p[0] - cx, :3] for p in disp_pts]
        for rnd in range(1, 6):
            sequence = []
            last_lit = -1
            start_t = _time.time()
            while len(sequence) < rnd and _time.time() - start_t < 10.0:
                img = _np.array(sct.grab(monitor))
                lit_now = -1
                for i, (dx, dy) in enumerate(disp_pts):
                    px_col = img[dy - cy, dx - cx, :3]
                    bc = base_colors[i]
                    diff = abs(int(px_col[0]) - int(bc[0])) + abs(int(px_col[1]) - int(bc[1])) + abs(int(px_col[2]) - int(bc[2]))
                    if diff > 50:
                        lit_now = i
                        break
                if lit_now != -1:
                    if lit_now != last_lit:
                        sequence.append(lit_now)
                        last_lit = lit_now
                        start_t = _time.time()
                        _time.sleep(0.15)
                else:
                    last_lit = -1
                    _time.sleep(0.02)
            if len(sequence) == 0:
                break
            _time.sleep(0.4)
            for idx in sequence:
                kx, ky = keyp_pts[idx]
                _click_hold(kx, ky, durata)
                _time.sleep(0.05)
    _time.sleep(attesa)


