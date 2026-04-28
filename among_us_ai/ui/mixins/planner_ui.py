"""
Pianificatore Auto-All: preview del giro + popup pesi configurabili.

Due popup gestiti da questo mixin:

1. PREVIEW DEL GIRO (tasto F1 o bottone "Mostra preview"):
   Mostra in tempo reale la sequenza ottimale calcolata dal
   `TaskPlanner` con:
   - Lista numerata a sinistra (1, 2, 3, ...) con dettagli per task
     (nome, lunghezza, vitale, distanza dalla precedente, score)
   - Visualizzazione sulla mappa con linee colorate e numeri sui
     pallini delle task (gestita dal `rendering_entities`)

2. POPUP PESI PIANIFICATORE (Strumenti -> Pesi pianificatore Auto-All):
   Slider per modificare in runtime i pesi che influenzano la scelta:
   - peso vitale (default 1000)
   - peso lunghezza (Long, Common, N/A, Short)
   - peso multi-fase (task con cooldown interno)
   - alpha distanza (penalita' della distanza A*)
   Salva su `planner_weights.json` per persistenza fra sessioni.
"""

from ._imports import *
from ...managers.task_planner import carica_pesi_da_config
import json as _json
import os as _os


# File di persistenza dei pesi modificati dall'utente
PLANNER_WEIGHTS_FILE = "planner_weights.json"


