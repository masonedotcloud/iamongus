"""
Generazione dei file di esecuzione delle task in ``tasks_exec/``.

Architettura del modello "thin wrapper":

    tasks_exec/
        _motore/                      <- package modulare con il motore comune
            __init__.py               <- API pubblica (run_task, esegui_lifecycle, ...)
            geometria.py              <- helper geometriche (poligono, rect)
            input_mouse.py            <- click + drag con movimenti umani
            handlers_clicks.py        <- handler per click/click_rect/click_poly/click_until
            handlers_drags.py         <- handler per drag/drag_multi/drag_zone/drag_hold
            handlers_wiring.py        <- handler per Fix Wiring
            handlers_sync.py          <- handler per Calibrate Distributor (sync_click)
            handlers_anomaly.py       <- handler per Detect Anomaly
            handlers_yolo.py          <- 5 handler YOLO
            handlers_simon.py         <- handler per Simon Says
            handlers_ocr.py           <- handler per OCR/keypad
            dispatcher.py             <- _DISPATCH_MAP + esegui_azioni
            lifecycle.py              <- setup, run_task, teardown, esegui_lifecycle
        task_001_Swipe_Card.py        <- thin wrapper (~74 righe)
        task_002_Download_Data.py     <- thin wrapper
        ...

Il package ``_motore/`` viene COPIATO da ``among_us_ai/execution/_motore_pkg/``
nella cartella ``tasks_exec/`` come ``_motore/``. I thin wrapper fanno
``import _motore`` e poi ``_motore.esegui_lifecycle(TASK_META, AZIONI)``.

Vantaggi del package modulare:
- ogni handler vive nel suo file, leggibile in isolamento
- modificare un singolo handler non tocca gli altri file
- il `__init__.py` espone solo l'API pubblica

API pubblica:
    genera_file_esecuzione(task, azioni_effettive, src_id, tasks_exec_dir)
        -> filepath (oppure None)
"""

import os
import shutil

from .task_template import get_motore_modulo


# Nome della cartella del package motore in tasks_exec/
NOME_DIR_MOTORE = "_motore"

# Path della cartella sorgente del package nel codice sorgente del bot
_SRC_PKG_DIR = os.path.join(os.path.dirname(__file__), "_motore_pkg")


def genera_file_esecuzione(task, azioni_effettive, src_id, tasks_exec_dir):
    """
    Crea (o sovrascrive) il file `.py` thin-wrapper della ``task`` dentro
    ``tasks_exec_dir``. Si occupa anche di creare/aggiornare ``_motore.py``
    nella stessa cartella se non esiste o se il template e' cambiato.

    Ritorna il path del file task creato, oppure ``None`` in caso di errore.

    Parametri
    ---------
    task : dict
        Dict della task (id, nome, x, y, tipo, id_stanza, vitale, fasi, ...).
    azioni_effettive : list
        Lista delle azioni gia' risolte (per task figlie sono quelle del
        padre, altrimenti quelle proprie).
    src_id : int | None
        ID della task da cui provengono ``azioni_effettive``. None se sono
        della task stessa, l'ID del padre se ereditate.
    tasks_exec_dir : str
        Directory di output (creata se mancante).
    """
    if task is None:
        return None

    # Crea la directory (e i parent) se non esiste
    os.makedirs(tasks_exec_dir, exist_ok=True)

    # 1) Assicura che _motore.py sia presente e aggiornato
    _scrivi_motore_se_necessario(tasks_exec_dir)

    # 2) Genera il thin wrapper della task
    return _scrivi_thin_wrapper(task, azioni_effettive, src_id, tasks_exec_dir)


