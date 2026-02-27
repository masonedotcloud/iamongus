"""
Dispatcher principale: prende una lista di azioni e le esegue una per una.

Macro-passi:
  1. Suddivide le azioni in CHUNK separati dai cooldown.
  2. Sceglie il chunk da eseguire (current_step), o tutto in test mode.
  3. Per ogni azione: focus check + rect read + dispatch via _DISPATCH_MAP.
"""
import time as _time
try:
    import win32gui as _win32gui
except Exception:
    _win32gui = None

from .geometria import _client_rect
# `_OK` indica se pyautogui e' disponibile. Definito in input_mouse
# (dove viene caricato pyautogui). Lo importiamo qui per il check
# all'inizio di esegui_azioni.
from .input_mouse import _OK

# Import handler per popolare il DISPATCH_MAP. Questi import non sono
# usati direttamente ma servono per registrare le funzioni nel dict.
from .handlers_clicks   import _h_click, _h_click_rect, _h_click_poly, _h_click_until
from .handlers_drags    import _h_drag, _h_drag_multi, _h_drag_zone, _h_drag_hold
from .handlers_wiring   import _h_wiring
from .handlers_sync     import _h_sync_click
from .handlers_anomaly  import _h_click_anomaly
from .handlers_yolo     import (_h_yolo_drag, _h_yolo_drag_all,
                                _h_yolo_click, _h_yolo_click_all,
                                _h_yolo_drag_seq)
from .handlers_simon    import _h_simon_says
from .handlers_ocr      import _h_number_match, _h_ocr_keypad

# DISPATCH MAP: tipo di azione -> funzione handler
# Aggiungere un nuovo tipo: scrivi `_h_<tipo>` nel modulo handlers_*
# appropriato e registralo qui.
_DISPATCH_MAP = {
    'click':          _h_click,
    'click_rect':     _h_click_rect,
    'click_poly':     _h_click_poly,
    'click_until':    _h_click_until,
    'drag':           _h_drag,
    'drag_multi':     _h_drag_multi,
    'drag_zone':      _h_drag_zone,
    'drag_hold':      _h_drag_hold,
    'wiring':         _h_wiring,
    'sync_click':     _h_sync_click,
    'click_anomaly':  _h_click_anomaly,
    'yolo_drag':      _h_yolo_drag,
    'yolo_drag_all':  _h_yolo_drag_all,
    'yolo_click':     _h_yolo_click,
    'yolo_click_all': _h_yolo_click_all,
    'yolo_drag_seq':  _h_yolo_drag_seq,
    'simon_says':     _h_simon_says,
    'number_match':   _h_number_match,
    'ocr_keypad':     _h_ocr_keypad,
}

def esegui_azioni(azioni, hwnd, current_step=0, is_test=False):
    # =========================================================================
    # DISPATCHER PRINCIPALE
    # =========================================================================
    # Esegue una lista di azioni nel gioco. Macro-passi:
    #   1) Suddivide le azioni in CHUNK separati dai cooldown
    #   2) Sceglie il chunk da eseguire (current_step), tutto se test
    #   3) Per ogni azione:
    #      - aspetta che il gioco sia in primo piano
    #      - legge il rect del client
    #      - delega all'handler in _DISPATCH_MAP[tipo]
    # Parametri:
    #   azioni        list[dict]
    #   hwnd          handle finestra del gioco
    #   current_step  int (chunk_id da eseguire)
    #   is_test       True se chiamato dall'editor
    # =========================================================================
    if not _OK:
        return False

    # --- 1) SPLIT IN CHUNKS ---
    chunks = []
    current_chunk = []
    cooldowns = []
    for az in azioni:
        if az.get('tipo') == 'cooldown':
            chunks.append(current_chunk)
            cooldowns.append(az.get('durata', 0.0))
            current_chunk = []
        else:
            current_chunk.append(az)
    chunks.append(current_chunk)

    # Clamp del current_step entro i limiti validi
    if current_step >= len(chunks):
        current_step = max(0, len(chunks) - 1)

    # In TEST tutto, in PRODUZIONE solo il chunk corrente
    azioni_da_eseguire = chunks[current_step] if not is_test else azioni

    # --- 2) LOOP PRINCIPALE: dispatch per ogni azione ---
    for az in azioni_da_eseguire:
        # 2a) Aspetta che il gioco sia in primo piano
        if _win32gui and hwnd and _win32gui.GetForegroundWindow() != hwnd:
            print("[Task] Gioco non in primo piano, in pausa...", flush=True)
            while _win32gui.GetForegroundWindow() != hwnd:
                _time.sleep(0.5)
            _time.sleep(0.3)

        # 2b) Leggi il rect del client del gioco
        rect = _client_rect(hwnd)
        if not rect:
            return False
        cx, cy, cw, ch = rect
        tipo   = az.get('tipo')
        durata = az.get('durata', 0.0)
        attesa = az.get('attesa', 0.0)

        # COOLDOWN: caso speciale, non passa al dispatcher
        if tipo == 'cooldown':
            if is_test:
                print(f"[Test] Attesa cooldown di {durata}s...")
                _time.sleep(durata)
            continue

        # 2c) Dispatch all'handler. Se il tipo non e' nel dizionario,
        #     stampiamo un warning ma andiamo avanti (non bloccante).
        handler = _DISPATCH_MAP.get(tipo)
        if handler is None:
            print(f"[esegui_azioni] tipo sconosciuto: {tipo}")
            continue
        handler(az, cx, cy, cw, ch, hwnd, durata, attesa)

        # 2d) Pausa post-azione (campo "attesa" del JSON).
        # Questo sleep e' GENERALE: si applica a tutti i tipi di azione.
        # Alcuni handler (wiring, yolo, ocr, ecc.) hanno gia' un loro
        # _time.sleep(attesa) interno per timing piu' precisi del minigioco;
        # in quei casi il timing totale fra azioni risulta circa 2*attesa,
        # comportamento volutamente preservato dal monolite originale.
        _time.sleep(attesa)

    # --- 3) STAMPA COOLDOWN POST-CHUNK ---
    # Dopo ogni chunk eseguito (in modalita' non-test), stampa la durata
    # del cooldown sul prossimo step. Il subprocess runner del TaskManager
    # intercetta questa riga di stdout e mette in pausa il bot per quel
    # tempo prima di lanciare il prossimo step della task.
    if not is_test and current_step < len(cooldowns):
        print(f"__COOLDOWN__:{cooldowns[current_step]}", flush=True)

    # --- 4) RITORNO ---
    # Tutte le azioni del chunk sono state eseguite senza eccezioni
    # bloccanti -> esecuzione conclusa con successo.
    # NB: senza questo return esplicito, Python ritornerebbe None e il
    # lifecycle interpreterebbe il task come "fallito" (exit code 1),
    # causando un falso errore.
    return True


