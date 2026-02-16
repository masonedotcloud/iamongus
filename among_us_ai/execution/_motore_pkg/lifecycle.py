"""
Lifecycle parametrizzato: setup -> run_task -> teardown.

Funzioni chiamate dai thin wrapper task_<id>_<nome>.py. Ricevono
TASK_META e AZIONI come parametri (non come globali!), per permettere
a un singolo modulo motore di gestire qualunque task.
"""
import sys as _sys
import time as _time
try:
    import pyautogui as _pag
    import win32gui as _win32gui
    _OK = True
except Exception:
    _pag = None
    _win32gui = None
    _OK = False

from .dispatcher import esegui_azioni

def setup(ctx):
    # Hook chiamato prima di run_task. Vuoto di default.
    pass


def run_task(task_meta, azioni, ctx=None):
    """
    Entry point chiamato dal thin wrapper della task.

    Parametri
    ---------
    task_meta : dict
        Dati della task (nome, step, fasi, ecc.). Contiene il campo 'step'
        che dice quale chunk di azioni eseguire.
    azioni : list[dict]
        Lista delle azioni da eseguire.
    ctx : dict | None
        Contesto opzionale: puo' contenere 'hwnd' (handle finestra)
        e 'finestra' (nome della finestra, default "Among Us").

    Ritorna
    -------
    bool
        True se l'esecuzione e' andata a buon fine, False altrimenti.
    """
    if ctx is None:
        ctx = {}
    # Senza ambiente Windows non si fa nulla
    if not _OK:
        return False

    # 1) Risolvi l'hwnd: dal ctx, oppure cerca per nome
    hwnd = ctx.get('hwnd')
    if hwnd is None:
        nome = ctx.get('finestra', 'Among Us')
        hwnd = _win32gui.FindWindow(None, nome)
        if not hwnd:
            print(f"[{task_meta.get('nome', '?')}] finestra non trovata: {nome}")
            return False
        # Porta la finestra in primo piano + grace period
        try:
            _win32gui.SetForegroundWindow(hwnd)
            _time.sleep(0.4)
        except Exception:
            # In alcune circostanze (UAC) Windows nega il SetForegroundWindow.
            # Continuiamo comunque, sperando che l'utente abbia gia' la
            # finestra in primo piano.
            pass

    # 2) Se la task non ha azioni, esci subito (puo' succedere per task
    #    figlie senza azioni proprie e senza padre)
    if not azioni:
        print(f"[{task_meta.get('nome', '?')}] nessuna azione registrata.")
        return True

    # 3) Esegui la sequenza, partendo dallo step indicato in task_meta
    #    (lo step viene aggiornato dal TaskManager basandosi sulla RAM)
    return esegui_azioni(azioni, hwnd, current_step=task_meta.get('step', 0))


def teardown(ctx):
    # Hook chiamato dopo run_task (anche in caso di errore). Vuoto di default.
    pass


def esegui_lifecycle(task_meta, azioni, ctx=None):
    """
    Esegue il lifecycle completo: setup -> run_task -> teardown.

    Chiamato dai thin wrapper nel main block. Gestisce le eccezioni e
    setta l'exit code appropriato (1 se run_task ritorna False).
    """
    if ctx is None:
        ctx = {}
    nome = task_meta.get('nome', '?')
    print(f"[{nome}] Setup...")
    setup(ctx)
    print(f"[{nome}] Esecuzione...")
    try:
        ok = run_task(task_meta, azioni, ctx)
        print(f"[{nome}] Completata: {ok}")
        # Se l'esecuzione ha fallito, exit con codice 1 cosi' il
        # TaskManager (subprocess) puo' rilevare l'errore e tentare
        # un fallback (es. provare un punto alternativo).
        if not ok:
            _sys.exit(1)
    except Exception as exc:
        print(f"[{nome}] Errore: {exc}")
        # Re-raise: il subprocess avra' exit code != 0 e stack trace su stderr
        raise
    finally:
        # Garantito eseguito anche in caso di eccezione
        teardown(ctx)
        print(f"[{nome}] Teardown completato.")


