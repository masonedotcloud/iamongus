"""
Configurazione globale del bot e palette colori.

Tutti i parametri "magici" del progetto (file path, soglie pathfinding,
dimensioni finestra, modelli YOLO, pesi pianificatore, ecc.) vivono in
:class:`GPSConfig` per essere modificati in un solo posto invece di essere
sparsi nel codice.

I valori sono organizzati in sezioni; cerca i commenti ``# ---`` per
navigare velocemente.
"""


class GPSConfig:
    """Configurazione globale: una sola classe statica con tutti i parametri."""

    # ============================================================
    # --- Mappa / finestra DearPyGui ---
    # ============================================================
    MAP_FILE = "mappa_skeld.json"     # JSON con celle calpestabili e ostacoli
    DEFAULT_SCALE = 60                # zoom iniziale (px per unita' di gioco)
    MIN_SCALE = 5
    MAX_SCALE = 300
    WINDOW_W = 1280
    WINDOW_H = 820
    GRID_SIZE = 1.0                   # passo della griglia di sfondo
    SMOOTHING = 15.0                  # interpolazione camera (piu' alto = piu' fluido)
    TRAIL_MAX = 500                   # max punti di trail (storico posizioni)
    TRAIL_INTERVAL = 0.05             # s fra un campione di trail e il successivo
    SIDE_PANEL_W = 350                # larghezza del pannello laterale destro
    STATUS_BAR_H = 30                 # altezza della status bar in fondo

    # ============================================================
    # --- Pathfinding A* ---
    # ============================================================
    # Step della griglia di celle calpestabili. DEVE combaciare con lo step
    # usato dal mapper per registrare il trail (sennò A* non trova celle).
    CELL_STEP              = 0.15

    # Raggio entro cui un waypoint viene "consumato" (si avanza al prossimo).
    # Valore ampio = transizioni piu' fluide ma meno precisione.
    WAYPOINT_ADVANCE       = 0.55

    # AUTO_ARRIVAL_THRESHOLD: distanza sotto la quale si considera "arrivato"
    # al target e si lancia la task. Valore basso = arrivo piu' preciso ma
    # piu' rischio di stuck per imprecisioni del pathfinding. 0.15 e' un
    # compromesso fra precisione e robustezza (ridotto per arrivare nel
    # raggio di attivazione del pulsante Use del gioco).
    AUTO_ARRIVAL_THRESHOLD = 0.15

    # AUTO_FINAL_NUDGE: dopo aver toccato la soglia di arrivo, il bot fa un
    # piccolo "nudge" (movimento di rifinitura) di N secondi puntando ancora
    # al target con i tasti direzionali. Serve a recuperare gli ultimi
    # centimetri quando il pathfinding lascia un margine. 0 = disabilitato.
    AUTO_FINAL_NUDGE_SEC   = 0.20

    # LAUNCH_ANIMATION_ENABLED: animazione cosmetica del popup di lancio task
    # (mostra "Collegamento al task node...", "Handshake OK", ecc. uno step
    # alla volta). Quando True, il bot aspetta ~2.6s di animazione prima di
    # iniziare ad eseguire la task. Quando False, il subprocess viene
    # triggerato subito dopo l'arrivo (no attesa cosmetica).
    # Default: False (avvio rapido).
    LAUNCH_ANIMATION_ENABLED = False

    # ============================================================
    # --- MICRO-NUDGE iterativo basato su pulsante "Use" ---
    # ============================================================
    # Quando attivato (USE_BUTTON_CHECK_ENABLED=True e calibrazione presente),
    # dopo l'arrivo al target il bot:
    #   1) Controlla se il pulsante Use e' illuminato (= target in range)
    #   2) Se SI -> lancia subito la task (massima precisione raggiunta)
    #   3) Se NO -> fa un micro-nudge WASD verso il target, poi ricontrolla
    #   4) Ripete fino a USE_BUTTON_MAX_NUDGES tentativi
    #   5) Se dopo N tentativi ancora spento -> lancia la task comunque
    #      (best-effort, niente blocchi)
    USE_BUTTON_CHECK_ENABLED = True
    USE_BUTTON_MAX_NUDGES    = 10
    MICRO_NUDGE_DURATION_SEC = 0.05

    # ============================================================
    # --- LOOP GUARD RETRY ---
    # ============================================================
    # Quando il subprocess termina ma la task NON risulta done in RAM
    # (= il minigioco non si e' chiuso / non si e' aperto / il bot non e'
    # arrivato perfettamente), invece di applicare subito il cooldown di
    # sicurezza, tentiamo un riavvio "leggero":
    #   1) Premere ESC piu' volte per chiudere eventuali pannelli aperti
    #   2) Rilanciare la stessa task (senza ri-navigare: il bot e' gia'
    #      in posizione, basta tentare di nuovo SPAZIO + esecuzione)
    # Se dopo LOOP_GUARD_MAX_RETRIES tentativi la task non e' ancora done
    # in RAM, applichiamo finalmente il cooldown di sicurezza.
    LOOP_GUARD_MAX_RETRIES = 3
    LOOP_GUARD_ESC_COUNT   = 3      # n. ESC premuti prima del retry
    LOOP_GUARD_SAFETY_CD_SEC = 8.0  # cooldown finale di sicurezza (sec)

    # ============================================================
    # --- PESI PIANIFICATORE AUTO-ALL ---
    # ============================================================
    # Score finale per scegliere la prossima task =
    #   bonus_vitale + bonus_lunghezza + bonus_multi_fase
    #   - alpha_distanza * distanza_A*
    #
    # Modificabili in runtime dal popup "Strumenti -> Pesi pianificatore".
    # Sovrascritti da `planner_weights.json` se presente, altrimenti default.
    PLANNER_PESO_VITALE   = 1000.0  # priorita' assoluta sui sabotaggi
    PLANNER_PESO_LONG     = 30.0    # bonus per lunghezza='Long'
    PLANNER_PESO_COMMON   = 20.0    # bonus per lunghezza='Common'
    PLANNER_PESO_NA       = 25.0    # bonus per lunghezza='N/A' (sabotaggi)
    PLANNER_PESO_SHORT    = 10.0    # bonus per lunghezza='Short'
    PLANNER_PESO_MULTI    = 15.0    # bonus per task multi-fase
                                     # (Submit Scan, Inspect Sample, Empty Garbage)
    PLANNER_ALPHA_DIST    = 0.5     # peso della distanza (penalita')
    PLANNER_USE_ASTAR     = True    # True: distanza A* reale, False: euclidea

    # ============================================================
    # --- INTELLIGENCE: sidebar analisi sospettosita' player (F2) ---
    # ============================================================
    # Sistema modulare che gira in background raccogliendo dati dalle
    # detection esistenti. Mostra una sidebar (F2) con:
    # - Sospettosita' per ogni player (0-100%)
    # - Task probabilmente fatte
    # - Chi mi segue di piu'
    # - Vent uses, vicinanza cadaveri, sparizioni improvvise
    #
    # Vedi `among_us_ai/intelligence/` per i 5 moduli sottostanti
    # (player_tracker, activity_detector, proximity_analyzer,
    # task_inference, suspicion_analyzer).
    INTELLIGENCE_ENABLED       = True
    INTELLIGENCE_SIDEBAR_WIDTH = 320     # px
    INTELLIGENCE_REFRESH_HZ    = 2.0     # 2 update al secondo
    # I dati GREZZI vengono raccolti sempre, anche se la sidebar e' chiusa.

    # Toggle iniziale "evita player sospetti": se True, il path A* del bot
    # evita di passare sopra player con score > 40%. Si puo' cambiare a
    # runtime dal checkbox nella sidebar Intelligence (F2).
    AVOID_SUSPECTS_DEFAULT = False

    # Toggle iniziale Anti-AFK: se True, quando il bot e' fermo per piu' di
    # ANTI_AFK_THRESHOLD_SEC, lancia Auto-All automaticamente.
    # Si puo' cambiare a runtime con F3.
    ANTI_AFK_DEFAULT        = False
    ANTI_AFK_THRESHOLD_SEC  = 30.0

    # ============================================================
    # --- EXEC_MODE: come vengono eseguite le task ---
    # ============================================================
    #   - 'subprocess' : esegue il file .py come processo Python separato
    #                    via subprocess.Popen. Modalita' isolata e robusta:
    #                    lo stdout del bot principale resta intatto.
    #                    DEFAULT.
    #   - 'thread'     : esegue il motore come THREAD interno al bot.
    #                    Risparmia 1-2s di startup di Python, MA reindirizza
    #                    sys.stdout (globale per processo) -> tutte le print
    #                    del bot principale finiscono nella pipe del thread.
    #                    Rischio: pipe-buffer pieno (blocco) e crash su STOP.
    #                    Sconsigliato in produzione, lasciato solo per test.
    #
    # Per ridurre il delay del 'subprocess' al lancio, il bot fa
    # PRE-WARMING: il subprocess parte all'INIZIO del viaggio verso la task
    # (non all'arrivo). Cosi' al momento del SPAZIO il subprocess ha gia'
    # completato lo startup di Python e parte istantaneo.
    #
    # In entrambe le modalita' i file .py in `tasks_exec/` vengono generati
    # e restano lanciabili a mano dalla shell.
    EXEC_MODE = 'subprocess'

    # ============================================================
    # --- Auto-move (controllo input WASD) ---
    # ============================================================
    AUTO_AXIS_THRESHOLD    = 0.10    # soglia sotto cui NON premo il tasto
    AUTO_STUCK_TIME        = 0.8     # s di stuck prima di triggerare replan
    AUTO_STUCK_DELTA       = 0.06    # delta minimo di movimento per non-stuck
    AUTO_REPLAN_ON_STUCK   = True
    NEAREST_SEARCH_RADIUS  = 80      # raggio per ricerca cella calpestabile piu' vicina
    ASTAR_MAX_NODES        = 20000   # safety limit per non bloccare il loop A*

    # ============================================================
    # --- Simon Says (Reactor) ---
    # ============================================================
    # Tempo massimo (in secondi) per cui aspettiamo che il pannello del
    # minigioco si "stabilizzi" prima di catturare la base_img per l'analisi
    # della sequenza luminosa.
    #
    # Se il pannello si apre velocemente (~100-200ms), la stabilita' viene
    # rilevata in 60-150ms grazie al polling ogni 30ms - molto prima del
    # timeout.
    #
    # Aumentare se il tuo PC e' lento o il minigioco ha animazioni di
    # apertura piu' lunghe. Diminuire se vuoi essere ancora piu' rapido
    # (ma rischi di catturare una base imperfetta).
    #
    # NB: puo' essere sovrascritto per singola azione tramite il campo
    # `panel_timeout` nel JSON dell'azione simon_says
    # (es. {"tipo":"simon_says","panel_timeout":2.0,...}).
    SIMON_PANEL_TIMEOUT_SEC = 1.0

    # ============================================================
    # --- Zone nominate (poligoni "stanze" disegnati dall'utente) ---
    # ============================================================
    ZONE_FILE = "zone_skeld.json"
    # Distanza minima in pixel fra punti consecutivi del poligono freehand.
    # Valori piu' piccoli = poligoni piu' dettagliati (piu' pesanti).
    ZONA_PUNTO_DIST_PX = 8

    # ============================================================
    # --- Task ---
    # ============================================================
    # Formato split: dettagli (struttura) + esecuzione (azioni) separati.
    TASK_DETTAGLI_FILE  = "tasks_dettagli.json"
    TASK_ESECUZIONE_DIR = "tasks_esecuzione"
    # Vecchio formato monolitico: se esiste e tasks_dettagli.json no,
    # parte la migrazione automatica all'avvio.
    TASK_LEGACY_FILE    = "task_registrate.json"

    TASKS_DEF_FILE      = "tasks.json"  # definizioni originali (task_lista.py)
    TASK_ICON_RADIUS    = 8             # raggio dell'icona task sulla mappa

    # Alias retro-compatibile: alcuni mixin/log si riferiscono a TASK_FILE.
    TASK_FILE = TASK_LEGACY_FILE

    # ============================================================
    # --- AI / Modelli YOLO ---
    # ============================================================
    YOLO_PLAYER_MODEL = "yolo_players.pt"
    YOLO_DOOR_MODEL   = "porte.pt"

    # ============================================================
    # --- Punti di Interesse (POI) ---
    # ============================================================
    POI_FILE = "poi_skeld.json"

    # ============================================================
    # --- Palette dei colori per le zone nominate ---
    # ============================================================
    # Hex picker: ciclicamente assegnato alle nuove zone create.
    COLORI_ZONE = [
        "#E74C3C", "#F39C12", "#F1C40F", "#27AE60",
        "#16A085", "#3498DB", "#9B59B6", "#E91E63",
        "#FF5722", "#795548", "#00BCD4", "#CDDC39",
    ]


class Colors:
    """Palette colori usata da tutto il rendering DearPyGui."""
    BG           = (12, 12, 15, 255)
    PANEL_BG     = (18, 18, 22, 255)
    GRID         = (25, 25, 30, 255)
    AXIS         = (70, 120, 170, 255)
    VISITED      = (38, 38, 42, 255)
    TRAIL        = (255, 200, 0)
    PLAYER       = (0, 255, 100, 255)
    PLAYER_GLOW  = (0, 255, 100, 50)
    CROSSHAIR    = (0, 255, 100, 180)
    TEXT         = (220, 220, 220, 255)
    TEXT_DIM     = (140, 140, 150, 255)
    ACCENT       = (0, 200, 255, 255)
    TARGET       = (255, 80, 180, 255)
    TARGET_DIM   = (255, 80, 180, 90)
    PATH         = (0, 220, 255, 220)
    PATH_DONE    = (0, 150, 180, 140)
    WAYPOINT     = (0, 255, 220, 255)
    ZONE_PREVIEW = (255, 255, 255, 220)


# Dimensioni massime delle schermate di anteprima (es. preview giro F1).
MAX_PREVIEW_W = 720
MAX_PREVIEW_H = 650
