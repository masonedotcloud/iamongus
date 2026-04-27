"""
Rilevamento del pulsante "Use" in basso a destra del client di Among Us.

Idea
----
Il bot, dopo essere arrivato al target di una task, vorrebbe sapere se
e' davvero nel raggio di interazione. Il segnale "ground truth" del
gioco e' il pulsante "Use" in basso a destra: si ILLUMINA (luminoso)
quando puoi interagire con qualcosa (task, sabotaggio, vent, ...) e
resta GRIGIO/SCURO quando sei fuori raggio.

Il pulsante e' un cerchio con icona personalizzata. Per riconoscerlo
in modo affidabile usiamo una calibrazione manuale fatta una volta
dall'utente:
- l'utente seleziona la ROI (rect rx,ry,rw,rh in coordinate relative
  al client del gioco)
- il sistema misura la **luminosita' media** (mean RGB) della ROI nei
  due stati ("acceso" e "spento") e salva i 2 valori
- a runtime il bot cattura la stessa ROI e confronta la luminosita'
  con i 2 riferimenti: se piu' vicina ad "acceso" -> True, altrimenti
  False

Stato calibrazione
------------------
Salvato in `use_button_calibration.json`:

    {
        "roi": {"rx": 0.93, "ry": 0.85, "rw": 0.07, "rh": 0.12},
        "lit_brightness": 215.4,
        "off_brightness": 80.7,
        "calibrated": true
    }

Default `calibrated=false`: senza calibrazione, `is_lit()` ritorna
sempre `None` (= "non so"). Il bot in quel caso deve procedere
comunque (best-effort).
"""

import json as _json


# Percorso del file di calibrazione (relativo alla cwd del bot).
# In produzione il bot gira con cwd = directory del bot, quindi il
# file finisce nella stessa cartella di mappa_skeld.json e simili.
CALIB_PATH = "use_button_calibration.json"


def _default_calibration():
    """Stato vuoto: nessuna calibrazione fatta."""
    return {
        "roi": {"rx": 0.92, "ry": 0.85, "rw": 0.07, "rh": 0.12},  # default ragionevole
        "lit_brightness": None,
        "off_brightness": None,
        "calibrated": False,
    }


def carica_calibrazione(path=None):
    """
    Carica la calibrazione dal file JSON. Se manca o e' corrotto,
    ritorna i default (calibrated=False).
    """
    p = path or CALIB_PATH
    try:
        with open(p, 'r', encoding='utf-8') as f:
            d = _json.load(f)
        # Validazione campi minimi
        if 'roi' not in d or not isinstance(d.get('roi'), dict):
            return _default_calibration()
        return d
    except (FileNotFoundError, _json.JSONDecodeError, OSError):
        return _default_calibration()


def salva_calibrazione(calib, path=None):
    """Scrive la calibrazione su disco."""
    p = path or CALIB_PATH
    try:
        with open(p, 'w', encoding='utf-8') as f:
            _json.dump(calib, f, indent=2)
        return True
    except OSError as e:
        print(f"[UseButton] Errore salvataggio calibrazione: {e}")
        return False


def cattura_roi_luminosita(client_rect, calib, sct_optional=None):
    """
    Cattura la ROI del pulsante Use dal client del gioco e ritorna
    la luminosita' media (scalare in [0, 255]).

    Parametri
    ---------
    client_rect : tuple(cx, cy, cw, ch)
        Rect del client di Among Us (assoluti rispetto allo schermo).
    calib : dict
        Calibrazione corrente (per leggere la ROI rx,ry,rw,rh).
    sct_optional : mss.mss() ctx
        Se passato, riusa il context invece di crearne uno nuovo
        (piu' veloce in chiamate ripetute).

    Ritorna
    -------
    float | None
        Luminosita' media (RGB mean) oppure None se cattura fallita.
    """
    try:
        import numpy as _np
        import mss as _mss
    except ImportError:
        return None

    cx, cy, cw, ch = client_rect
    roi = calib.get('roi', {})
    rx = float(roi.get('rx', 0.92))
    ry = float(roi.get('ry', 0.85))
    rw = float(roi.get('rw', 0.07))
    rh = float(roi.get('rh', 0.12))

    # Coordinate assolute della ROI sullo schermo
    abs_left = cx + int(rx * cw)
    abs_top = cy + int(ry * ch)
    abs_w = max(1, int(rw * cw))
    abs_h = max(1, int(rh * ch))

    monitor = {'top': abs_top, 'left': abs_left,
               'width': abs_w, 'height': abs_h}

    try:
        if sct_optional is not None:
            img = _np.array(sct_optional.grab(monitor))
        else:
            with _mss.mss() as sct:
                img = _np.array(sct.grab(monitor))
        # img e' BGRA: prendiamo i 3 canali colore e calcoliamo la media
        rgb = img[:, :, :3].astype(_np.float32)
        return float(rgb.mean())
    except Exception as e:
        print(f"[UseButton] Errore cattura ROI: {e}")
        return None


def is_lit(client_rect, calib=None, sct_optional=None):
    """
    Ritorna True/False/None:
      - True  = il pulsante Use sembra ILLUMINATO (puoi interagire)
      - False = il pulsante Use sembra SPENTO (fuori raggio)
      - None  = impossibile determinare (calibrazione mancante o
                cattura fallita) -> il bot dovra' procedere comunque

    Logica:
      1. Se calibrazione mancante (`calibrated=False`) -> None
      2. Cattura luminosita' media della ROI
      3. Confronta con i 2 riferimenti (lit_brightness, off_brightness)
      4. Se piu' vicina ad acceso -> True; altrimenti False
    """
    if calib is None:
        calib = carica_calibrazione()
    if not calib.get('calibrated', False):
        return None
    lit_ref = calib.get('lit_brightness')
    off_ref = calib.get('off_brightness')
    if lit_ref is None or off_ref is None:
        return None

    bright = cattura_roi_luminosita(client_rect, calib, sct_optional)
    if bright is None:
        return None

    # Distanze (in scala lineare)
    d_lit = abs(bright - lit_ref)
    d_off = abs(bright - off_ref)

    # Più vicino al riferimento "acceso" -> True
    return d_lit < d_off
