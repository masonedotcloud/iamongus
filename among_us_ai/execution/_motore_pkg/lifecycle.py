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
    """
    Hook chiamato prima di :func:`run_task`. Vuoto di default.

    Sovrascrivibile in test e custom task: il subprocess legge l'``__init__``
    del modulo e puo' definirne uno proprio.
    """
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

    # === STDIN READER THREAD ===
    # Il bot principale comunica col subprocess via stdin pipe.
    # Messaggi supportati (uno per riga, terminati da \n):
    #   "GO"   -> sblocca il pre-warming (attesa iniziale)
    #   "STOP" -> richiedi interruzione dell'esecuzione (RAM avanzata,
    #             fase considerata completata, no piu' azioni inutili)
    #   altro  -> ignorato (forward compatibility)
    #
    # Il thread reader gira in background per tutta la vita del
    # subprocess. Termina quando stdin viene chiusa dal bot principale
    # o all'EOF naturale.
    from . import stop_flag as _stop_flag
    # Reset della stop flag (sicurezza: se il subprocess fosse riusato,
    # la flag NON deve persistere fra task diverse)
    _stop_flag.reset_stop()

    # Evento che segnala "GO ricevuto" per il pre-warming
    import threading as _threading
    _go_event = _threading.Event()

    def _stdin_reader():
        """Thread reader di stdin: gestisce GO e STOP."""
        import sys as _sys
        try:
            while True:
                line = _sys.stdin.readline()
                if not line:
                    # stdin chiuso: il bot principale e' morto o ha
                    # finito di comunicare. Esci dal thread.
                    # Sblocca anche il pre-warming, cosi' non resta
                    # bloccato a vita.
                    _go_event.set()
                    return
                msg = line.strip().upper()
                if msg == "GO":
                    _go_event.set()
                elif msg == "STOP":
                    nome_t = task_meta.get('nome', '?')
                    print(f"[{nome_t}] STOP richiesto: interrompo esecuzione",
                          flush=True)
                    _stop_flag.request_stop()
                    # Continua a leggere (potrebbero arrivare altri
                    # messaggi futuri, anche se ora non ne abbiamo).
        except Exception:
            # Lettura fallita (pipe rotta, ecc.): esci silenziosamente
            _go_event.set()
            return

    _reader_thread = _threading.Thread(target=_stdin_reader, daemon=True)
    _reader_thread.start()

    # 0) PRE-WARMING: se attivo, aspetta che il reader thread riceva "GO".
    #    Il bot principale avvia il subprocess in anticipo (durante
    #    l'arrivo al target del giocatore) con --wait-trigger. Il
    #    subprocess fa setup (import, mss, ecc.) poi aspetta qui.
    #    Quando il bot preme SPAZIO per aprire il pannello, manda
    #    "GO\n" sullo stdin del subprocess, che riprende immediatamente.
    if task_meta.get('wait_trigger', False):
        nome_t = task_meta.get('nome', '?')
        print(f"[{nome_t}] Pronto, aspetto trigger...", flush=True)
        # Aspetta che il reader thread setti _go_event (per "GO" o EOF).
        # Timeout di sicurezza 60s: se nessuno manda GO in 60s, parti
        # comunque per non bloccare a vita.
        _go_event.wait(timeout=60.0)
        print(f"[{nome_t}] Trigger ricevuto, parto!", flush=True)

    # 1) Risolvi l'hwnd: dal ctx, oppure cerca per nome
    hwnd = ctx.get('hwnd')
    if hwnd is None:
        nome = ctx.get('finestra', 'Among Us')
        hwnd = _win32gui.FindWindow(None, nome)
        if not hwnd:
            print(f"[{task_meta.get('nome', '?')}] finestra non trovata: {nome}")
            return False
        # Porta la finestra in primo piano se non lo e' gia'.
        # Skipping del SetForegroundWindow + sleep(0.4) quando la
        # finestra e' GIA' in primo piano: in questo caso il bot
        # principale (che ci ha appena lanciato come subprocess)
        # ha gia' garantito il foreground, e la pausa di 0.4s e'
        # solo latenza inutile. Risparmio cruciale per minigiochi
        # tempo-critici come Simon Says (Start Reactor) dove ogni
        # millisecondo di lag fa perdere il primo flash della sequenza.
        try:
            if _win32gui.GetForegroundWindow() != hwnd:
                _win32gui.SetForegroundWindow(hwnd)
                # Grace period solo se abbiamo davvero spostato la finestra
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

    # 3) Inietta nelle azioni simon_says il `panel_timeout` da TASK_META
    #    se non e' gia' specificato a livello di singola azione. Cosi'
    #    l'handler `_h_simon_says` puo' leggere il valore corretto via
    #    `az.get('panel_timeout')` senza dover importare config.
    #
    # Priorita' (dalla piu' alta alla piu' bassa):
    #   1. `panel_timeout` nel JSON dell'azione (override per task)
    #   2. `simon_panel_timeout` in TASK_META (config globale iniettata
    #      dal task_writer al momento della generazione del file .py)
    #   3. Default 1.0s nel handler (fallback)
    panel_timeout_default = task_meta.get('simon_panel_timeout')
    if panel_timeout_default is not None:
        for az in azioni:
            if (az.get('tipo') == 'simon_says'
                    and 'panel_timeout' not in az):
                az['panel_timeout'] = panel_timeout_default

    # 4) DELAY AVVIO (configurabile per task nel popup di modifica).
    #    Pausa applicata UNA volta prima di iniziare le azioni. Default
    #    0 (parte subito). Utile per minigiochi con animazione di
    #    apertura lenta (es. Reactor Simon Says): l'utente puo' impostare
    #    1-2 secondi per dare al pannello il tempo di stabilizzarsi
    #    prima di analizzare/cliccare.
    delay_avvio = float(task_meta.get('delay_avvio', 0.0))
    if delay_avvio > 0:
        print(f"[{task_meta.get('nome', '?')}] Delay avvio: {delay_avvio}s",
              flush=True)
        _time.sleep(delay_avvio)

    # 5) Esegui la sequenza, partendo dallo step indicato in task_meta
    #    (lo step viene aggiornato dal TaskManager basandosi sulla RAM)
    #    e saltando le prime N azioni se richiesto (modalita' "ripeti azione").
    return esegui_azioni(
        azioni, hwnd,
        current_step=task_meta.get('step', 0),
        start_from_action=task_meta.get('start_from_action', 0),
    )


def teardown(ctx):
    """
    Hook chiamato dopo :func:`run_task` (anche in caso di eccezione).
    Vuoto di default. Sovrascrivibile per cleanup custom (es. release
    risorse esterne).
    """
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