def _scrivi_motore_se_necessario(tasks_exec_dir):
    """
    Copia il package ``_motore_pkg/`` (contenuto in
    ``among_us_ai/execution/``) come ``tasks_exec/_motore/``, sovrascrivendo
    se gia' presente.

    Confronto file-per-file: se tutti i file sono identici, non riscrive
    (preserva timestamp).
    """
    dst_dir = os.path.join(tasks_exec_dir, NOME_DIR_MOTORE)

    # Verifica che la sorgente esista
    if not os.path.isdir(_SRC_PKG_DIR):
        print(f"[TaskWriter] !! Package motore sorgente non trovato: {_SRC_PKG_DIR}")
        return

    # Se la destinazione e' identica alla sorgente, salta
    if _package_identico(_SRC_PKG_DIR, dst_dir):
        return

    # Pulisci la destinazione e ricopia
    if os.path.isdir(dst_dir):
        shutil.rmtree(dst_dir)
    shutil.copytree(_SRC_PKG_DIR, dst_dir)
    print(f"[TaskWriter] Motore package aggiornato: {dst_dir}/")


def _package_identico(src_dir, dst_dir):
    """
    Ritorna True se ``dst_dir`` esiste e contiene file con lo stesso
    nome e contenuto di ``src_dir`` (compresi __pycache__ esclusi).
    """
    if not os.path.isdir(dst_dir):
        return False
    src_files = sorted(f for f in os.listdir(src_dir)
                       if f.endswith('.py') and f != '__pycache__')
    dst_files = sorted(f for f in os.listdir(dst_dir)
                       if f.endswith('.py') and f != '__pycache__')
    if src_files != dst_files:
        return False
    for fn in src_files:
        with open(os.path.join(src_dir, fn), 'rb') as a, \
             open(os.path.join(dst_dir, fn), 'rb') as b:
            if a.read() != b.read():
                return False
    return True


def _scrivi_thin_wrapper(task, azioni_effettive, src_id, tasks_exec_dir):
    """
    Scrive il thin wrapper ``task_<id>_<nome>.py`` per la task data.
    """
    # Nome file sicuro: task_<id>_<nome_sanitizzato>.py
    nome_safe = "".join(c if c.isalnum() or c in "_- " else "_" for c in task['nome'])
    nome_safe = nome_safe.replace(" ", "_").strip("_")
    filename = f"task_{task['id']:03d}_{nome_safe}.py"
    filepath = os.path.join(tasks_exec_dir, filename)

    # Costruisce le righe delle fasi (nel commento header)
    fasi_lines = ""
    for i, f in enumerate(task.get('fasi', [])):
        fasi_lines += (
            f"# Fase {i}: {f['nome']}  @ ({f['x']:.3f}, {f['y']:.3f})\n"
        )
    if not fasi_lines:
        fasi_lines = "# Nessuna fase registrata\n"

    # Valori pre-estratti per evitare accessi nidificati nelle f-string
    t_id        = task['id']
    t_nome      = task['nome']
    t_x         = task['x']
    t_y         = task['y']
    t_zona      = task.get('nome_zona', 'N/A')
    t_tipo      = task.get('tipo')
    t_id_stanza = task.get('id_stanza')
    t_vitale    = task.get('vitale', False)
    t_due_p     = task.get('due_giocatori', False)
    t_lunghezza = task.get('lunghezza', 'N/A')
    t_fasi      = task.get('fasi', [])
    t_id_padre  = task.get('id_padre')
    # Pausa iniziale (sec) che il motore deve rispettare prima di iniziare
    # le azioni. Default 0 (parte subito). Configurabile per task nel popup
    # di modifica. Utile per minigiochi con animazione di apertura lenta
    # (es. Reactor Simon Says): se imposti 1.5s, il bot aspetta che il
    # pannello sia stabile prima di analizzare.
    t_delay_avvio = float(task.get('delay_avvio', 0.0))
    t_params    = task.get('esecuzione', {}).get('parametri',
                  task.get('esecuzione', {}).get('params', {}))

    # Costruisce il contenuto del file
    header = _build_header(
        t_id, t_nome, t_x, t_y, t_zona, t_tipo, t_id_stanza,
        t_vitale, t_due_p, t_id_padre, src_id,
        len(azioni_effettive), fasi_lines,
    )
    meta = _build_meta(
        t_id, t_nome, t_x, t_y, t_tipo, t_id_stanza,
        t_vitale, t_due_p, t_lunghezza, t_id_padre,
        t_fasi, t_params, azioni_effettive,
        t_delay_avvio,
    )
    main_block = _build_main_block()

    contenuto = header + meta + main_block

    try:
        with open(filepath, 'w', encoding='utf-8') as fh:
            fh.write(contenuto)
        print(f"[TaskWriter] File esecuzione creato: {filepath}")
        return filepath
    except Exception as e:
        print(f"[TaskWriter] Errore creazione file esecuzione: {e}")
        return None


