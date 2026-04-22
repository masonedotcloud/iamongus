"""
Handler per il minigioco "Fix Wiring".

4 fili a sinistra, 4 connettori a destra, 4 luci-indicatore.
Il bot legge il colore del filo a sinistra (`pyautogui.pixel`),
lo trascina sul connettore destro dello stesso colore.
"""
import time as _time
try:
    import pyautogui as _pag
except Exception:
    _pag = None

def _h_wiring(az, cx, cy, cw, ch, hwnd, durata, attesa):
    """
    Handler ``wiring``: minigioco "Fix Wiring".

    4 cavi a sinistra, 4 connettori a destra, 4 luci-indicatore.
    Strategia:
      1. Per ogni cavo (left[i]) leggi il colore via ``pyautogui.pixel``
      2. Ordina i connettori destri per somiglianza di colore (delta RGB minimo)
      3. Tieni premuto sul cavo, prova ogni connettore in ordine di
         somiglianza; quando la luce associata si accende (R>160, G>150, B<100
         = colore "giallo conferma"), rimuovi il connettore dai candidati
         e passa al cavo successivo.
    """
    left_pts = az.get('left', [])
    right_pts = az.get('right', [])
    light_pts = az.get('lights', [])
    # Indici dei connettori dx ancora disponibili (rimossi mano a mano).
    disp_dx = list(range(len(right_pts)))

    for i in range(len(left_pts)):
        start_rx, start_ry = left_pts[i]
        sx = cx + int(start_rx * cw)
        sy = cy + int(start_ry * ch)
        # Leggi il colore del cavo sinistro per matching.
        try:
            col_sx = _pag.pixel(sx, sy)
        except Exception:
            col_sx = (0, 0, 0)

        # Ordina i connettori destri disponibili per somiglianza di colore.
        target_scelti = []
        for r_idx in list(disp_dx):
            end_rx, end_ry = right_pts[r_idx]
            ex = cx + int(end_rx * cw)
            ey = cy + int(end_ry * ch)
            try:
                col_dx = _pag.pixel(ex, ey)
                diff = (abs(col_sx[0] - col_dx[0])
                        + abs(col_sx[1] - col_dx[1])
                        + abs(col_sx[2] - col_dx[2]))
            except Exception:
                col_dx = (0, 0, 0)
                diff = 999  # match impossibile: lo lascio per ultimo
            target_scelti.append((diff, r_idx))
            print(f'[Wiring] Cavo sx {i} {col_sx} vs Target dx {r_idx} '
                  f'{col_dx} -> diff: {diff}')
        target_scelti.sort(key=lambda item: item[0])
        ordine_tentativi = [t[1] for t in target_scelti]

        # Press del tasto sinistro sul cavo, poi cicla i connettori
        # in ordine di somiglianza fino a trovare quello giusto.
        _pag.moveTo(sx, sy, duration=0.15)
        _pag.mouseDown(button='left')
        _time.sleep(0.1)
        for r_idx in ordine_tentativi:
            end_rx, end_ry = right_pts[r_idx]
            ex = cx + int(end_rx * cw)
            ey = cy + int(end_ry * ch)
            light_rx, light_ry = light_pts[r_idx]
            lx = cx + int(light_rx * cw)
            ly = cy + int(light_ry * ch)
            _pag.moveTo(ex, ey, duration=0.25)
            _time.sleep(0.1)
            try:
                # Luce gialla = conferma del gioco "match corretto".
                r, g, b = _pag.pixel(lx, ly)
                if r > 160 and g > 150 and (b < 100):
                    disp_dx.remove(r_idx)
                    break
            except Exception:
                pass
        _pag.mouseUp(button='left')
        _time.sleep(attesa)


