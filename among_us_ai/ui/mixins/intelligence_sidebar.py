"""
Intelligence Sidebar: pannello laterale con info strategiche sui player.

Mostra una sidebar in DPG (apribile con F2) con:
- Lista di tutti i player conosciuti, ordinati per sospettosita' decrescente
- Per ogni player:
  * Nome + colore + barra sospettosita' (0-100%)
  * Verdetto qualitativo (safe/sus/super_sus)
  * Ultima posizione + secondi dall'ultimo avvistamento
  * Task probabilmente fatte (numero)
  * Tempo speso vicino a me (follow score)
  * Mini-cronologia ultime 3 posizioni

Si aggiorna a 2 Hz (ogni 500ms) per non pesare sul rendering.
"""

from ._imports import *
import time as _time


# Tag del pannello (univoco)
SIDEBAR_TAG = "intelligence_sidebar_window"
SIDEBAR_CONTENT_TAG = "intelligence_sidebar_content"


class IntelligenceSidebarMixin:
    """Mixin con i metodi della sidebar di intelligence (F2)."""

    # ============================================================
    # TOGGLE / SHOW / HIDE
    # ============================================================

    def _toggle_intelligence_sidebar(self):
        """Apre/chiude la sidebar di intelligence (callback F2)."""
        print("[Intelligence] F2 premuto / toggle sidebar", flush=True)
        if not getattr(self, '_intelligence_enabled', False):
            print("[Intelligence] Disabilitata via config "
                  "(INTELLIGENCE_ENABLED=False)", flush=True)
            return
        if dpg.does_item_exist(SIDEBAR_TAG):
            print("[Intelligence] Sidebar gia' aperta, la chiudo",
                  flush=True)
            dpg.delete_item(SIDEBAR_TAG)
            self._intelligence_sidebar_open = False
            return
        print("[Intelligence] Apro sidebar", flush=True)
        self._intelligence_sidebar_open = True
        self._intelligence_update_timer = 0.0
        self._build_intelligence_sidebar()

    def _build_intelligence_sidebar(self):
        """Costruisce la finestra DPG della sidebar (una volta)."""
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        w = getattr(GPSConfig, 'INTELLIGENCE_SIDEBAR_WIDTH', 320)
        h = vp_h - 80  # tutta l'altezza meno barra menu + status bar

        # Pannello visibile: NIENTE no_focus_on_appearing /
        # no_bring_to_front_on_focus, altrimenti la finestra resta
        # nascosta dietro al canvas della mappa che occupa lo schermo.
        with dpg.window(label="Intelligence ([F2] chiude)",
                        tag=SIDEBAR_TAG,
                        no_close=False,
                        no_resize=True,
                        no_collapse=False,
                        width=w, height=h,
                        pos=(10, 40),
                        on_close=lambda *a: self._on_close_intelligence()):
            # Header
            dpg.add_text("ANALISI PLAYER", color=Colors.ACCENT)
            dpg.add_text("Premi F2 (o X) per chiudere",
                         color=Colors.TEXT_DIM)
            dpg.add_separator()

            # === OPZIONI ===
            with dpg.group(horizontal=False):
                dpg.add_checkbox(
                    label="Evita player sospetti (path-aware)",
                    tag="intel_avoid_suspects_chk",
                    default_value=bool(getattr(self, '_avoid_suspects', False)),
                    callback=lambda s, app, ud: setattr(
                        self, '_avoid_suspects', bool(app)),
                )
                dpg.add_text("  Il bot evita di passare sopra i player",
                              color=Colors.TEXT_DIM)
                dpg.add_text("  con sospetto > 40% (sorpasso laterale).",
                              color=Colors.TEXT_DIM)
            dpg.add_separator()

            # Container per la lista (riempito dinamicamente)
            with dpg.child_window(tag=SIDEBAR_CONTENT_TAG,
                                   border=False,
                                   width=-1, height=-1):
                dpg.add_text("In attesa di rilevamenti player...",
                              color=Colors.TEXT_DIM,
                              tag="intel_empty_msg")

    def _on_close_intelligence(self):
        """Callback alla chiusura con la X del pannello."""
        self._intelligence_sidebar_open = False

    # ============================================================
    # UPDATE LOOP
    # ============================================================

    def _update_intelligence_sidebar(self, dt):
        """
        Aggiorna i dati della sidebar.

        Chiamato da loop principale. Aggiorna a frequenza ridotta
        (default 2 Hz) per non pesare sul rendering.
        Aggiorna anche i moduli intelligence (tracker -> activity ->
        proximity -> task_inf) regolarmente, anche se la sidebar
        e' chiusa: l'analisi avanza in background.
        """
        if not getattr(self, '_intelligence_enabled', False):
            return

        # Throttle: aggiorna i moduli ogni 0.5s
        self._intelligence_update_timer = (
            getattr(self, '_intelligence_update_timer', 0.0) + dt
        )
        interval = 1.0 / getattr(GPSConfig, 'INTELLIGENCE_REFRESH_HZ', 2.0)
        if self._intelligence_update_timer < interval:
            return
        self._intelligence_update_timer = 0.0

        # GUARD fase: pausa il tracking durante lobby/voto/impostore/morto.
        # NON azzero i dati accumulati: solo non aggiorno. Cosi' quando
        # ritorniamo in partita la storia precedente e' intatta.
        # Il rendering della sidebar (se aperta) continua mostrando gli
        # ultimi dati conosciuti.
        if hasattr(self, '_intelligence_should_run'):
            if not self._intelligence_should_run():
                # Aggiorno solo il rendering della sidebar se aperta
                if (getattr(self, '_intelligence_sidebar_open', False)
                        and dpg.does_item_exist(SIDEBAR_TAG)):
                    self._render_intelligence_sidebar()
                return

        # === Aggiornamento moduli intelligence ===
        try:
            self._intelligence_feed_tracker()
            self._intelligence_activity.update(
                self._intelligence_tracker,
                bot_pos=self.pos_target)
            self._intelligence_proximity.update(
                self._intelligence_tracker, self.pos_target)
            self._intelligence_task_inf.update(self._intelligence_tracker)
        except Exception as e:
            print(f"[Intelligence] Errore update moduli: {e}", flush=True)
            return

        # === Aggiorna la UI solo se la sidebar e' aperta ===
        if not getattr(self, '_intelligence_sidebar_open', False):
            return
        if not dpg.does_item_exist(SIDEBAR_TAG):
            self._intelligence_sidebar_open = False
            return

        self._render_intelligence_sidebar()

    def _intelligence_feed_tracker(self):
        """
        Alimenta il PlayerTracker con i player attualmente rilevati.

        Sorgente: `self.detected_players` (gia' popolato dal sistema
        YOLO esistente in `yolo_scanner.py`).
        """
        now = _time.time()
        for dp in getattr(self, 'detected_players', []):
            try:
                self._intelligence_tracker.observe(
                    name=dp.get('name', 'Unknown'),
                    x=dp.get('x', 0.0),
                    y=dp.get('y', 0.0),
                    color=dp.get('color', (128, 128, 128)),
                    t=dp.get('time', now),
                    is_dead=dp.get('is_dead', False),
                )
            except Exception:
                # Detection malformata, skip
                pass

    # ============================================================
    # RENDERING
    # ============================================================

    def _render_intelligence_sidebar(self):
        """Ricostruisce il contenuto della sidebar."""
        if not dpg.does_item_exist(SIDEBAR_CONTENT_TAG):
            return

        # Calcola score per tutti i player
        try:
            scores = self._intelligence_suspicion.analyze_all(
                self._intelligence_tracker,
                self._intelligence_activity,
                self._intelligence_proximity,
                self._intelligence_task_inf,
            )
        except Exception as e:
            print(f"[Intelligence] Errore analyze_all: {e}", flush=True)
            return

        # Pulisco i figli e ricostruisco
        dpg.delete_item(SIDEBAR_CONTENT_TAG, children_only=True)

        # Eventuali player morti separati a parte (in fondo)
        morti = [p for p in self._intelligence_tracker.all_players()
                  if p.is_dead]
        vivi_count = len(self._intelligence_tracker.all_players()) - len(morti)

        if vivi_count == 0:
            dpg.add_text("Nessun player rilevato finora.",
                          parent=SIDEBAR_CONTENT_TAG,
                          color=Colors.TEXT_DIM)
            return

        # === Header con statistiche generali ===
        dpg.add_text(f"Player conosciuti: {vivi_count} vivi, "
                      f"{len(morti)} morti",
                      parent=SIDEBAR_CONTENT_TAG,
                      color=Colors.ACCENT)
        # Gruppi rilevati
        groups = self._intelligence_proximity.detect_groups(
            self._intelligence_tracker)
        if groups:
            grp_str = ", ".join(
                "(" + "+".join(p.name for p in g) + ")"
                for g in groups
            )
            dpg.add_text(f"Gruppi attivi: {grp_str}",
                          parent=SIDEBAR_CONTENT_TAG,
                          color=(255, 200, 80))
        dpg.add_separator(parent=SIDEBAR_CONTENT_TAG)

        # === Per ogni player ===
        now = _time.time()
        for sc in scores:
            player = self._intelligence_tracker.get(sc.player_name)
            if player is None:
                continue
            self._render_player_card(player, sc, now)

        # === Sezione morti ===
        if morti:
            dpg.add_separator(parent=SIDEBAR_CONTENT_TAG)
            dpg.add_text("MORTI",
                          parent=SIDEBAR_CONTENT_TAG,
                          color=(180, 100, 100))
            for p in morti:
                self._render_dead_player_card(p, now)

    def _render_player_card(self, player, score, now):
        """Rendering di una singola card player (vivo)."""
        # Pannello-card per ogni player
        with dpg.group(parent=SIDEBAR_CONTENT_TAG):
            # Riga 1: pallino colorato + nome + score
            with dpg.group(horizontal=True):
                # Pallino: simulato con un draw_circle? Piu' semplice:
                # un quadrato colorato con dpg.add_color_button
                dpg.add_color_button(default_value=(*player.color, 255),
                                       width=22, height=22,
                                       no_border=False)
                # Nome del player
                col_text = self._verdict_color(score.verdict)
                dpg.add_text(player.name, color=col_text)
                # Visibilita'
                if player.is_visible_now(now):
                    dpg.add_text("[VISTO]", color=(80, 220, 120))
                else:
                    secs = player.seconds_since_last_seen(now)
                    dpg.add_text(f"-{secs:.0f}s", color=Colors.TEXT_DIM)

            # Riga 2: barra di sospettosita'
            with dpg.group(horizontal=True):
                dpg.add_text("Sospetto:", color=Colors.TEXT_DIM)
                dpg.add_progress_bar(
                    default_value=score.score / 100.0,
                    overlay=f"{score.score:.0f}% [{score.verdict}]",
                    width=-1,
                )

            # Riga 3: ultimi avvistamenti
            last_pos = player.last_snapshot
            if last_pos:
                stanza = last_pos.stanza or "?"
                dpg.add_text(
                    f"Ultimo: ({last_pos.x:.1f},{last_pos.y:.1f}) {stanza}",
                    color=Colors.TEXT_DIM)

            # Riga 4: fattori che alzano/abbassano lo score
            if score.factors:
                fact_lines = []
                for fname, (count, contrib) in score.factors.items():
                    sign = '+' if contrib >= 0 else ''
                    fact_lines.append(
                        f"  {sign}{contrib:.0f} {self._human_factor(fname)} ({count})"
                    )
                fact_text = "\n".join(fact_lines)
                dpg.add_text(fact_text, color=Colors.TEXT_DIM, wrap=300)

            # Riga 5: task fatte
            n_tasks = self._intelligence_task_inf.task_count(player.name)
            if n_tasks > 0:
                tasks = self._intelligence_task_inf.tasks_of(player.name)
                names = [t.task_name for t in tasks[-3:]]  # ultime 3
                dpg.add_text(f"Task: {n_tasks} ({', '.join(names)})",
                              color=(120, 200, 220))

            # Riga 6: follow score
            follow = self._intelligence_proximity.follow_score(player.name)
            if follow > 5:
                dpg.add_text(f"Mi segue: {follow:.0f}s",
                              color=(255, 180, 100))

            # Mini-cronologia: ultime 3 posizioni
            recent = player.get_last_n_positions(3)
            if len(recent) > 1:
                pos_str = " > ".join(
                    f"({s.x:.0f},{s.y:.0f})"
                    for s in recent
                )
                dpg.add_text(f"Tragitto: {pos_str}",
                              color=Colors.TEXT_DIM, wrap=300)

            dpg.add_separator()

    def _render_dead_player_card(self, player, now):
        """Card piu' compatta per i morti."""
        with dpg.group(parent=SIDEBAR_CONTENT_TAG):
            with dpg.group(horizontal=True):
                dpg.add_color_button(default_value=(*player.color, 255),
                                       width=16, height=16)
                dpg.add_text(f"{player.name} (morto)",
                              color=(180, 100, 100))
            if player.died_pos:
                age = (now - player.died_at) if player.died_at else 0
                dpg.add_text(
                    f"  Visto morto: ({player.died_pos[0]:.1f},"
                    f"{player.died_pos[1]:.1f}) - {age:.0f}s fa",
                    color=Colors.TEXT_DIM)

    # ============================================================
    # HELPERS
    # ============================================================

    @staticmethod
    def _verdict_color(verdict):
        """
        Mapping verdetto -> tupla RGB per evidenziare il giudizio nella UI.

        :param verdict: ``'safe'`` / ``'sus'`` / ``'super_sus'``
        :return: ``(r, g, b)`` (default grigio se verdict sconosciuto).
        """
        return {
            'safe':      (120, 220, 120),
            'sus':       (255, 200, 80),
            'super_sus': (255, 80, 80),
        }.get(verdict, (220, 220, 220))

    @staticmethod
    def _human_factor(fname):
        """Trasforma il nome del fattore in italiano leggibile."""
        return {
            'vent_use':         'vent uses',
            'sudden_disappear': 'sparizioni improvvise',
            'near_body':        'vicino a cadaveri',
            'tasks_done':       'task fatte',
            'following_me':     's vicino a me',
            'alone_with_safe':  's 1v1 vivi (safe)',
            'no_tasks_seen':    's senza task',
        }.get(fname, fname)
