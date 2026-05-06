"""
GameStateMonitor: polling dello stato del gioco di Among Us.

Legge in continuo (1 Hz) lo stato del gioco dalla memoria e gestisce
le fasi:
- MENU       : siamo nel menu principale -> bot fermo
- LOBBY      : siamo in lobby di attesa  -> bot fermo
- IMPOSTOR   : siamo in partita ma impostore -> bot fermo
- VOTING     : votazione in corso        -> bot fermo
- GHOST      : crewmate morto/fantasma   -> attivo, ma con linea retta (attraversa muri)
- ACTIVE     : crewmate vivo in partita  -> bot pienamente attivo
- POST_VOTE  : appena finita votazione -> bot fermo per 10s (grace period)

Quando il bot e' "fermo" per via di questa logica:
- Auto-Move e Auto-All vengono bloccati (no nuovi path / nessuna task)
- L'Intelligence viene messa in pausa (nessun update di tracker /
  activity / proximity / suspicion). Lo stato accumulato resta intatto.
- Il rendering della mappa continua normalmente
- Un banner colorato nella status bar indica lo stato corrente

Tutto modulare: una variabile `self._game_phase` mantiene lo stato
e altri mixin la consultano con `self._is_bot_active()`.
"""

from ._imports import *
import time as _time


# Costanti delle fasi
PHASE_UNKNOWN  = 'UNKNOWN'
PHASE_MENU     = 'MENU'
PHASE_LOBBY    = 'LOBBY'
PHASE_IMPOSTOR = 'IMPOSTOR'
PHASE_VOTING   = 'VOTING'
PHASE_GHOST    = 'GHOST'
PHASE_ACTIVE   = 'ACTIVE'
PHASE_POST_VOTE = 'POST_VOTE'

# Quanto aspettare dopo che la votazione finisce prima di riprendere
POST_VOTE_GRACE_SEC = 10.0

# Hz di polling della memoria (default 1 Hz)
POLLING_HZ = 1.0


