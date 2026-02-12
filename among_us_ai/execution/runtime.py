"""
Motore di esecuzione delle azioni registrate (runtime).

Eseguito quando l'utente clicca "Test" nell'editor: preme/trascina il
mouse sulla finestra di Among Us, eseguendo la sequenza di azioni di
una task in modo umano (movimenti Bezier con jitter, durate
randomizzate).

Lo stesso motore in versione INLINE e' anche embedded nel template
``task_template.txt`` per i file ``.py`` generati nei ``tasks_exec/``.
Le due implementazioni convivono apposta:

- Questo modulo dipende dalla dashboard (usa import diretti dal package
  ``among_us_ai``).
- Il template e' autonomo (re-importa al bisogno), eseguibile come
  script Python standalone.

Tutte le funzioni assumono che l'ambiente Windows (mss, win32gui,
pyautogui, cv2, numpy) sia inizializzato — vedi ``core.win_deps``.

Architettura del file
---------------------
Il file e' un dispatcher snello, organizzato in 4 funzioni piccole:

- ``_extract_pure_shape(az)``   -> 20 righe (helper di rendering editor)
- ``_split_in_chunks(azioni)``  -> 15 righe (suddivide su cooldown)
- ``_attendi_focus(hwnd, ...)`` -> 12 righe (aspetta che il gioco sia attivo)
- ``esegui_azioni(...)``         -> 30 righe (entry point + dispatch loop)

La logica specifica di ogni famiglia di azioni (click, drag, wiring,
yolo, ecc.) e' nei file ``handlers/<famiglia>.py``. Il dispatcher si
limita a chiamare il handler giusto via ``DISPATCH_MAP``.
"""

import time

import win32gui

from ..core.geometry import get_client_rect
from ..core.win_deps import WIN_OK as _WIN_OK
from ..core import stop_flag
from .handlers import DISPATCH_MAP

# Ri-export delle funzioni helper di drag/click cosi' i mixin
# dell'editor (es. EditorSaveTestMixin) possono importarle da qui
# senza conoscere la struttura interna degli handlers.
from ._drag_utils import (
    trascinamento_umano,
    trascinamento_multi,
    esegui_click_hold,
    trascinamento_e_tieni,
    trascinamento_seq_tappe,
)


# =============================================================================
# Helper: estrae la "forma pura" di un'azione (per rendering editor)
# =============================================================================

# Mapping: per ogni tipo di azione, quali campi sono "geometrici"
# (posizioni, poligoni, zone) e vanno mantenuti per il rendering.
_FORMA_FIELDS = {
    'click':       ('rx', 'ry'),
    'drag':        ('start_rx', 'start_ry', 'end_rx', 'end_ry'),
    'drag_hold':   ('start_rx', 'start_ry', 'end_rx', 'end_ry'),
    'click_poly':  ('punti', 'rect'),
    'click_rect':  ('punti', 'rect'),
    'drag_multi':  ('punti', 'rect'),
    'drag_zone':   ('zone_a', 'zone_b'),
}


def _extract_pure_shape(az):
    """
    Estrae la "forma pura" di un'azione per il rendering nell'editor.

    Per le azioni che hanno punti (poligono, rettangolo, drag), ritorna
    un dict con solo le coordinate, senza durate/attese/parametri.
    Usato dall'editor per mostrare graficamente il path di un'azione
    senza dover capire ogni tipo di azione singolarmente.
    """
    tipo = az.get('tipo')
    # Recupero la lista di campi geometrici per questo tipo (default: nessuno)
    fields = _FORMA_FIELDS.get(tipo, ())
    # Costruisco il dict risultato: tipo + solo i campi geometrici presenti
    return {'tipo': tipo,
            **{k: az[k] for k in fields if k in az}}


# =============================================================================
# Helper: suddivide la lista azioni in "chunk" separati dai cooldown
# =============================================================================

def _split_in_chunks(azioni):
    """
    Suddivide la lista azioni in chunk e durate di cooldown.

    Le task multi-step usano "cooldown" come separatori. Esempio:
    ``[click, drag, cooldown(2s), click, click]`` -> 2 chunk
    ``[[click, drag], [click, click]]`` con cooldowns = ``[2.0]``.

    Ritorna la coppia (chunks, cooldowns) dove:
    - ``chunks`` = lista di liste di azioni (senza cooldown).
    - ``cooldowns`` = lista delle durate dei cooldown fra i chunk
      (lunghezza = ``len(chunks) - 1``).
    """
    chunks = []           # lista risultato dei chunk
    chunk_corrente = []   # chunk in costruzione
    cooldowns = []        # durate dei cooldown trovati
    for az in azioni:
        if az.get('tipo') == 'cooldown':
            # Cooldown: chiudi il chunk corrente e registra la durata
            chunks.append(chunk_corrente)
            cooldowns.append(az.get('durata', 0.0))
            chunk_corrente = []
        else:
            # Azione normale: accodala al chunk in costruzione
            chunk_corrente.append(az)
    # L'ultimo chunk va sempre aggiunto (anche se vuoto)
    chunks.append(chunk_corrente)
    return chunks, cooldowns


