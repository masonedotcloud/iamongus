"""
Popup di registrazione task sconosciuta + relazioni padre/figlio.

Mixin di GPSVisualizerPro.
"""

from ._imports import *


class TasksPopupsRegisterMixin:
    """Mixin con i metodi di tasks popups register di GPSVisualizerPro."""
    def _registra_task_sconosciuta(self):
        """
        Se la task selezionata in memoria non e' mappata, apre il popup
        di registrazione pre-compilato con nome, tipo e id_stanza (identificatori univoci).
        """
        t = self._get_selected_mem_task()
        if t is None:
            self.auto_status_msg = "Seleziona una task dalla lista"
            return
        if t.get('reg_task') is not None:
            self.auto_status_msg = f"'{t['nome']}' è già registrata"
            return

        # Dati univoci e persistenti della task
        tipo_id = t.get('tipo')
        id_stanza = t.get('id_stanza')

        tag = "popup_registra_sconosciuta"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        px, py = self.pos_target
        vp_w   = dpg.get_viewport_client_width()
        vp_h   = dpg.get_viewport_client_height()

        # --- Zona rilevata automaticamente dalla posizione attuale ---
        zona_now  = self._zona_alla_posizione(px, py)
        gz_id_now = zona_now.get('game_zone_id') if zona_now else None
        zl_id_now = zona_now['id']               if zona_now else None

        # Pre-compila nome vuoto per far scegliere all'utente
        nome_default = ""

        if zona_now:
            gz_str    = f"  GZ:{gz_id_now}" if gz_id_now is not None else "  (nessun game_zone_id)"
            zona_info = f"[{zl_id_now:02d}] {zona_now['nome']}{gz_str}"
            col_zona  = Colors.ACCENT
        else:
            zona_info = "Fuori da qualsiasi zona - id_zona non impostato"
            col_zona  = (200, 120, 30, 255)

        def do_salva(*_):
            """Callback del bottone Salva del popup."""
            nome_v      = dpg.get_value("rs_nome").strip()
            x_v         = dpg.get_value("rs_x")
            y_v         = dpg.get_value("rs_y")
            vitale_v    = dpg.get_value("rs_vitale")
            due_p_v     = dpg.get_value("rs_due_p")
            if not nome_v:
                return

            # Ricalcola la zona basandosi sulle coordinate finali scelte nel popup
            zona_s  = self._zona_alla_posizione(x_v, y_v) or zona_now
            gz_id_s = zona_s.get('game_zone_id') if zona_s else gz_id_now
            zl_id_s = zona_s['id']               if zona_s else zl_id_now

            # Salvataggio tramite TaskManager usando i nuovi parametri
            self.task_mgr.aggiungi(
                nome_v, x_v, y_v,
                id_stanza       = id_stanza,
                tipo          = tipo_id,
                id_zona       = gz_id_s,
                id_zona_locale = zl_id_s,
                nome_zona     = zona_s['nome'] if zona_s else None,
                vitale        = vitale_v,
                due_giocatori = due_p_v,
            )
            self._refresh_reg_task_listbox()
            self._refresh_mem_task_listbox()
            
            zona_msg = f" in '{zona_s['nome']}'" if zona_s else ""
            self.auto_status_msg = (f"Task '{nome_v}' registrata{zona_msg}  "
                                    f"tipo={tipo_id}  room={id_stanza}")
            if dpg.does_item_exist(tag):
                dpg.delete_item(tag)

        def do_usa_pos(*_):
            """Callback del bottone \"Usa posizione attuale\"."""
            nx = round(self.pos_target[0], 3)
            ny = round(self.pos_target[1], 3)
            dpg.set_value("rs_x", nx)
            dpg.set_value("rs_y", ny)
            
            # Aggiorna label della zona in tempo reale se il giocatore si sposta
            z2 = self._zona_alla_posizione(nx, ny)
            if z2:
                gz2   = z2.get('game_zone_id')
                info2 = f"[{z2['id']:02d}] {z2['nome']}" + (f"  GZ:{gz2}" if gz2 is not None else "")
            else:
                info2 = "Fuori da qualsiasi zona"
            if dpg.does_item_exist("rs_zona_info"):
                dpg.set_value("rs_zona_info", info2)

        # Mostriamo gli ID utili a schermo per debug e chiarezza
        id_str = f"Task Type: {tipo_id}  |  Room ID: {id_stanza}"
        with dpg.window(label="Registra Task", tag=tag,
                        modal=True, no_resize=True, no_collapse=True,
                        width=400, height=315,
                        pos=(max(0, vp_w // 2 - 200), max(0, vp_h // 2 - 147))):
            dpg.add_text(id_str, color=Colors.ACCENT)
            dpg.add_text("Zona rilevata automaticamente:", color=Colors.TEXT_DIM)
            dpg.add_text(zona_info, tag="rs_zona_info", color=col_zona)
            dpg.add_separator()
            dpg.add_text("Nome  (puoi modificarlo):")
            dpg.add_input_text(tag="rs_nome", default_value=nome_default, width=-1)
            dpg.add_spacer(height=4)
            dpg.add_text("Coordinate:")
            with dpg.group(horizontal=True):
                dpg.add_text("X:")
                dpg.add_input_float(tag="rs_x", default_value=round(px, 3), width=155, step=0)
                dpg.add_text("Y:")
                dpg.add_input_float(tag="rs_y", default_value=round(py, 3), width=155, step=0)
            dpg.add_button(label="Usa posizione attuale  (aggiorna zona)", width=-1,
                           callback=do_usa_pos)
            dpg.add_spacer(height=6)
            dpg.add_checkbox(tag="rs_vitale", label=" Task di VITALE importanza  [!]",
                             default_value=False)
            dpg.add_checkbox(tag="rs_due_p", label=" Richiede due giocatori  [2P]",
                             default_value=False)
            dpg.add_spacer(height=6)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Salva", width=195, callback=do_salva)
                dpg.add_button(label="Annulla", width=195,
                               callback=lambda *a: dpg.delete_item(tag)
                               if dpg.does_item_exist(tag) else None)

    def _apri_popup_padre_figlia(self):
        """
        Finestra non-modale che mostra tutte le task registrate come card,
        raggruppate in FAMIGLIE (padre + figlie) e TASK LIBERE.
        Permette di collegare/scollegare relazioni padre-figlia con due click:
          1. Clicca "Imposta come PADRE" su una task
          2. Clicca "<- Collega come figlia" su un'altra
        """
        TAG_WIN    = "popup_relazioni_task"
        TAG_SCROLL = "rel_cards_scroll"
        TAG_STATUS = "rel_status_txt"
        WIN_W, WIN_H = 860, 700
        if dpg.does_item_exist(TAG_WIN):
            dpg.delete_item(TAG_WIN)

        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()

        # Stato condiviso tra i callback: quale task e' "padre pending"
        state = {'pending': None}   # None oppure id_task

        # ── Helper stato / refresh ─────────────────────────────────────────

        def _status(msg, col=None):
            """Aggiorna il messaggio di stato del popup."""
            if dpg.does_item_exist(TAG_STATUS):
                dpg.set_value(TAG_STATUS, msg)
                if col:
                    # Cambia le configurazioni di un widget gia' creato
                    dpg.configure_item(TAG_STATUS, color=col)

        def _refresh(*_):
            """Ricostruisce le card della lista task (chiamare dopo CRUD o cambio di stato)."""
            if not dpg.does_item_exist(TAG_SCROLL):
                return
            dpg.delete_item(TAG_SCROLL, children_only=True)
            _build_cards()

        # ── Callback bottoni ──────────────────────────────────────────────

        def _cb_imposta_padre(sender, app_data, tid):
            """Callback: imposta la task selezionata come padre della corrente."""
            t = self.task_mgr.get_by_id(tid)
            state['pending'] = tid
            _status(
                f"PADRE selezionato: [{tid:02d}] {t['nome']}  "
                f"->  clicca '<- Collega come figlia' sulla task da collegare",
                (255, 200, 0))
            _refresh()

        def _cb_collega_figlia(sender, app_data, id_figlia):
            """Callback: collega una nuova figlia alla task corrente."""
            id_padre = state['pending']
            if id_padre is None:
                return
            # Imposta il padre della task (per ereditarieta' delle azioni)
            ok = self.task_mgr.imposta_padre(id_figlia, id_padre)
            if ok:
                state['pending'] = None
                p = self.task_mgr.get_by_id(id_padre)
                f = self.task_mgr.get_by_id(id_figlia)
                _status(
                    f"OK  [{id_figlia:02d}] {f['nome']}  "
                    f"collegata come figlia di  [{id_padre:02d}] {p['nome']}",
                    (0, 220, 120))
                self._refresh_reg_task_listbox()
                self._refresh_mem_task_listbox()
            else:
                _status(
                    "X  Collegamento non valido: self-loop, "
                    "catena multi-livello, o padre gia' figlia di qualcuno",
                    (255, 100, 80))
            _refresh()

        def _cb_scollega(sender, app_data, tid):
            """Callback: scollega la relazione padre-figlia."""
            # Imposta il padre della task (per ereditarieta' delle azioni)
            self.task_mgr.imposta_padre(tid, None)
            state['pending'] = None
            t = self.task_mgr.get_by_id(tid)
            _status(f"[{tid:02d}] {t['nome']} scollegata dal padre",
                    Colors.TEXT_DIM)
            self._refresh_reg_task_listbox()
            self._refresh_mem_task_listbox()
            _refresh()

        def _cb_annulla(*_):
            """Callback di annullamento (chiude il popup)."""
            state['pending'] = None
            _status(
                "Seleziona una task come PADRE per iniziare il collegamento",
                Colors.TEXT_DIM)
            _refresh()

        def _cb_modifica(sender, app_data, tid):
            """Callback: apre il popup di modifica della task."""
            self._apri_popup_modifica_task(task=self.task_mgr.get_by_id(tid))

        # ── Costruzione card singola ───────────────────────────────────────

        def _card(t, indented=False, padre_nome=None):
            """Renderizza una "card" task nel layout padre/figlia."""
            tid    = t['id']
            nome   = t['nome']
            zona   = t.get('nome_zona') or '-'
            n_az   = len(t.get('azioni', []))
            _, src = self.task_mgr.get_azioni_effettive(tid)
            figli  = self.task_mgr.get_figli(tid)
            pid    = state['pending']

            # Colore della card
            if tid == pid:
                col_id = (255, 200, 0)    # giallo: padre selezionato
            elif figli:
                col_id = (80, 180, 255)   # azzurro: e' padre
            elif t.get('id_padre'):
                col_id = (120, 220, 120)  # verde: e' figlia
            else:
                col_id = (190, 190, 190)  # grigio: libera

            # Stringa azioni
            if n_az > 0:
                az_str = f"A:{n_az}"
            elif src and src != tid:
                az_str = f"A:0<-P{src:02d}"
            else:
                az_str = "A:0"

            indent_txt = "    ->  " if indented else ""

            with dpg.group(horizontal=False, parent=TAG_SCROLL):
                # ── Riga 1: id + nome + badge ──
                with dpg.group(horizontal=True):
                    dpg.add_text(f"{indent_txt}[{tid:02d}]", color=col_id)
                    dpg.add_text(f"  {nome}")
                    dpg.add_text(f"   {az_str}", color=(100, 200, 255))
                    if t.get('vitale'):
                        dpg.add_text("  [!]",  color=(255, 80, 80))
                    if t.get('due_giocatori'):
                        dpg.add_text("  [2P]", color=(255, 200, 80))

                # ── Riga 2: dettagli ──
                dettagli = f"      Zona: {zona}"
                if padre_nome:
                    dettagli += f"   |   Padre: {padre_nome}"
                if figli:
                    nomi_f = ", ".join(f"[{f['id']:02d}] {f['nome']}"
                                       for f in figli[:4])
                    if len(figli) > 4:
                        nomi_f += f"  (+{len(figli)-4})"
                    dettagli += f"   |   Figli: {nomi_f}"
                dpg.add_text(dettagli, color=Colors.TEXT_DIM)

                # ── Riga 3: bottoni ──
                with dpg.group(horizontal=True):
                    if pid is None:
                        # Nessun padre in selezione
                        if not t.get('id_padre'):
                            # Puo' diventare padre (non e' gia' figlia di nessuno)
                            dpg.add_button(
                                label="Imposta come PADRE",
                                user_data=tid,
                                callback=_cb_imposta_padre,
                                width=155, height=22)
                        if t.get('id_padre'):
                            # È gia' figlia: offri di scollegarla
                            dpg.add_button(
                                label="Scollega dal padre",
                                user_data=tid,
                                callback=_cb_scollega,
                                width=140, height=22)
                    else:
                        # Un padre e' selezionato
                        if tid == pid:
                            dpg.add_text("[PADRE SELEZIONATO]",
                                         color=(255, 200, 0))
                            dpg.add_button(
                                label="Annulla",
                                callback=_cb_annulla,
                                width=70, height=22)
                        elif not t.get('id_padre') and not figli:
                            # Task libera: puo' diventare figlia
                            dpg.add_button(
                                label=f"<- Collega come figlia di [{pid:02d}]",
                                user_data=tid,
                                callback=_cb_collega_figlia,
                                width=230, height=22)
                        elif t.get('id_padre'):
                            dpg.add_text("(ha già un padre)",
                                         color=Colors.TEXT_DIM)
                        elif figli:
                            dpg.add_text("(è padre: non può diventare figlia)",
                                         color=Colors.TEXT_DIM)

                    # Modifica sempre disponibile
                    dpg.add_button(
                        label="Modifica",
                        user_data=tid,
                        callback=_cb_modifica,
                        width=75, height=22)

                dpg.add_separator()

        # ── Costruzione completa lista card ───────────────────────────────

        def _build_cards():
            """Costruisce le card di tutte le task per il popup padre/figlia."""
            tasks  = self.task_mgr.task_list
            padri  = [t for t in tasks
                      if self.task_mgr.get_figli(t['id']) and not t.get('id_padre')]
            orfane = [t for t in tasks
                      if not self.task_mgr.get_figli(t['id']) and not t.get('id_padre')]

            if not tasks:
                with dpg.group(parent=TAG_SCROLL):
                    dpg.add_text("Nessuna task registrata ancora.",
                                 color=Colors.TEXT_DIM)
                return

            # Riepilogo numerico
            n_famiglie = len(padri)
            n_figli    = sum(len(self.task_mgr.get_figli(p['id'])) for p in padri)
            n_libere   = len(orfane)
            with dpg.group(horizontal=True, parent=TAG_SCROLL):
                dpg.add_text(
                    f"Totale: {len(tasks)} task   |   "
                    f"{n_famiglie} famiglie ({n_figli} figlie)   |   "
                    f"{n_libere} libere",
                    color=Colors.TEXT_DIM)
            with dpg.group(parent=TAG_SCROLL):
                dpg.add_spacer(height=6)

            # ─── Sezione FAMIGLIE ───────────────────────────────────────
            if padri:
                with dpg.group(parent=TAG_SCROLL):
                    dpg.add_text("FAMIGLIE  -  padre con le sue figlie",
                                 color=(80, 180, 255))
                    dpg.add_separator()
                    dpg.add_spacer(height=4)

                for padre in padri:
                    _card(padre)
                    for figlia in self.task_mgr.get_figli(padre['id']):
                        _card(figlia, indented=True, padre_nome=padre['nome'])
                    with dpg.group(parent=TAG_SCROLL):
                        dpg.add_spacer(height=8)

            # ─── Sezione TASK LIBERE ────────────────────────────────────
            if orfane:
                with dpg.group(parent=TAG_SCROLL):
                    dpg.add_spacer(height=4)
                    dpg.add_text("TASK LIBERE  -  senza relazioni",
                                 color=(190, 190, 190))
                    dpg.add_separator()
                    dpg.add_spacer(height=4)
                for t in orfane:
                    _card(t)

        # ── Finestra ──────────────────────────────────────────────────────

        with dpg.window(
                label="Relazioni Task  -  Padre <-> Figlia",
                tag=TAG_WIN,
                width=WIN_W, height=WIN_H,
                pos=(max(0, vp_w // 2 - WIN_W // 2),
                     max(0, vp_h // 2 - WIN_H // 2)),
                no_collapse=True,
                on_close=lambda *a: (dpg.delete_item(TAG_WIN)
                                     if dpg.does_item_exist(TAG_WIN) else None)):

            dpg.add_text("GESTIONE RELAZIONI  PADRE <-> FIGLIA",
                         color=Colors.ACCENT)
            dpg.add_separator()

            # Barra di stato / istruzioni
            dpg.add_text(
                "Seleziona una task come PADRE per iniziare il collegamento",
                tag=TAG_STATUS, color=Colors.TEXT_DIM, wrap=WIN_W - 30)

            dpg.add_spacer(height=4)
            with dpg.group(horizontal=True):
                dpg.add_button(label="Annulla selezione",
                               callback=_cb_annulla,
                               width=150, height=26)
                dpg.add_button(label="Aggiorna vista",
                               callback=_refresh,
                               width=120, height=26)
                dpg.add_button(
                    label="Chiudi",
                    callback=lambda *a: (dpg.delete_item(TAG_WIN)
                                         if dpg.does_item_exist(TAG_WIN) else None),
                    width=90, height=26)
            dpg.add_separator()
            dpg.add_spacer(height=4)

            # Area scrollabile con le card
            with dpg.child_window(tag=TAG_SCROLL, width=-1, height=-1):
                pass

            _build_cards()