def _build_header(t_id, t_nome, t_x, t_y, t_zona, t_tipo, t_id_stanza,
                  t_vitale, t_due_p, t_id_padre, src_id,
                  num_azioni, fasi_lines):
    """Commento di intestazione con metadati della task."""
    parent_note = (
        "  (azioni ereditate)\n"
        if (t_id_padre is not None and src_id == t_id_padre)
        else "\n"
    )
    azioni_note = (
        f"  [dalla task padre {src_id}]\n"
        if (src_id is not None and src_id != t_id)
        else "\n"
    )

    return (
        "# =============================================================\n"
        "# FILE ESECUZIONE TASK - generato automaticamente dal bot\n"
        "# =============================================================\n"
        f"# Task ID         : {t_id}\n"
        f"# Nome            : {t_nome}\n"
        f"# Posizione mappa : ({t_x:.3f}, {t_y:.3f})\n"
        f"# Zona            : {t_zona}\n"
        f"# Tipo RAM gioco  : {t_tipo}  |  ID stanza: {t_id_stanza}\n"
        f"# Vitale          : {t_vitale}\n"
        f"# Due giocatori   : {t_due_p}\n"
        f"# ID padre        : {t_id_padre}"
        + parent_note
        + f"# Numero azioni   : {num_azioni}"
        + azioni_note
        + "# =============================================================\n"
        "# Questo file e' un THIN WRAPPER: contiene solo i dati specifici\n"
        "# della task (TASK_META e AZIONI), il codice del motore comune\n"
        "# e' in `_motore.py` nella stessa cartella.\n"
        "#\n"
        "# Uso da CLI:\n"
        "#     python task_<id>_<nome>.py [--step N]\n"
        "#\n"
        "# Le modifiche manuali a questo file saranno SOVRASCRITTE al\n"
        "# prossimo salvataggio dalla dashboard del bot. Per evitare la\n"
        "# sovrascrittura, abilita 'codice personalizzato' nella scheda\n"
        "# della task.\n"
        "# =============================================================\n\n"
        "# --- Fasi registrate (ordine di esecuzione suggerito) ---\n"
        f"{fasi_lines}\n"
    )


