"""
Generazione dei file di esecuzione delle task in ``tasks_exec/``.

Architettura del modello "thin wrapper" (v2.1.8):

    tasks_exec/
        _motore.py                    <- codice comune (~1100 righe)
        task_001_Swipe_Card.py        <- thin wrapper (~100 righe)
        task_002_Download_Data.py     <- thin wrapper
        ...

Il file ``_motore.py`` contiene tutto il codice condiviso:
- 10 helper geometriche (`_client_rect`, `_drag_umano`, ...)
- 19 handler per i tipi di azione (`_h_click`, `_h_drag`, ...)
- ``_DISPATCH_MAP`` (tipo -> handler)
- ``esegui_azioni(...)`` dispatcher principale
- ``run_task(task_meta, azioni, ctx)`` lifecycle parametrizzato

I file ``task_<id>_<nome>.py`` sono THIN WRAPPER che contengono solo:
- ``TASK_META`` (dict con id, nome, posizione, fasi, ecc.)
- ``AZIONI`` (lista delle azioni)
- import relativo di ``_motore`` + chiamata a ``run_task``

Vantaggi:
- File task da ~1300 righe a ~100 righe (-90%)
- Modificare il motore aggiorna automaticamente tutte le task
- Cartella ``tasks_exec/`` portable (basta copiarla intera)

API pubblica:
    genera_file_esecuzione(task, azioni_effettive, src_id, tasks_exec_dir)
        -> filepath  (oppure None in caso di errore)
"""

import os

from .task_template import get_motore_modulo


# Nome del file motore comune. Importato dai thin wrapper come `_motore`.
NOME_FILE_MOTORE = "_motore.py"


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
    Scrive ``tasks_exec/_motore.py`` se non esiste o se e' obsoleto.

    Confronto contenuto byte-per-byte: se il file esistente e' identico
    al template, non riscrive (preserva timestamp e evita rewrite inutili).
    """
    path = os.path.join(tasks_exec_dir, NOME_FILE_MOTORE)
    nuovo = get_motore_modulo()

    # Se esiste e identico, non riscrivere
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                if f.read() == nuovo:
                    return  # gia' aggiornato
        except Exception:
            # Errore di lettura: meglio sovrascrivere
            pass

    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(nuovo)
        print(f"[TaskWriter] Motore aggiornato: {path}")
    except Exception as e:
        print(f"[TaskWriter] Errore scrittura {NOME_FILE_MOTORE}: {e}")


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
                t_fasi, t_params, t_azioni):
    """Dizionario TASK_META + costante AZIONI (parsing args CLI incluso)."""
    return (
        "# --- Parsing argomenti CLI ---\n"
        "# Lo step indica QUALE chunk di azioni eseguire (le azioni\n"
        "# sono divise in chunk dai 'cooldown'). Il TaskManager passa\n"
        "# lo step appropriato in base alla RAM del gioco (es. step 1\n"
        "# se siamo nella seconda fase di una task multi-fase).\n"
        "import argparse\n"
        "_parser = argparse.ArgumentParser()\n"
        "_parser.add_argument('--step', type=int, default=0,\n"
        "                     help='Indice del chunk di azioni da eseguire')\n"
        "_args, _ = _parser.parse_known_args()\n"
        "CURRENT_STEP = _args.step\n\n"
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
        "    'step':          CURRENT_STEP,\n"
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
