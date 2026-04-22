"""
Funzioni helper per simulare trascinamenti del mouse in modo umano.

Sono primitive di basso livello usate dagli handler di azione (click,
drag, wiring, yolo, ...). Ogni handler le compone per realizzare la
specifica logica della propria categoria.
"""

import math
import random
import time

import pyautogui


def trascinamento_umano(sx, sy, ex, ey, durata):
    """
    Simula un drag con movimento "umano": parte dal punto (sx, sy),
    traccia una curva di Bezier verso (ex, ey) con jitter laterale,
    e impiega circa ``durata`` secondi.

    Il movimento *non* e' una linea retta: c'e' un offset perpendicolare
    randomizzato che produce una curvatura leggera. Inoltre la velocita'
    non e' costante (usa ``easeOutQuad``). Cosi' il sistema anti-bot del
    gioco vede un pattern simile a quello umano.
    """
    # Fase 1: muovi il mouse al punto di partenza con easing
    pyautogui.moveTo(sx, sy, duration=random.uniform(0.15, 0.25),
                     tween=pyautogui.easeOutQuad)
    # Fase 2: premi il tasto sinistro e attendi un attimo (umano: non
    # rilascia subito)
    pyautogui.mouseDown(button='left')
    time.sleep(random.uniform(0.05, 0.1))

    if durata > 0:
        # Numero di step interpolati: 60 step/sec
        steps = max(10, int(durata * 60))
        sleep_time = durata / steps
        # Offset perpendicolare: introduce curvatura pseudo-umana
        offset_dist = random.randint(-40, 40)
        # Direzione perpendicolare al segmento sx,sy -> ex,ey
        dx, dy = ex - sx, ey - sy
        length = math.hypot(dx, dy) or 1.0
        # Vettore unitario perpendicolare (90 gradi)
        nx, ny = -dy / length, dx / length

        # Interpolazione step-by-step
        for i in range(steps + 1):
            t = i / steps
            # Lerp lineare lungo il segmento
            x = sx + dx * t
            y = sy + dy * t
            # Aggiungi curvatura: massima al centro (sin(pi*t)), zero
            # agli estremi
            curvature = math.sin(math.pi * t) * offset_dist
            x += nx * curvature
            y += ny * curvature
            # Jitter random (1-2 px) per simulare imprecisione umana
            x += random.uniform(-1, 1)
            y += random.uniform(-1, 1)
            pyautogui.moveTo(int(x), int(y))
            time.sleep(sleep_time)

    # Fase 3: rilascia il tasto
    pyautogui.mouseUp(button='left')


def trascinamento_multi(punti, durata_totale):
    """
    Esegue un drag che visita una sequenza di ``punti`` in ordine,
    senza rilasciare il tasto sinistro fra un punto e l'altro.

    Usato ad esempio per trascinare gli asteroidi: fra una freccia e
    l'altra il mouse non si stacca, segue una traiettoria continua.
    """
    if not punti or len(punti) < 2:
        return

    # Tempo per segmento: distribuito proporzionalmente alla distanza
    distanze = []
    for i in range(len(punti) - 1):
        x1, y1 = punti[i]
        x2, y2 = punti[i + 1]
        distanze.append(math.hypot(x2 - x1, y2 - y1))
    tot_dist = sum(distanze) or 1.0

    sx, sy = punti[0]
    pyautogui.moveTo(sx, sy, duration=0.2, tween=pyautogui.easeOutQuad)
    pyautogui.mouseDown(button='left')
    time.sleep(random.uniform(0.05, 0.1))

    # Per ogni segmento esegue un piccolo drag interno
    for i in range(len(punti) - 1):
        x1, y1 = punti[i]
        x2, y2 = punti[i + 1]
        # Durata proporzionale alla lunghezza del segmento
        seg_durata = (distanze[i] / tot_dist) * durata_totale
        steps = max(8, int(seg_durata * 60))
        sleep_time = seg_durata / steps if steps > 0 else 0
        for s in range(steps + 1):
            t = s / steps
            x = x1 + (x2 - x1) * t
            y = y1 + (y2 - y1) * t
            x += random.uniform(-1, 1)
            y += random.uniform(-1, 1)
            pyautogui.moveTo(int(x), int(y))
            time.sleep(sleep_time)
    pyautogui.mouseUp(button='left')


def esegui_click_hold(x, y, durata):
    """
    Esegue un click in ``(x, y)`` mantenendo il tasto premuto per
    ``durata`` secondi (utile per pulsanti che richiedono una pressione
    prolungata, es. il bottone "Hold" di Reactor).
    """
    pyautogui.moveTo(x, y, duration=random.uniform(0.1, 0.2),
                     tween=pyautogui.easeOutQuad)
    pyautogui.mouseDown(button='left')
    time.sleep(durata)
    pyautogui.mouseUp(button='left')


def trascinamento_e_tieni(sx, sy, ex, ey, durata, hold_at_end):
    """
    Drag da (sx, sy) a (ex, ey) e poi MANTIENE il tasto premuto per
    ``hold_at_end`` secondi prima di rilasciare.

    Usato in alcuni minigiochi dove il giocatore deve trascinare
    qualcosa fino a una posizione e poi tenerla ferma (es. allineamenti
    di Engine Output, calibrazione del Distributor).
    """
    pyautogui.moveTo(sx, sy, duration=random.uniform(0.15, 0.25),
                     tween=pyautogui.easeOutQuad)
    pyautogui.mouseDown(button='left')
    time.sleep(random.uniform(0.05, 0.1))

    if durata > 0:
        steps = max(10, int(durata * 60))
        sleep_time = durata / steps
        for i in range(steps + 1):
            t = i / steps
            x = sx + (ex - sx) * t + random.uniform(-1, 1)
            y = sy + (ey - sy) * t + random.uniform(-1, 1)
            pyautogui.moveTo(int(x), int(y))
            time.sleep(sleep_time)

    # MANTIENE il tasto premuto sull'ultimo punto
    time.sleep(hold_at_end)
    pyautogui.mouseUp(button='left')


def trascinamento_seq_tappe(tappe, durata_per_tappa):
    """
    Variante di ``trascinamento_multi`` dove ogni tappa ha un proprio
    rilascio e ripresa del tasto.

    Usato quando ogni "punto della sequenza" rappresenta un click
    separato (es. wiring multi-step) e non un drag continuo.
    """
    for sx, sy, ex, ey in tappe:
        trascinamento_umano(sx, sy, ex, ey, durata_per_tappa)
        time.sleep(random.uniform(0.1, 0.2))
