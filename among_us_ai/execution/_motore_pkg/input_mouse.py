"""
Helper di input mouse: click, drag con movimenti "umani" (Bezier + jitter).

Dipende da pyautogui (mouseDown/mouseUp/moveTo). Tutte le funzioni
controllano `_OK` per gestire l'assenza di pyautogui.
"""
import math as _math
import random as _random
import time as _time

try:
    import pyautogui as _pag
    _pag.FAILSAFE = True
    _pag.PAUSE = 0
    _OK = True
except Exception as _e:
    print(f"[InputMouse] pyautogui mancante: {_e}")
    _pag = None
    _OK = False

def _click_hold(x, y, durata):
    # Click in (x, y) con eventuale "hold" del tasto sinistro.
    # durata=0  -> click istantaneo (mouseDown+mouseUp immediato)
    # durata>0  -> tieni premuto per `durata` secondi prima di rilasciare
    _pag.moveTo(x, y, duration=0.1)
    if durata > 0:
        _pag.mouseDown(); _time.sleep(durata); _pag.mouseUp()
    else:
        _pag.click()


def _drag_umano(sx, sy, ex, ey, durata):
    # Drag "umano" dal punto (sx, sy) al punto (ex, ey) in `durata` secondi.
    # NON e' una linea retta: usa una curva di Bezier quadratica con un
    # punto di controllo offset random, per simulare il movimento naturale
    # della mano. Il timing usa easeInOutSine per accelerare/decelerare.
    #
    # Reattivita' a STOP: se il bot principale richiede stop durante il
    # drag (es. RAM segnala fase completata), interrompiamo subito,
    # rilasciamo il mouse pulito ed usciamo.
    from . import stop_flag as _stop_flag
    #
    # 1) Move to start con tween easeOutQuad
    _pag.moveTo(sx, sy, duration=_random.uniform(0.15, 0.25),
                tween=_pag.easeOutQuad)
    # 2) Press del tasto sinistro
    _pag.mouseDown(button='left')
    # 3) Micro-pausa per dare al gioco il tempo di registrare il press
    _time.sleep(_random.uniform(0.05, 0.1))
    if durata > 0:
        # 4) Calcola N step in funzione della durata (60 fps target)
        steps = max(10, int(durata * 60)); st = durata / steps
        # 5) Punto di controllo della Bezier: midpoint + offset random
        #    L'offset e' generoso (-40, +40 px) per produrre archi
        #    abbastanza visibili e quindi "umani"
        off = _random.randint(-40, 40)
        mx = (sx + ex) / 2 + off; my = (sy + ey) / 2 + off
        # 6) Loop di interpolazione: t in [0,1], te e' la versione con
        #    easing (easeInOutSine) per accelerare/decelerare
        for i in range(1, steps + 1):
            # Interruzione richiesta dal main? Esci dalla curva.
            if _stop_flag.is_stop_requested():
                break
            t = i / steps; te = -(_math.cos(_math.pi * t) - 1) / 2
            # Equazione Bezier quadratica: B(t) = (1-t)^2*P0 + 2(1-t)t*P1 + t^2*P2
            _pag.moveTo(int((1-te)**2*sx + 2*(1-te)*te*mx + te**2*ex),
                        int((1-te)**2*sy + 2*(1-te)*te*my + te**2*ey))
            _time.sleep(st)
        # 7) Snap finale al punto target esatto (la curva potrebbe
        #    arrotondare a 1 px di distanza). Skip se stop richiesto:
        #    il punto attuale va bene, non vogliamo "completare" il drag
        #    ad un target che il gioco ha gia' considerato risolto.
        if not _stop_flag.is_stop_requested():
            _pag.moveTo(ex, ey)
    else:
        # Drag istantaneo: niente Bezier, vai dritto al target
        _pag.moveTo(ex, ey)
    # 8) Micro-pausa pre-rilascio per simulare reazione umana
    _time.sleep(_random.uniform(0.05, 0.15))
    # 9) Release del tasto sinistro (sempre, anche se stop: serve per
    #    non lasciare il mouse con il tasto premuto -> bug del gioco)
    _pag.mouseUp(button='left')


