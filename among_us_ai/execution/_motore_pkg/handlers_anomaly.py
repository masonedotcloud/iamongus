"""
Handler per "Detect Anomaly": clicca l'elemento "diverso" dagli altri.
Confronta la "forma pura" di N elementi e clicca quello con la
similarita' minore (= il piu' diverso dalla media).
"""
import time as _time
try:
    import pyautogui as _pag
except Exception:
    _pag = None
from .input_mouse import _extract_pure_shape, _click_hold

def _h_click_anomaly(az, cx, cy, cw, ch, hwnd, durata, attesa):
    """
    Handler ``click_anomaly``: minigioco "Detect Anomaly".

    Strategia: legge il colore di N punti di check, trova quello "piu'
    diverso" (somma delle distanze RGB dagli altri) e clicca il pulsante
    associato.

    Schema di un punto in az['punti']: ``(chk_rx, chk_ry, btn_rx, btn_ry)``;
    se il pulsante non e' specificato (lista lunga 2) si clicca il punto
    di check stesso.
    """
    # Attesa iniziale: il pannello potrebbe avere un'animazione di apertura.
    _time.sleep(1.0)
    chk_pts = [(cx + int(p[0] * cw), cy + int(p[1] * ch))
               for p in az.get('punti', [])]
    btn_pts = []
    for p in az.get('punti', []):
        if len(p) >= 4:
            btn_pts.append((cx + int(p[2] * cw), cy + int(p[3] * ch)))
        else:
            # Legacy: niente pulsante separato -> clicca il check stesso.
            btn_pts.append((cx + int(p[0] * cw), cy + int(p[1] * ch)))
    if len(chk_pts) >= 3:
        # Lettura colori: prima provo con mss (cattura unica della finestra,
        # piu' veloce di N chiamate a pyautogui.pixel). Fallback a pyautogui.
        colori = []
        try:
            import mss as _mss
            import numpy as _np
            with _mss.mss() as sct:
                monitor = {'top': cy, 'left': cx, 'width': cw, 'height': ch}
                sct_img = _np.array(sct.grab(monitor))
                for px, py in chk_pts:
                    y_idx = max(0, min(ch - 1, py - cy))
                    x_idx = max(0, min(cw - 1, px - cx))
                    b, g, r, _ = sct_img[y_idx, x_idx]
                    colori.append((int(r), int(g), int(b)))
        except Exception:
            for px, py in chk_pts:
                try:
                    colori.append(_pag.pixel(px, py))
                except Exception:
                    colori.append((0, 0, 0))

        # Trova il punto "anomalo": quello con la max somma di distanze RGB
        # da tutti gli altri (= il piu' diverso dalla media).
        max_dist = -1
        anomalo_idx = 0
        for i in range(len(colori)):
            dist_sum = 0
            for j in range(len(colori)):
                if i != j:
                    dist_sum += (abs(colori[i][0] - colori[j][0])
                                 + abs(colori[i][1] - colori[j][1])
                                 + abs(colori[i][2] - colori[j][2]))
            if dist_sum > max_dist:
                max_dist = dist_sum
                anomalo_idx = i
        print(f'[Anomalia] Colori: {colori} -> Scelto bottone {anomalo_idx}',
              flush=True)
        _click_hold(btn_pts[anomalo_idx][0], btn_pts[anomalo_idx][1], durata)
    _time.sleep(attesa)