# =============================================================================
# Helper: attende che la finestra del gioco torni in primo piano
# =============================================================================

def _attendi_focus(hwnd, is_test):
    """
    Se la finestra del gioco non e' in primo piano, mette il bot in pausa
    finche' non lo torna.

    Ritorna True se il focus e' stato (re)acquisito, False se l'utente
    ha richiesto stop globale durante l'attesa.
    """
    # Se il gioco e' gia' in primo piano, niente da fare
    if win32gui.GetForegroundWindow() == hwnd:
        return True
    # Altrimenti aspetta finche' torna in foreground
    print("[Esecuzione] Gioco non in primo piano, in pausa...")
    # Ottiene l'handle della finestra in primo piano
    while win32gui.GetForegroundWindow() != hwnd:
        # In modalita' Test, F4/END devono interrompere subito
        if is_test and stop_flag.requested:
            return False
        # Pausa il thread per il tempo specificato (secondi)
        time.sleep(0.5)
    # Piccolo grace period dopo il refocus per evitare di cliccare
    # mentre la finestra sta ancora "ricevendo" il focus
    time.sleep(0.3)
    return True


# =============================================================================
# Entry point: esegui_azioni
# =============================================================================

def esegui_azioni(azioni, hwnd, current_step=0, is_test=False):
    """
    Esegue una lista di azioni in sequenza (motore live).

    Parametri
    ---------
    azioni : list[dict]
        Lista delle azioni da eseguire. Ognuna ha almeno un campo
        ``tipo`` che decide quale handler invocare.
    hwnd : int
        Handle della finestra del gioco. Usato per:
        1. Verificare che il gioco sia in primo piano prima di ogni azione.
        2. Calcolare il rect del client per coordinate relative.
    current_step : int
        Indice del "chunk" di azioni da eseguire (le azioni sono
        suddivise in chunk dai cooldown). Se ``is_test`` e' True,
        questo parametro viene ignorato e si esegue tutto.
    is_test : bool
        True se chiamato dal pulsante "Test" dell'editor (modalita'
        verbosa con stampe + supporto stop_flag).

    Ritorna
    -------
    bool
        True se tutto e' andato bene, False se l'ambiente Windows
        non e' disponibile o se non si riesce a leggere il rect.
    """
    # Senza ambiente Windows non si fa nulla
    if not _WIN_OK:
        return False

    # 1) Suddividi le azioni in chunk (separati dai cooldown)
    chunks, cooldowns = _split_in_chunks(azioni)
    # Clamp del current_step entro i limiti validi
    if current_step >= len(chunks):
        current_step = max(0, len(chunks) - 1)
    # In test mode si esegue TUTTO, altrimenti solo il chunk corrente
    azioni_da_eseguire = azioni if is_test else chunks[current_step]

    # 2) Esegui ogni azione del chunk
    for az in azioni_da_eseguire:
        # Stop globale: il pulsante Test puo' essere interrotto
        if is_test and stop_flag.requested:
            print("[Test] Sequenza interrotta dall'utente.")
            break
        # Aspetta che il gioco sia in primo piano (gestisce anche stop)
        if _WIN_OK and not _attendi_focus(hwnd, is_test):
            break
        # Leggi il rect del client per coordinate relative
        rect = get_client_rect(hwnd)
        if not rect:
            return False
        cx, cy, cw, ch = rect
        tipo = az.get("tipo")

        # Cooldown e' un caso speciale: gestito direttamente dal dispatcher
        # senza passare a un handler. In modalita' test mostra il messaggio
        # e mette in pausa, in modalita' produzione viene saltato (gia'
        # gestito dal subprocess runner via __COOLDOWN__).
        if tipo == "cooldown":
            if is_test:
                durata = az.get("durata", 0.0)
                print(f"[Test] Attesa cooldown di {durata}s...")
                # Pausa il thread per il tempo specificato (secondi)
                time.sleep(durata)
            continue

        # 3) Dispatch all'handler della famiglia di azione.
        # Ogni handler ha la firma: handle_X(az, cx, cy, cw, ch, hwnd, is_test)
        handler = DISPATCH_MAP.get(tipo)
        if handler is None:
            print(f"[esegui_azioni] Tipo sconosciuto: {tipo}")
        else:
            handler(az, cx, cy, cw, ch, hwnd, is_test)

        # Pausa fra azioni (configurabile per ogni azione)
        time.sleep(az.get("attesa", 0.0))

    # 4) Stampa la durata del cooldown post-step. Il subprocess runner
    # (in tasks_process.py) intercetta questa riga di stdout e mette in
    # pausa il bot prima di lanciare il prossimo step.
    if not is_test and current_step < len(cooldowns):
        print(f"__COOLDOWN__:{cooldowns[current_step]}")
    return True
