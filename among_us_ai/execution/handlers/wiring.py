"""
Cablaggio (collega pin sinistri ai destri per colore).

Handler per le azioni di tipo: wiring.

Ogni funzione ha la firma standard:
    handle_<tipo>(az, ctx) -> None

dove ``az`` e' il dict dell'azione e ``ctx`` e' un namespace con i
parametri condivisi (cx, cy, cw, ch del rect del gioco; hwnd; flag
is_test). Le funzioni delegano i movimenti del mouse ai helper di
``_drag_utils.py``.
"""

import time

import pyautogui

def handle_wiring(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Cablaggio: per ogni pin di sinistra, identifica il colore via pyautogui.pixel() e lo collega al pin destro dello stesso colore.

    Parametri
    ---------
    az : dict
        Dizionario dell'azione (chiavi specifiche del tipo).
    cx, cy : int
        Origine (top-left) del rect del client del gioco.
    cw, ch : int
        Larghezza e altezza del rect del client.
    hwnd : int
        Handle della finestra del gioco (per check foreground).
    is_test : bool
        True se chiamato dal pulsante "Test" dell'editor (modalita' verbosa).
    """
    durata = az.get("durata", 0.0)
    attesa = az.get("attesa", 0.0)
    left_pts = az.get('left', [])
    right_pts = az.get('right', [])
    light_pts = az.get('lights', [])
    disp_dx = list(range(len(right_pts)))
    
    for i in range(len(left_pts)):
        start_rx, start_ry = left_pts[i]
        sx = cx + int(start_rx * cw); sy = cy + int(start_ry * ch)
        
        try:
            col_sx = pyautogui.pixel(sx, sy)
        except Exception:
            col_sx = (0, 0, 0)
            
        target_scelti = []
        for r_idx in disp_dx:
            end_rx, end_ry = right_pts[r_idx]
            ex = cx + int(end_rx * cw); ey = cy + int(end_ry * ch)
            try:
                col_dx = pyautogui.pixel(ex, ey)
                diff = abs(col_sx[0]-col_dx[0]) + abs(col_sx[1]-col_dx[1]) + abs(col_sx[2]-col_dx[2])
            except Exception:
                col_dx = (0, 0, 0)
                diff = 999
            target_scelti.append((diff, r_idx))
            print(f"[Wiring] Cavo sx {i} {col_sx} vs Target dx {r_idx} {col_dx} -> diff: {diff}")
        target_scelti.sort(key=lambda item: item[0])
        ordine_tentativi = [t[1] for t in target_scelti]
        
        # Sposta il mouse alla posizione
        pyautogui.moveTo(sx, sy, duration=0.15)
        # Premi il tasto sinistro del mouse
        pyautogui.mouseDown(button='left')
        # Pausa il thread per il tempo specificato (secondi)
        time.sleep(0.1)
        for r_idx in ordine_tentativi:
            end_rx, end_ry = right_pts[r_idx]
            ex = cx + int(end_rx * cw); ey = cy + int(end_ry * ch)
            light_rx, light_ry = light_pts[r_idx]
            lx = cx + int(light_rx * cw); ly = cy + int(light_ry * ch)
            # Sposta il mouse alla posizione
            pyautogui.moveTo(ex, ey, duration=0.25)
            # Pausa il thread per il tempo specificato (secondi)
            time.sleep(0.1)
            try:
                r, g, b = pyautogui.pixel(lx, ly)
                if r > 160 and g > 150 and b < 100:
                    disp_dx.remove(r_idx)
                    break
            except Exception:
                pass
        # Rilascia il tasto sinistro del mouse
        pyautogui.mouseUp(button='left')
        # Pausa il thread per il tempo specificato (secondi)
        time.sleep(attesa)