def _drag_snap(sx, sy, ex, ey, durata):
    """
    Drag "SNAP" istantaneo, ottimizzato per afferrare oggetti animati.

    Differenze rispetto a `_drag_umano`:
      1. NESSUN tween nel move-to-start: snap IMMEDIATO su (sx, sy).
         Cosi' la foglia/oggetto NON ha tempo di muoversi per le sue
         animazioni prima che il bot la afferri.
      2. Pausa post-mouseDown piu' generosa (180ms): il gioco ha tempo
         di registrare "afferra".
      3. Movimento in linea retta (no Bezier curva ampia): il gioco
         non perde l'oggetto.
      4. Snap finale al target.
      5. Pausa pre-mouseUp piu' lunga (150ms): "rilascia qui".

    Da usare per:
      - yolo_drag_all (foglie O2 Filter)
      - tutte le task dove l'oggetto e' animato/mobile

    NON usare per drag con curva naturale (es. wiring): usare _drag_umano
    o _drag_multi.
    """
    from . import stop_flag as _stop_flag

    # 1) SNAP immediato sulla posizione (no tween)
    _pag.moveTo(sx, sy)
    # 2) Pausa minima per assicurare che il move sia "registrato"
    _time.sleep(0.02)
    # 3) Press del tasto sinistro
    _pag.mouseDown(button='left')
    # 4) Pausa GENEROSA post-press: il gioco capisce "afferro l'oggetto"
    #    e lo "incolla" al cursore. Senza questo, il drag successivo
    #    afferra solo "aria".
    _time.sleep(_random.uniform(0.15, 0.20))

    if durata > 0:
        # 5) Linea retta dal punto iniziale al target con N step
        steps = max(8, int(durata * 50))
        st = durata / steps
        for i in range(1, steps + 1):
            if _stop_flag.is_stop_requested():
                break
            t = i / steps
            mx = int(sx + (ex - sx) * t)
            my = int(sy + (ey - sy) * t)
            _pag.moveTo(mx, my)
            _time.sleep(st)
        # 6) Snap finale al target esatto
        if not _stop_flag.is_stop_requested():
            _pag.moveTo(ex, ey)
    else:
        _pag.moveTo(ex, ey)

    # 7) Pausa GENEROSA pre-release: "rilascia qui"
    _time.sleep(_random.uniform(0.15, 0.20))
    # 8) Release
    _pag.mouseUp(button='left')


def _drag_multi(punti_abs, durata_totale):
    # Drag che passa per N punti in sequenza, in tempo `durata_totale`.
    # Usato per minigiochi tipo "drag in poligono" dove il giocatore
    # deve seguire un percorso prestabilito (es. wiring complesso).
    # Ogni segmento riceve un tempo proporzionale alla sua lunghezza.
    from . import stop_flag as _stop_flag
    if len(punti_abs) < 2:
        # Non si puo' fare drag con < 2 punti
        return
    # 1) Move to first point + press
    sx, sy = punti_abs[0]
    _pag.moveTo(sx, sy, duration=_random.uniform(0.15, 0.25),
                tween=_pag.easeOutQuad)
    _pag.mouseDown(button='left')
    _time.sleep(_random.uniform(0.05, 0.1))
    # 2) Calcola lunghezza totale del percorso
    total = sum(_math.hypot(punti_abs[i+1][0]-punti_abs[i][0],
                             punti_abs[i+1][1]-punti_abs[i][1])
                for i in range(len(punti_abs)-1))
    if total <= 0:
        # Tutti i punti coincidono: rilascia subito
        _pag.mouseUp(button='left'); return
    # 3) Per ogni segmento, traccia una Bezier quadratica (come _drag_umano)
    for i in range(len(punti_abs)-1):
        # Stop richiesto fra segmenti? Esci pulito.
        if _stop_flag.is_stop_requested():
            break
        ax, ay = punti_abs[i]; bx, by = punti_abs[i+1]
        seg = _math.hypot(bx-ax, by-ay)
        # Tempo proporzionale alla lunghezza del segmento sul totale
        dur_seg = max(0.05, durata_totale * (seg/total))
        # Step in base alla durata (60 fps target)
        steps = max(6, int(dur_seg * 60)); st = dur_seg / steps
        # Punto di controllo offset minimo (-3, +3 px) per non
        # deviare troppo dal percorso desiderato del minigioco
        off = _random.randint(-3, 3)
        mx = (ax+bx)/2+off; my = (ay+by)/2+off
        for k in range(1, steps+1):
            if _stop_flag.is_stop_requested():
                break
            t = k/steps; te = -(_math.cos(_math.pi*t)-1)/2
            _pag.moveTo(int((1-te)**2*ax + 2*(1-te)*te*mx + te**2*bx),
                        int((1-te)**2*ay + 2*(1-te)*te*my + te**2*by))
            _time.sleep(st)
        # Snap a fine segmento (skip se stop)
        if not _stop_flag.is_stop_requested():
            _pag.moveTo(bx, by)
    # 4) Micro-pausa + release (sempre)
    _time.sleep(_random.uniform(0.05, 0.15))
    _pag.mouseUp(button='left')