def _build_meta(t_id, t_nome, t_x, t_y, t_tipo, t_id_stanza,
                t_vitale, t_due_p, t_lunghezza, t_id_padre,
                t_fasi, t_params, t_azioni,
                t_delay_avvio=0.0):
    """Dizionario TASK_META + costante AZIONI (parsing args CLI incluso)."""
    # Leggi valori dalla config corrente per "iniettarli" come costanti
    # globali nel file generato. Questo permette al motore (motore_pkg)
    # di usarli senza dover importare GPSConfig (che non e' disponibile
    # nei file autonomi). Se l'utente cambia la config, basta rigenerare
    # i file delle task per propagare il nuovo valore.
    try:
        from ..core.config import GPSConfig as _GPSCfg
        simon_panel_timeout = float(getattr(_GPSCfg, 'SIMON_PANEL_TIMEOUT_SEC', 1.0))
    except Exception:
        simon_panel_timeout = 1.0

    return (
        "# --- Parsing argomenti CLI ---\n"
        "# Lo step indica QUALE chunk di azioni eseguire (le azioni\n"
        "# sono divise in chunk dai 'cooldown'). Il TaskManager passa\n"
        "# lo step appropriato in base alla RAM del gioco (es. step 1\n"
        "# se siamo nella seconda fase di una task multi-fase).\n"
        "#\n"
        "# --start-from-action N : per il modello 'ripeti azione', il\n"
        "# bot rilancia il subprocess saltando le prime N azioni del\n"
        "# chunk corrente (utile quando solo alcune azioni hanno\n"
        "# [Ripeti]=True e va riprovata solo la parte finale).\n"
        "#\n"
        "# --wait-trigger : modalita' pre-warming. Il subprocess fa il\n"
        "# setup (import, mss apertura, ecc.) poi ASPETTA una riga 'GO'\n"
        "# su stdin prima di iniziare l'esecuzione. Il bot principale\n"
        "# usa questo per avviare il subprocess in anticipo (es. durante\n"
        "# l'arrivo al target) e poi triggerarlo al press SPAZIO. Cosi'\n"
        "# tutto il startup di Python (~300-500ms) e l'import del motore\n"
        "# avvengono PRIMA del trigger, e all'analisi parte istantanea.\n"
        "import argparse\n"
        "_parser = argparse.ArgumentParser()\n"
        "_parser.add_argument('--step', type=int, default=0,\n"
        "                     help='Indice del chunk di azioni da eseguire')\n"
        "_parser.add_argument('--start-from-action', type=int, default=0,\n"
        "                     dest='start_from_action',\n"
        "                     help='Salta le prime N azioni del chunk')\n"
        "_parser.add_argument('--wait-trigger', action='store_true',\n"
        "                     dest='wait_trigger',\n"
        "                     help='Aspetta GO su stdin prima di partire')\n"
        "_args, _ = _parser.parse_known_args()\n"
        "CURRENT_STEP = _args.step\n"
        "START_FROM_ACTION = _args.start_from_action\n"
        "WAIT_TRIGGER = bool(_args.wait_trigger)\n\n"
        "# --- Costanti di config iniettate dal task_writer ---\n"
        "# Lette da among_us_ai/core/config.py al momento della\n"
        "# generazione del file. Se modifichi la config, rigenera i\n"
        "# file delle task per propagare i nuovi valori.\n"
        f"SIMON_PANEL_TIMEOUT_SEC = {simon_panel_timeout!r}  # default 1.0s\n\n"
        "# --- Metadati della task ---\n"
        "TASK_META = {\n"
        f"    'id':            {t_id!r},\n"
        f"    'nome':          {t_nome!r},\n"
        f"    'x':             {t_x:.3f},\n"
        f"    'y':             {t_y:.3f},\n"
        f"    'tipo':          {t_tipo!r},\n"
        f"    'id_stanza':     {t_id_stanza!r},\n"
        f"    'vitale':        {t_vitale!r},\n"
        f"    'due_giocatori': {t_due_p!r},\n"
        f"    'lunghezza':     {t_lunghezza!r},\n"
        f"    'id_padre':      {t_id_padre!r},\n"
        f"    'fasi':          {t_fasi!r},\n"
        f"    'parametri':     {t_params!r},\n"
        f"    'delay_avvio':   {t_delay_avvio!r},  # sec di pausa pre-azioni (0 = subito)\n"
        "    'step':                CURRENT_STEP,\n"
        "    'start_from_action':   START_FROM_ACTION,\n"
        "    'wait_trigger':        WAIT_TRIGGER,\n"
        "    # Costante config iniettata dal task_writer:\n"
        "    'simon_panel_timeout': SIMON_PANEL_TIMEOUT_SEC,\n"
        "}\n\n"
        "# --- Lista azioni della task ---\n"
        f"AZIONI = {t_azioni!r}\n\n"
    )


def _build_main_block():
    """
    Main block: import del motore comune + chiamata a esegui_lifecycle.

    L'import e' relativo: assume che `_motore.py` sia nella stessa cartella
    di questo file. Aggiunge la cartella al sys.path se non c'e' gia'.
    """
    return (
        "# --- Import del motore comune (_motore.py nella stessa cartella) ---\n"
        "import os\n"
        "import sys\n"
        "_DIR = os.path.dirname(os.path.abspath(__file__))\n"
        "if _DIR not in sys.path:\n"
        "    sys.path.insert(0, _DIR)\n"
        "import _motore  # codice condiviso da tutte le task\n\n"
        "# --- Entry point ---\n"
        "# Quando il file e' lanciato come script, esegue il lifecycle\n"
        "# completo (setup -> run_task -> teardown) sul motore comune.\n"
        "if __name__ == '__main__':\n"
        "    _motore.esegui_lifecycle(TASK_META, AZIONI)\n"
    )
