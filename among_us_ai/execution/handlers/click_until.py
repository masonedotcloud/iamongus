"""
Click ripetuto finche' un check non passa.

Handler per le azioni di tipo: click_until.

Per ogni "punto" della lista, sposta il mouse sul pulsante e clicca
ripetutamente fino a quando un pixel di "check" non assume un colore
chiaro (R>200, G>200, B>200) — segnale che la condizione attesa e'
verificata. Dopo 8 secondi senza progresso passa al punto successivo.

Usato per minigiochi dove il bottone va premuto piu' volte (es. tasti
da spammare in alcune calibrazioni del Distributor).
"""

import time

import pyautogui

def handle_click_until(az, cx, cy, cw, ch, hwnd, is_test):
    """
    Esegue click ripetuto finche' un check pixel non passa.

    Parametri
    ---------
    az : dict
        Deve contenere ``punti``: lista di tuple (cx_rel, cy_rel,
        bx_rel, by_rel) dove (cx, cy) e' il pixel di check e (bx, by)
        e' il bottone da cliccare.
    cx, cy : int
        Origine (top-left) del rect del client del gioco.
    cw, ch : int
        Larghezza e altezza del rect del client.
    hwnd : int
        Handle della finestra del gioco (non usato qui ma passato per
        uniformita').
    is_test : bool
        True se chiamato dal pulsante "Test" dell'editor.
    """
    attesa = az.get("attesa", 0.0)
    for cx_rel, cy_rel, bx_rel, by_rel in az.get('punti', []):
        # Coordinate assolute del check pixel e del pulsante
        chk_x = cx + int(cx_rel * cw)
        chk_y = cy + int(cy_rel * ch)
        btn_x = cx + int(bx_rel * cw)
        btn_y = cy + int(by_rel * ch)

        # Posiziona il mouse sul pulsante
        pyautogui.moveTo(btn_x, btn_y, duration=0.1)

        # Ciclo: clicca finche' il check pixel non e' chiaro o scadono 8s
        start_t = time.time()
        while time.time() - start_t < 8.0:
            try:
                r, g, b = pyautogui.pixel(chk_x, chk_y)
                # Pixel chiaro -> condizione raggiunta -> esci
                if r > 200 and g > 200 and b > 200:
                    break
                # Click rapido (mouseDown + sleep + mouseUp = ~30ms)
                pyautogui.click()
                # Premi il tasto sinistro del mouse
                pyautogui.mouseDown(button='left')
                # Pausa il thread per il tempo specificato (secondi)
                time.sleep(0.03)
                # Rilascia il tasto sinistro del mouse
                pyautogui.mouseUp(button='left')
            except Exception:
                # pyautogui.pixel puo' fallire se il mouse esce dallo schermo
                pass
            # Pausa il thread per il tempo specificato (secondi)
            time.sleep(0.05)

    # Pausa il thread per il tempo specificato (secondi)
    time.sleep(attesa)