def _drag_seq_tappe(punti_abs, durata_segmento):
    # Drag a "tappe" tra N punti: tra una tappa e l'altra usa il
    # tween di pyautogui (easeInOutQuad) invece della Bezier.
    # Piu' rigido di `_drag_multi` ma piu' preciso per minigiochi che
    # richiedono di passare ESATTAMENTE per i punti (es. wiring sequenziale).
    from . import stop_flag as _stop_flag
    if len(punti_abs) < 2:
        return
    # Move to start + press
    sx, sy = punti_abs[0]
    _pag.moveTo(sx, sy, duration=_random.uniform(0.15, 0.25), tween=_pag.easeOutQuad)
    _pag.mouseDown(button='left')
    _time.sleep(_random.uniform(0.05, 0.1))

    # Durata per segmento (minimo 250ms per dare tempo al gioco di reagire)
    dur_seg = max(0.25, durata_segmento)
    for i in range(1, len(punti_abs)):
        if _stop_flag.is_stop_requested():
            break
        bx, by = punti_abs[i]
        # Tween di pyautogui per movimento smooth fra le tappe
        _pag.moveTo(bx, by, duration=dur_seg, tween=_pag.easeInOutQuad)
        # Pausa breve a ogni tappa (il minigioco potrebbe dover registrare)
        _time.sleep(0.15)

    # Micro-pausa + release
    _time.sleep(_random.uniform(0.05, 0.15))
    _pag.mouseUp(button='left')


def _drag_e_tieni(sx, sy, ex, ey, durata, hold):
    # Drag normale + hold finale del tasto premuto.
    # Usato per minigiochi che richiedono di "tenere premuto al target"
    # come le leve di Reactor.
    _drag_umano(sx, sy, ex, ey, durata)
    if hold > 0:
        # NB: _drag_umano fa giA' mouseUp. Qui rifacciamo down/up
        # per il tempo di hold extra (in pratica il gioco vede
        # un secondo press dopo il primo release).
        _pag.mouseDown(); _time.sleep(hold); _pag.mouseUp()


def _extract_pure_shape(roi_image):
    # Estrae la "forma pura" da un'immagine ROI (Region Of Interest).
    # Usata dai minigiochi tipo `click_anomaly` (Detect Anomaly) e
    # `simon_says` per confrontare due immagini ignorando posizione,
    # dimensione e antialiasing.
    #
    # Pipeline:
    #   1) Converti in grayscale
    #   2) Threshold (binarizza: nero/bianco)
    #   3) Trova bbox dei pixel non-bianchi
    #   4) Centra la forma in un quadrato (padding nero)
    #   5) Resize a 40x40 + leggero blur per smoothing
    import cv2
    import numpy as np
    # 1) Grayscale (gestisce sia BGRA che BGR)
    gray = cv2.cvtColor(roi_image, cv2.COLOR_BGRA2GRAY) if roi_image.shape[2] == 4 else cv2.cvtColor(roi_image, cv2.COLOR_BGR2GRAY)
    # 2) Threshold inverso: pixel scuri (< 120) -> bianco (255), altri -> nero (0)
    _, thresh = cv2.threshold(gray, 120, 255, cv2.THRESH_BINARY_INV)
    # 3) Bounding box dei pixel "accesi"
    points = cv2.findNonZero(thresh)
    if points is not None:
        tx, ty, tw, th = cv2.boundingRect(points)
        # 4a) Crop al bbox
        cropped = thresh[ty:ty+th, tx:tx+tw]
        # 4b) Padding per renderlo quadrato (la forma resta centrata)
        size = max(tw, th)
        top = (size - th) // 2
        bottom = size - th - top
        left = (size - tw) // 2
        right = size - tw - left
        square = cv2.copyMakeBorder(cropped, top, bottom, left, right, cv2.BORDER_CONSTANT, value=0)
        # 5a) Resize a 40x40 con interpolazione AREA (qualita' ottimale per shrinking)
        res = cv2.resize(square, (40, 40), interpolation=cv2.INTER_AREA)
    else:
        # Fallback: nessun pixel acceso, resize diretto
        res = cv2.resize(thresh, (40, 40))
    # 5b) Leggero blur per ammorbidire jitter di antialiasing
    return cv2.GaussianBlur(res, (3, 3), 0)