class GameStateMonitorMixin:
    """Mixin: monitora la fase del gioco e ferma il bot quando serve."""

    # ============================================================
    # SETUP / INIT
    # ============================================================

    def _init_game_state_monitor(self):
        """
        Inizializza lo stato (chiamato da `app.py.__init__`).
        Crea il reader e popola lo stato iniziale.
        """
        try:
            # Path: siamo in among_us_ai/ui/mixins/ -> 3 dots per salire
            # a among_us_ai/ e poi entrare in game_io
            from ...game_io import AmongUsGameStateReader
            self._game_state_reader = AmongUsGameStateReader()
        except Exception as e:
            print(f"[GameState] Errore init reader: {e}", flush=True)
            self._game_state_reader = None

        # Stato corrente
        self._game_phase = PHASE_UNKNOWN
        self._game_phase_since = _time.time()
        # Snapshot completo dell'ultima lettura
        self._last_game_state = None
        # Timer di polling
        self._game_state_poll_timer = 0.0
        # Per il grace period post-voto
        self._post_vote_end_t = None
        # Stato precedente (per detect transitions)
        self._prev_phase = PHASE_UNKNOWN

    # ============================================================
    # LOOP DI POLLING
    # ============================================================

    def _update_game_state(self, dt):
        """
        Chiamato dal loop principale ad ogni frame.
        Aggiorna la fase a frequenza ridotta (default 1 Hz).
        """
        if not getattr(self, '_game_state_reader', None):
            # Aggiorno comunque il banner UI (resta 'UNKNOWN')
            self._refresh_phase_label_ui()
            return

        self._game_state_poll_timer += dt
        interval = 1.0 / POLLING_HZ
        if self._game_state_poll_timer < interval:
            return
        self._game_state_poll_timer = 0.0

        state = self._game_state_reader.get_game_state()
        if state is None:
            # Non riusciamo a leggere: assumo MENU (sicuro: tutto fermo)
            new_phase = PHASE_MENU
        else:
            self._last_game_state = state
            new_phase = self._classify_phase(state)

        # Gestione transizioni
        if new_phase != self._game_phase:
            self._on_phase_transition(self._game_phase, new_phase)
            self._prev_phase = self._game_phase
            self._game_phase = new_phase
            self._game_phase_since = _time.time()

        # Refresh dell'etichetta in status bar
        self._refresh_phase_label_ui()

    def _refresh_phase_label_ui(self):
        """Aggiorna il testo + colore dell'etichetta status_phase."""
        try:
            if dpg.does_item_exist("status_phase"):
                dpg.set_value("status_phase", self._get_phase_label())
                col = self._get_phase_color()
                dpg.configure_item("status_phase", color=col)
        except Exception:
            # DPG non ancora pronto o tag mancante: ignoro silenziosamente
            pass

    # ============================================================
    # CLASSIFICAZIONE FASE
    # ============================================================

    def _classify_phase(self, state):
        """
        Determina la fase corrente in base allo stato letto.
        Gestisce anche il grace period post-voto.
        """
        # In partita?
        if not state["in_game"]:
            # Menu o lobby
            if state["game_status"] == 1:
                return PHASE_LOBBY
            return PHASE_MENU

        # In partita: prima check del POST_VOTE grace.
        # NB: il grace serve a dare ai VIVI il tempo di "materializzarsi"
        # nel punto in cui li teletrasporta il gioco dopo il meeting.
        # I FANTASMI invece possono muoversi subito (non vengono
        # teletrasportati allo stesso modo e attraversano i muri), quindi
        # per loro NON applichiamo il grace: classifichiamo subito GHOST.
        if self._post_vote_end_t is not None:
            if _time.time() < self._post_vote_end_t:
                if state["is_dead"]:
                    # Fantasma dopo il voto: niente grace, riparte subito.
                    self._post_vote_end_t = None
                    return PHASE_GHOST
                return PHASE_POST_VOTE
            # Grace finito: spengo il timer
            self._post_vote_end_t = None

        # Votazione in corso?
        if state["is_voting"]:
            return PHASE_VOTING

        # Impostore? (bot non deve assistere all'impostore)
        if state["is_impostor"]:
            return PHASE_IMPOSTOR

        # Crewmate vivo o fantasma?
        if state["is_dead"]:
            return PHASE_GHOST
        return PHASE_ACTIVE

    # ============================================================
    # TRANSIZIONI DI FASE
    # ============================================================

    def _on_phase_transition(self, old_phase, new_phase):
        """Chiamato quando la fase cambia. Gestisce side-effects."""
        print(f"[GameState] Transizione: {old_phase} -> {new_phase}",
              flush=True)

        # --- AUTO-RESET TRA PARTITE ---
        # Se il toggle e' attivo e stiamo ENTRANDO in una nuova partita
        # (da menu/lobby a partita giocabile o impostore), azzera task e
        # stati di progresso come un F5 automatico. Cosi' ogni partita
        # parte pulita senza intervento manuale.
        if getattr(self, '_auto_reset_enabled', False):
            entering_game = (
                old_phase in (PHASE_MENU, PHASE_LOBBY, PHASE_UNKNOWN)
                and new_phase in (PHASE_ACTIVE, PHASE_IMPOSTOR, PHASE_GHOST)
            )
            if entering_game and hasattr(self, '_reset_partita'):
                print("[GameState] Nuova partita rilevata -> auto-reset",
                      flush=True)
                try:
                    self._reset_partita(silent=True)
                    self.auto_status_msg = "Auto-reset: nuova partita"
                except Exception as e:
                    print(f"[GameState] Auto-reset fallito: {e}", flush=True)

        # --- #6 MEETING / EMERGENZA: interrompi la task in corso ---
        # Se parte una votazione (meeting d'emergenza o body report) mentre
        # una task e' in esecuzione, la task va abbandonata SUBITO: il
        # subprocess riceve ESC (chiude il minigioco aperto) e viene fermato.
        # Quando il meeting finisce, l'Auto-All ripartira' da solo e
        # ri-sceglie la prossima task (eventualmente proprio questa, se non
        # completata: non viene marcata done).
        if new_phase == PHASE_VOTING and old_phase != PHASE_VOTING:
            self._interrompi_task_per_meeting()

        # --- #4 MORTE: ricomincia il giro da fantasma ---
        # Quando il crewmate muore (ACTIVE -> GHOST), la task in corso si
        # chiude. Da fantasma si possono ancora completare le task, quindi
        # ripartiamo il giro: fermiamo l'esecuzione corrente e, se Auto-All
        # era attivo, lo rilanciamo cosi' il bot riprende dal task piu'
        # conveniente in modalita' fantasma (linea retta, attraversa muri).
        if old_phase == PHASE_ACTIVE and new_phase == PHASE_GHOST:
            self._ricomincia_giro_da_fantasma()

        # Se siamo USCITI dalla votazione, attiva il grace period
        # PRIMA del passaggio reale alla fase successiva.
        # NB: il classify ha gia' deciso new_phase=ACTIVE/GHOST (o altro)
        # quindi rimpiazzo con POST_VOTE per i prossimi POST_VOTE_GRACE_SEC.
        if old_phase == PHASE_VOTING and new_phase in (
                PHASE_ACTIVE, PHASE_GHOST):
            self._post_vote_end_t = _time.time() + POST_VOTE_GRACE_SEC
            # La prossima _update_game_state vedra' il grace attivo
            # e classifichera' come POST_VOTE.
            return

        # Se siamo ENTRATI in fase di stop, fermo Auto-Move/Auto-All
        if not self._is_phase_bot_active(new_phase):
            try:
                # Ferma navigazione (auto move)
                if getattr(self, 'auto_path', None):
                    self._cancel_auto_move(silent=True, stop_auto_all=True)
            except Exception as e:
                print(f"[GameState] Errore stop auto_move: {e}",
                      flush=True)

    # ============================================================
    # API DI QUERY (usata da altri mixin)
    # ============================================================

    def _is_bot_active(self):
        """
        True se il bot puo' muoversi/lanciare task. False altrimenti.
        Chiamato da auto_move e auto_quest per decidere se procedere.

        IMPORTANTE: se il reader non e' disponibile (pymem non installato,
        gioco non rilevato) o non e' configurato (classi non impostate),
        il bot e' considerato ATTIVO per non rompere chi non usa questa
        feature. Il monitor in quel caso resta in fase UNKNOWN e
        l'etichetta in status bar mostra 'Stato: ...'.
        """
        reader = getattr(self, '_game_state_reader', None)
        # Senza reader o non configurato: bot sempre attivo (no regressione)
        if reader is None or not getattr(reader, '_is_configured', False):
            return True
        # Reader presente e configurato: dipende dalla fase
        return self._is_phase_bot_active(
            getattr(self, '_game_phase', PHASE_UNKNOWN))

    @staticmethod
    def _is_phase_bot_active(phase):
        """Logica pura: in quali fasi il bot e' attivo?"""
        return phase in (PHASE_ACTIVE, PHASE_GHOST)

    def _is_ghost(self):
        """True se siamo crewmate morti (fantasma -> walk-through)."""
        return getattr(self, '_game_phase', None) == PHASE_GHOST

    def _is_pre_lobby(self):
        """
        True se siamo nel menu o nella lobby di attesa (pre-partita).
        In questo stato il bot non deve analizzare nulla ne' muoversi.
        """
        return getattr(self, '_game_phase', None) in (PHASE_MENU, PHASE_LOBBY)

    def _is_in_meeting(self):
        """
        True se e' in corso una votazione/meeting d'emergenza (o il grace
        period subito dopo). Usato per interrompere le task in corso.
        """
        return getattr(self, '_game_phase', None) in (PHASE_VOTING,
                                                       PHASE_POST_VOTE)

    def _intelligence_should_run(self):
        """
        True se il sistema Intelligence deve continuare a girare.
        In lobby/voto/impostore/morto: pausa (ma non azzera).

        Senza reader o non configurato: sempre True (no regressione).
        """
        reader = getattr(self, '_game_state_reader', None)
        if reader is None or not getattr(reader, '_is_configured', False):
            return True
        return getattr(self, '_game_phase', None) == PHASE_ACTIVE

    def _get_phase_label(self):
        """Stringa da mostrare in status bar."""
        # Se il reader non e' configurato, mostro un messaggio chiaro
        reader = getattr(self, '_game_state_reader', None)
        if reader is None or not getattr(reader, '_is_configured', False):
            return "Stato: monitor disabilitato (classi non config)"
        phase = getattr(self, '_game_phase', PHASE_UNKNOWN)
        return {
            PHASE_UNKNOWN:   "Stato: in attesa lettura...",
            PHASE_MENU:      "NON IN PARTITA (menu)",
            PHASE_LOBBY:     "PRE-LOBBY (attesa giocatori) - bot fermo",
            PHASE_IMPOSTOR:  "IMPOSTORE - bot inattivo",
            PHASE_VOTING:    "IN VOTAZIONE - bot in pausa",
            PHASE_GHOST:     "FANTASMA - task in linea retta",
            PHASE_ACTIVE:    "IN PARTITA - bot attivo",
            PHASE_POST_VOTE: "Ripresa fra poco (post-voto)...",
        }.get(phase, "Stato: ?")

    def _get_phase_color(self):
        """Colore RGBA da usare per il banner della fase."""
        phase = getattr(self, '_game_phase', PHASE_UNKNOWN)
        return {
            PHASE_UNKNOWN:   (150, 150, 150),
            PHASE_MENU:      (100, 100, 100),
            PHASE_LOBBY:     (180, 140, 80),
            PHASE_IMPOSTOR:  (220, 60, 60),
            PHASE_VOTING:    (220, 180, 60),
            PHASE_GHOST:     (140, 200, 220),
            PHASE_ACTIVE:    (100, 220, 120),
            PHASE_POST_VOTE: (180, 180, 100),
        }.get(phase, (150, 150, 150))

    # ============================================================
    # REAZIONI A EVENTI (meeting / morte)
    # ============================================================

    def _interrompi_task_per_meeting(self):
        """
        Abbandona immediatamente la task in corso quando parte un meeting.

        Sequenza:
          1. Premi ESC sul gioco (chiude il minigioco eventualmente aperto,
             cosi' non resta a schermo durante il meeting).
          2. Ferma il subprocess della task (senza marcarla done: cosi'
             potra' essere ri-eseguita dopo il meeting).
          3. Annulla la navigazione in corso e chiude il popup di lancio.

        Auto-All NON viene disattivato: alla fine del meeting (POST_VOTE ->
        ACTIVE) riprende da solo e ri-pianifica.
        """
        print("[GameState] Meeting rilevato -> abbandono task corrente",
              flush=True)

        # 1) ESC sul gioco per chiudere un eventuale minigioco aperto.
        if _WIN_OK:
            try:
                pyautogui.press('esc')
            except Exception as e:
                print(f"[GameState] ESC fallito: {e}", flush=True)
            try:
                # rilascio anche il mouse, se era premuto in un drag
                pyautogui.mouseUp(button='left')
            except Exception:
                pass

        # 2) Ferma il subprocess (success=False -> task NON marcata done).
        try:
            self._ferma_processo_task()
        except Exception as e:
            print(f"[GameState] stop task fallito: {e}", flush=True)

        # 3) Annulla navigazione + popup. Lascio Auto-All attivo: riprendera'
        #    da solo a meeting finito.
        try:
            self._cancel_auto_move(silent=True, stop_auto_all=False)
        except Exception:
            pass
        self._task_launch_arrivo = False
        if dpg.does_item_exist("task_launch_popup"):
            dpg.delete_item("task_launch_popup")
        self.auto_status_msg = "Meeting: task interrotta, riprendo dopo"

    def _ricomincia_giro_da_fantasma(self):
        """
        Quando il crewmate muore (ACTIVE -> GHOST), la task in corso si
        chiude da sola. Da fantasma si possono ancora completare le task,
        quindi facciamo ripartire il giro:

          1. Ferma il subprocess / la navigazione correnti (cleanup).
          2. Azzera SOLO lo stato di navigazione corrente (non i cooldown
             ne' le task completate: quelle restano valide anche da morto).
          3. Se Auto-All era attivo, lo lascia attivo: il prossimo tick di
             `_update_auto_all` ripianifichera' partendo dalla posizione
             attuale, in modalita' fantasma (linea retta, attraversa muri).

        Se Auto-All NON era attivo, non forziamo nulla: l'utente puo'
        riattivarlo a mano o lanciare le singole task.
        """
        print("[GameState] Morte rilevata -> ricomincio il giro da fantasma",
              flush=True)
        try:
            self._ferma_processo_task()
        except Exception:
            pass
        try:
            self._cancel_auto_move(silent=True, stop_auto_all=False)
        except Exception:
            pass
        self._task_launch_arrivo = False
        if dpg.does_item_exist("task_launch_popup"):
            dpg.delete_item("task_launch_popup")
        # Reset del solo target di navigazione corrente.
        if hasattr(self, '_current_nav_target'):
            self._current_nav_target = None
        self._current_auto_all_task_id = None
        if getattr(self, 'auto_execute_all', False):
            self.auto_status_msg = "Fantasma: riprendo il giro delle task"
        else:
            self.auto_status_msg = "Sei fantasma: puoi completare le task rimaste"