class PlannerMixin:
    """Mixin con i metodi di preview e configurazione del pianificatore."""

    # ============================================================
    # PREVIEW DEL GIRO (F1)
    # ============================================================

    def _toggle_preview_giro(self):
        """Apre/chiude il popup di preview del giro Auto-All."""
        tag = "popup_preview_giro"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)
            self._preview_giro_aperto = False
            # Pulisco anche il rendering del giro sulla mappa
            self._giro_preview_lista = []
            self._giro_preview_paths = []
            return
        self._preview_giro_aperto = True
        self._aggiorna_preview_giro()

    def _set_percorso_breve(self, enabled):
        """
        Attiva/disattiva la modalita' "percorso piu' breve" (callback
        checkbox del menu). Imposta ``GPSConfig.PLANNER_PERCORSO_BREVE``:
        i pesi vengono riletti ad ogni scelta del giro, quindi il
        cambiamento ha effetto immediato.

        Se la preview del giro e' aperta, la rinfresco per mostrare
        subito il nuovo ordinamento.
        """
        GPSConfig.PLANNER_PERCORSO_BREVE = bool(enabled)
        stato = "attivo" if enabled else "disattivato"
        self.auto_status_msg = f"Percorso piu' breve: {stato}"
        print(f"[Planner] Percorso piu' breve {stato}", flush=True)
        if getattr(self, '_preview_giro_aperto', False):
            self._aggiorna_preview_giro()

    def _aggiorna_preview_giro(self):
        """
        Ricalcola il giro completo (TaskPlanner.calcola_giro) e aggiorna
        il popup + la lista per il rendering mappa.

        Chiamato:
          - All'apertura del popup
          - Periodicamente quando il popup e' aperto (vedi _update)
          - Dopo cambi di stato delle task
        """
        tag = "popup_preview_giro"

        # 1) Calcolo candidate (stessa logica di _update_auto_all)
        if not self.memory_tasks:
            tasks_per_planner = []
        else:
            enriched = self.task_mgr.get_memory_tasks_info(self.memory_tasks)
            tasks_per_planner = []
            for t in enriched:
                if t.get('done'): continue
                reg = t.get('reg_task')
                if not reg: continue
                import time as _time
                rem = self.task_cooldowns.get(reg['id'], 0) - _time.time()
                if rem > 0: continue
                azioni_eff, _src = self.task_mgr.get_azioni_effettive(reg['id'])
                tasks_per_planner.append({
                    'id':        reg['id'],
                    'nome':      reg.get('nome', '?'),
                    'x':         reg['x'],
                    'y':         reg['y'],
                    'vitale':    bool(reg.get('vitale', False)),
                    'lunghezza': reg.get('lunghezza', 'Short'),
                    'azioni':    azioni_eff,
                })

        # 2) Calcolo del giro
        pesi = carica_pesi_da_config(GPSConfig)
        use_astar = bool(getattr(GPSConfig, 'PLANNER_USE_ASTAR', True))
        giro = self.task_planner.calcola_giro(
            self.pos_target, tasks_per_planner, pesi,
            use_astar=use_astar,
        )

        # Memorizzo per il rendering della mappa (vedi rendering_entities)
        self._giro_preview_lista = giro

        # 2b) PRE-CALCOLO dei path A* per il rendering.
        # Senza questo, _render_giro_preview chiamerebbe astar() ad ogni
        # frame (60 fps) per ogni segmento -> lag pesante. Li calcolo
        # qui UNA VOLTA (refresh ogni 1s) e li passo al render gia' fatti.
        # max_nodes=20000 (default del pathfinder): cerco di trovare
        # SEMPRE un path, anche per task lontane. Se uso meno, le linee
        # appaiono dritte (fallback) anche quando il path esiste.
        paths = []
        prev_x, prev_y = self.pos_target
        for task, _dist, _score in giro:
            tx, ty = task['x'], task['y']
            try:
                path = self.pathfinder.astar(
                    (prev_x, prev_y), (tx, ty), max_nodes=20000)
            except Exception:
                path = None
            paths.append(path)
            prev_x, prev_y = tx, ty
        self._giro_preview_paths = paths

        # 3) Costruisco/aggiorno il popup
        # Se esiste gia', svuoto il contenuto e ricostruisco; altrimenti
        # creo da zero.
        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        win_w, win_h = 480, min(700, vp_h - 100)

        if dpg.does_item_exist(tag):
            # Pulisco i figli e ricostruisco
            dpg.delete_item(tag, children_only=True)
            parent = tag
        else:
            with dpg.window(label="Preview giro Auto-All",
                            tag=tag,
                            width=win_w, height=win_h,
                            pos=(20, 50),
                            no_close=False,
                            on_close=lambda *a: self._on_close_preview_giro()):
                pass
            parent = tag

        # Riempio il contenuto
        if not giro:
            dpg.add_text("Nessuna task disponibile.", parent=parent,
                         color=Colors.TEXT_DIM)
            dpg.add_text("(tutte completate, in cooldown, o non registrate)",
                         parent=parent, color=Colors.TEXT_DIM)
        else:
            dpg.add_text(f"Sequenza ottimale ({len(giro)} task):",
                         parent=parent, color=Colors.ACCENT)
            dpg.add_separator(parent=parent)

            # Distanza totale stimata
            tot_dist = sum(d for _t, d, _s in giro)
            dpg.add_text(f"Distanza totale stimata: {tot_dist:.1f} unita'",
                         parent=parent, color=Colors.TEXT_DIM)
            dpg.add_separator(parent=parent)

            # Lista numerata
            for i, (task, dist, score) in enumerate(giro, 1):
                vitale_tag = "[VITALE] " if task.get('vitale') else ""
                lung = task.get('lunghezza', '?')
                multi = " [multi-fase]" if any(
                    a.get('tipo') == 'cooldown' for a in task.get('azioni', [])
                ) else ""

                # Colore: vitali in rosso, multi-fase in giallo, altri normali
                if task.get('vitale'):
                    col = (255, 100, 100, 255)
                elif multi:
                    col = (255, 200, 100, 255)
                else:
                    col = Colors.TEXT

                dpg.add_text(
                    f"{i:2d}. {vitale_tag}{task['nome']} ({lung}){multi}",
                    parent=parent, color=col)
                dpg.add_text(
                    f"     dist={dist:.1f}  score={score:.1f}",
                    parent=parent, color=Colors.TEXT_DIM)

        dpg.add_separator(parent=parent)
        dpg.add_text("Premi F1 per chiudere | Pesi: Strumenti -> Pesi pianificatore",
                     parent=parent, color=Colors.TEXT_DIM)

    def _on_close_preview_giro(self):
        """Callback alla chiusura del popup (X o F1)."""
        self._preview_giro_aperto = False
        self._giro_preview_lista = []
        self._giro_preview_paths = []

    def _update_preview_giro(self, dt):
        """
        Aggiorna periodicamente il popup di preview giro quando aperto.
        Chiamato dal render loop principale.

        Refresh ogni 1 secondo: il giro puo' cambiare se spawnano nuove
        task vitali, si completano task, ecc.
        """
        if not getattr(self, '_preview_giro_aperto', False):
            return
        self._preview_giro_refresh_timer = (
            getattr(self, '_preview_giro_refresh_timer', 0.0) + dt
        )
        if self._preview_giro_refresh_timer < 1.0:
            return
        self._preview_giro_refresh_timer = 0.0
        # Ricalcolo SOLO se il popup esiste ancora
        if dpg.does_item_exist("popup_preview_giro"):
            self._aggiorna_preview_giro()
        else:
            self._preview_giro_aperto = False

    # ============================================================
    # POPUP PESI PIANIFICATORE
    # ============================================================

    def _apri_popup_pesi_pianificatore(self):
        """Apre il popup di configurazione dei pesi del planner."""
        tag = "popup_pesi_planner"
        if dpg.does_item_exist(tag):
            dpg.delete_item(tag)

        vp_w = dpg.get_viewport_client_width()
        vp_h = dpg.get_viewport_client_height()
        win_w, win_h = 580, 620

        with dpg.window(label="Come scegliere le task",
                        tag=tag,
                        modal=True,
                        width=win_w, height=win_h,
                        pos=((vp_w - win_w) // 2, (vp_h - win_h) // 2)):

            # === SPIEGAZIONE INIZIALE ===
            dpg.add_text("Imposta quanto è importante ogni cosa per il bot",
                         color=Colors.ACCENT)
            dpg.add_text("quando deve scegliere quale task fare per prima.",
                         color=Colors.TEXT_DIM)
            dpg.add_separator()

            # === 1. SABOTAGGI ===
            with dpg.collapsing_header(
                    label="Quanto urgenti sono i sabotaggi",
                    default_open=True):
                dpg.add_text("Quando c'è un sabotaggio (es. ossigeno",
                             color=Colors.TEXT_DIM)
                dpg.add_text("che cala, reattore in fusione), il bot deve",
                             color=Colors.TEXT_DIM)
                dpg.add_text("interrompere tutto e correre a sistemarlo.",
                             color=Colors.TEXT_DIM)
                dpg.add_spacer(height=8)
                dpg.add_text("Importanza dei sabotaggi:", color=(255, 100, 100))
                dpg.add_slider_float(
                    tag="pp_vitale",
                    default_value=float(GPSConfig.PLANNER_PESO_VITALE),
                    min_value=0.0, max_value=5000.0,
                    format="%.0f",
                    width=-1,
                )
                dpg.add_text("  Più alto = il bot li priorizza sempre",
                              color=Colors.TEXT_DIM)
                dpg.add_text("  Valore consigliato: 1000",
                              color=Colors.TEXT_DIM)

            # === 2. TASK LUNGHE/CORTE ===
            with dpg.collapsing_header(
                    label="Quale tipo di task fare prima",
                    default_open=True):
                dpg.add_text("Alcune task durano poco (es. timbrare il",
                             color=Colors.TEXT_DIM)
                dpg.add_text("badge), altre sono lunghe (es. sistemare",
                             color=Colors.TEXT_DIM)
                dpg.add_text("i cavi). Più alto il valore, più il bot",
                             color=Colors.TEXT_DIM)
                dpg.add_text("preferisce fare quel tipo per primo.",
                             color=Colors.TEXT_DIM)
                dpg.add_spacer(height=8)

                # Long
                dpg.add_text("Task LUNGHE (es. cavi, ispezione campione):",
                              color=(180, 220, 255))
                dpg.add_slider_float(
                    tag="pp_long",
                    default_value=float(GPSConfig.PLANNER_PESO_LONG),
                    min_value=0.0, max_value=200.0,
                    format="%.0f",
                    width=-1,
                )

                dpg.add_spacer(height=8)

                # Common
                dpg.add_text("Task COMUNI a tutti (es. timbra badge):",
                              color=(180, 220, 255))
                dpg.add_slider_float(
                    tag="pp_common",
                    default_value=float(GPSConfig.PLANNER_PESO_COMMON),
                    min_value=0.0, max_value=200.0,
                    format="%.0f",
                    width=-1,
                )

                dpg.add_spacer(height=8)

                # N/A
                dpg.add_text("Sabotaggi piccoli (es. luci, comunicazioni):",
                              color=(180, 220, 255))
                dpg.add_slider_float(
                    tag="pp_na",
                    default_value=float(GPSConfig.PLANNER_PESO_NA),
                    min_value=0.0, max_value=200.0,
                    format="%.0f",
                    width=-1,
                )

                dpg.add_spacer(height=8)

                # Short
                dpg.add_text("Task CORTE (es. download dati, deviare energia):",
                              color=(180, 220, 255))
                dpg.add_slider_float(
                    tag="pp_short",
                    default_value=float(GPSConfig.PLANNER_PESO_SHORT),
                    min_value=0.0, max_value=200.0,
                    format="%.0f",
                    width=-1,
                )
                dpg.add_spacer(height=8)
                dpg.add_text("  Valori consigliati: Lunghe 30, Comuni 20,",
                              color=Colors.TEXT_DIM)
                dpg.add_text("  Sabotaggi piccoli 25, Corte 10",
                              color=Colors.TEXT_DIM)

            # === 3. TASK CON ATTESA ===
            with dpg.collapsing_header(
                    label="Task con attesa interna",
                    default_open=False):
                dpg.add_text("Alcune task hanno un'attesa al loro interno",
                             color=Colors.TEXT_DIM)
                dpg.add_text("(es. analizzare campioni in medbay).",
                             color=Colors.TEXT_DIM)
                dpg.add_text("Conviene farle quando il bot è nei paraggi,",
                             color=Colors.TEXT_DIM)
                dpg.add_text("per non sprecare il tempo di attesa.",
                             color=Colors.TEXT_DIM)
                dpg.add_spacer(height=8)
                dpg.add_text("Bonus per queste task:",
                              color=(255, 200, 100))
                dpg.add_slider_float(
                    tag="pp_multi",
                    default_value=float(GPSConfig.PLANNER_PESO_MULTI),
                    min_value=0.0, max_value=200.0,
                    format="%.0f",
                    width=-1,
                )
                dpg.add_text("  Valore consigliato: 15",
                              color=Colors.TEXT_DIM)

            # === 4. DISTANZE ===
            with dpg.collapsing_header(
                    label="Quanto contano le distanze",
                    default_open=True):
                dpg.add_text("Quanto è importante per il bot che la",
                             color=Colors.TEXT_DIM)
                dpg.add_text("prossima task sia vicina (rispetto a una",
                             color=Colors.TEXT_DIM)
                dpg.add_text("lontana ma più importante).",
                             color=Colors.TEXT_DIM)
                dpg.add_spacer(height=8)
                dpg.add_text("Importanza della distanza:",
                              color=(180, 255, 180))
                dpg.add_slider_float(
                    tag="pp_alpha",
                    default_value=float(GPSConfig.PLANNER_ALPHA_DIST),
                    min_value=0.0, max_value=10.0,
                    format="%.2f",
                    width=-1,
                )
                dpg.add_text("  BASSO: il bot va anche lontano per task",
                              color=Colors.TEXT_DIM)
                dpg.add_text("          importanti",
                              color=Colors.TEXT_DIM)
                dpg.add_text("  ALTO:  il bot preferisce sempre le task",
                              color=Colors.TEXT_DIM)
                dpg.add_text("          vicine (a costo di farle 'sbagliate')",
                              color=Colors.TEXT_DIM)
                dpg.add_text("  Valore consigliato: 0.50",
                              color=Colors.TEXT_DIM)

                dpg.add_spacer(height=12)
                dpg.add_checkbox(
                    tag="pp_astar",
                    label=" Calcola distanze evitando muri (consigliato)",
                    default_value=bool(GPSConfig.PLANNER_USE_ASTAR),
                )
                dpg.add_text("  Se spunto OFF: distanza in linea retta",
                              color=Colors.TEXT_DIM)
                dpg.add_text("  (più veloce ma non considera i muri)",
                              color=Colors.TEXT_DIM)

            # === BOTTONI ===
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="Salva e applica", width=150,
                               callback=lambda *a: self._applica_pesi_pianificatore())
                dpg.add_button(label="Ripristina valori consigliati", width=200,
                               callback=lambda *a: self._reset_pesi_pianificatore())
                dpg.add_button(label="Annulla", width=110,
                               callback=lambda *a: dpg.delete_item(tag))

    def _applica_pesi_pianificatore(self):
        """Legge gli slider del popup e applica + salva i nuovi pesi."""
        nuovi = {
            'PLANNER_PESO_VITALE': dpg.get_value("pp_vitale"),
            'PLANNER_PESO_LONG':   dpg.get_value("pp_long"),
            'PLANNER_PESO_COMMON': dpg.get_value("pp_common"),
            'PLANNER_PESO_NA':     dpg.get_value("pp_na"),
            'PLANNER_PESO_SHORT':  dpg.get_value("pp_short"),
            'PLANNER_PESO_MULTI':  dpg.get_value("pp_multi"),
            'PLANNER_ALPHA_DIST':  dpg.get_value("pp_alpha"),
            'PLANNER_USE_ASTAR':   dpg.get_value("pp_astar"),
        }
        # Applico a GPSConfig (modifica runtime)
        for k, v in nuovi.items():
            setattr(GPSConfig, k, v)
        # Salvo su file per persistenza
        try:
            with open(PLANNER_WEIGHTS_FILE, 'w', encoding='utf-8') as f:
                _json.dump(nuovi, f, indent=2)
            self.auto_status_msg = "Pesi pianificatore aggiornati"
            print(f"[Planner] Nuovi pesi salvati in {PLANNER_WEIGHTS_FILE}")
        except OSError as e:
            self.auto_status_msg = f"Errore salvataggio pesi: {e}"

        # Chiudo il popup
        if dpg.does_item_exist("popup_pesi_planner"):
            dpg.delete_item("popup_pesi_planner")
        # Refresh della preview se aperta
        if getattr(self, '_preview_giro_aperto', False):
            self._aggiorna_preview_giro()

    def _reset_pesi_pianificatore(self):
        """Resetta gli slider ai valori di default."""
        defaults = {
            'pp_vitale': 1000.0,
            'pp_long':   30.0,
            'pp_common': 20.0,
            'pp_na':     25.0,
            'pp_short':  10.0,
            'pp_multi':  15.0,
            'pp_alpha':  0.5,
            'pp_astar':  True,
        }
        for tag_n, v in defaults.items():
            if dpg.does_item_exist(tag_n):
                dpg.set_value(tag_n, v)

    @staticmethod
    def carica_pesi_da_file():
        """
        Carica i pesi salvati da `planner_weights.json` e li applica
        a GPSConfig. Da chiamare all'avvio dell'app. Se il file non
        esiste, mantiene i default di GPSConfig.
        """
        if not _os.path.exists(PLANNER_WEIGHTS_FILE):
            return
        try:
            with open(PLANNER_WEIGHTS_FILE, 'r', encoding='utf-8') as f:
                d = _json.load(f)
            for k, v in d.items():
                if hasattr(GPSConfig, k):
                    setattr(GPSConfig, k, v)
            print(f"[Planner] Pesi caricati da {PLANNER_WEIGHTS_FILE}")
        except (OSError, _json.JSONDecodeError) as e:
            print(f"[Planner] Errore caricamento pesi: {e}")
