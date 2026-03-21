"""
Configurazione globale del bot e palette colori.

Tutti i parametri "magici" del progetto (file, soglie pathfinding, dimensioni
finestra, modelli YOLO ecc.) vivono in questa classe statica per essere
modificati in un solo posto.
"""


class GPSConfig:
    """Configurazione globale: dimensioni finestra, file path, costanti timing, soglie pathfinding."""
    # --- Mappa / finestra ---
    MAP_FILE = "mappa_skeld.json"
    DEFAULT_SCALE = 60
    MIN_SCALE = 5
    MAX_SCALE = 300
    WINDOW_W = 1280
    WINDOW_H = 820
    GRID_SIZE = 1.0
    SMOOTHING = 15.0
    TRAIL_MAX = 500
    TRAIL_INTERVAL = 0.05
    SIDE_PANEL_W = 350
    STATUS_BAR_H = 30

    # --- Pathfinding ---
    CELL_STEP              = 0.15    # deve combaciare con lo step del mapper
    WAYPOINT_ADVANCE       = 0.55    # Raggio ampio per transizioni fluide tra i punti

    # AUTO_ARRIVAL_THRESHOLD: distanza dal target sotto la quale si considera
    # "arrivato" e si lancia la task. Valore basso = arrivo piu' preciso ma
    # piu' rischio di stuck per imprecisioni del pathfinding. 0.15 e' un
    # compromesso fra precisione e robustezza (era 0.25 in v2.x, ridotto in
    # v2.2.11 per arrivare meglio nel raggio di attivazione del pulsante Use).
    AUTO_ARRIVAL_THRESHOLD = 0.15

    # AUTO_FINAL_NUDGE: dopo aver toccato la soglia di arrivo, il bot fa
    # un piccolo "nudge" (movimento di rifinitura) di N secondi puntando
    # ancora al target con i tasti direzionali. Serve per recuperare gli
    # ultimi centimetri quando il pathfinding lascia un piccolo margine.
    # 0 = disabilitato.
    AUTO_FINAL_NUDGE_SEC   = 0.20

    # MICRO-NUDGE iterativo basato sul rilevamento del pulsante "Use".
    # Quando attivato (USE_BUTTON_CHECK_ENABLED=True e calibrazione
    # presente), dopo l'arrivo al target il bot:
    #   1) Controlla se il pulsante Use e' illuminato
    #   2) Se SI -> lancia subito la task (massima precisione raggiunta)
    #   3) Se NO -> fa un micro-nudge WASD di MICRO_NUDGE_DURATION_SEC
    #              verso il target, poi ricontrolla il pulsante Use
    #   4) Ripete fino a USE_BUTTON_MAX_NUDGES tentativi
    #   5) Se dopo N tentativi ancora spento -> lancia la task comunque
    #      (best-effort, niente blocchi)
    USE_BUTTON_CHECK_ENABLED = True
    USE_BUTTON_MAX_NUDGES    = 10
    MICRO_NUDGE_DURATION_SEC = 0.05

    # EXEC_MODE: modalita' di esecuzione delle task (v2.2.17+).
    #   - 'subprocess' : esegue il file .py come processo Python separato
    #                    via subprocess.Popen. Modalita' originale, robusta
    #                    e isolata. (Default consigliato)
    #   - 'thread'     : esegue il motore come THREAD interno al bot
    #                    principale. Risparmia ~300-500ms di startup di
    #                    Python ma redirige sys.stdout (globale per processo)
    #                    causando potenziali problemi con altre print del
    #                    bot. SPERIMENTALE - usa solo se subprocess e' lento.
    #
    # In entrambi i modi i file .py in tasks_exec/ vengono generati e
    # restano funzionanti se l'utente li lancia a mano dalla shell.
    EXEC_MODE = 'subprocess'

    AUTO_AXIS_THRESHOLD    = 0.10    # sotto cui non premo il tasto
    AUTO_STUCK_TIME        = 0.8     # Tempo ridotto per un replan piu' rapido
    AUTO_STUCK_DELTA       = 0.06
    AUTO_REPLAN_ON_STUCK   = True
    NEAREST_SEARCH_RADIUS  = 80      # ricerca cella calpestabile piu' vicina
    ASTAR_MAX_NODES        = 20000   # safety limit

    # --- Simon Says (Reactor) ---
    # Tempo massimo (in secondi) per cui aspettiamo che il pannello del
    # minigioco si "stabilizzi" prima di catturare la base_img per
    # l'analisi della sequenza luminosa.
    #
    # Se il pannello si apre velocemente (~100-200ms), la stabilita'
    # viene rilevata in 60-150ms grazie al polling ogni 30ms - molto
    # prima del timeout.
    #
    # Aumentare se il tuo PC e' lento o il minigioco ha animazioni di
    # apertura piu' lunghe. Diminuire se vuoi essere ancora piu' rapido
    # (ma rischi di catturare una base imperfetta).
    #
    # NB: questo valore puo' essere sovrascritto per singola azione
    # tramite il campo `panel_timeout` nel JSON dell'azione simon_says
    # (es. {"tipo":"simon_says","panel_timeout":2.0,...}).
    SIMON_PANEL_TIMEOUT_SEC = 1.0

    # --- Zone nominate ---
    ZONE_FILE = "zone_skeld.json"
    # Distanza minima in pixel tra punti consecutivi del poligono freehand.
    # Valori piu' piccoli = poligoni piu' dettagliati (piu' pesanti).
    ZONA_PUNTO_DIST_PX = 8

    # --- Task ---
    # Formato v2.1: dettagli (struttura) + esecuzione (azioni) separati.
    TASK_DETTAGLI_FILE  = "tasks_dettagli.json"
    TASK_ESECUZIONE_DIR = "tasks_esecuzione"
    # Vecchio formato monolitico (v2.0): se esiste e tasks_dettagli.json no,
    # parte la migrazione automatica.
    TASK_LEGACY_FILE    = "task_registrate.json"

    TASKS_DEF_FILE      = "tasks.json"  # definizioni originali (task_lista.py)
    TASK_ICON_RADIUS    = 8

    # Alias retro-compatibilita': alcuni mixin/log si riferiscono a TASK_FILE.
    TASK_FILE = TASK_LEGACY_FILE

    # --- AI / Modelli YOLO ---
    YOLO_PLAYER_MODEL = "yolo_players.pt"
    YOLO_DOOR_MODEL   = "porte.pt"

    # --- Punti di Interesse ---
    POI_FILE = "poi_skeld.json"

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


# Costante usata da varie schermate di anteprima
MAX_PREVIEW_W = 720
MAX_PREVIEW_H = 650
