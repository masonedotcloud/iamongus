# Among Us Ultimate GPS Pro

Bot di navigazione/automazione per Among Us: legge la posizione del giocatore
direttamente dalla RAM, mostra una mappa interattiva, fa pathfinding A*,
permette di registrare/eseguire task semi-automatiche, scansiona gli altri
giocatori e le porte chiuse via YOLO, e altro.

Questa versione e' la riorganizzazione modulare del file unico `main.py`
originale (~11.000 righe) in un package Python strutturato. **Logica e
funzionamento sono invariati** — solo la disposizione del codice e' cambiata.


## Requisiti

- **Windows** (il bot usa `SendInput`, `win32gui`, lettura RAM via `pymem`).
- Python 3.9+.
- Among Us installato e in esecuzione (versione compatibile con gli offset
  RAM definiti in `among_us_gps/game_io/memory_reader.py`).

Installa le dipendenze:

```bash
pip install -r requirements.txt
```


## Avvio

Dalla cartella radice del progetto:

```bash
python main.py
```

oppure equivalentemente:

```bash
python -m among_us_gps
```


## Struttura del progetto

```
bot_organized/
├── main.py                       # entry point convenience
├── requirements.txt
├── mappa_skeld.json              # mappa registrata dal mapper
├── zone_skeld.json               # zone disegnate freehand
├── door_zones_skeld.json         # zone "porte"
├── poi_skeld.json                # punti di interesse
├── task_registrate.json          # task registrate dall'utente
├── *.pt                          # modelli YOLO (giocatori, porte, ecc.)
├── tasks_exec/                   # file .py autonomi generati per ogni task
└── among_us_gps/                 # codice sorgente del bot
    ├── core/
    │   ├── config.py             # GPSConfig + Colors (palette)
    │   ├── geometry.py           # point_in_polygon, get_client_rect, ecc.
    │   └── win_deps.py           # import opzionali Windows (mss, win32, cv2...)
    ├── io_input/
    │   └── key_controller.py     # SendInput a livello scan-code
    ├── pathfinding/
    │   └── pathfinder.py         # A* su griglia con string-pulling
    ├── game_io/
    │   └── memory_reader.py      # lettura RAM Among Us via pymem
    ├── managers/
    │   ├── zone_manager.py       # CRUD + persistenza zone JSON
    │   ├── poi_manager.py        # CRUD + persistenza POI JSON
    │   └── task_manager.py       # task + generazione file esecuzione
    ├── execution/
    │   ├── runtime.py            # motore esecuzione runtime (per il "test")
    │   ├── task_template.py      # loader del template di file generato
    │   └── task_template.txt     # template raw del motore inline
    └── ui/
        ├── gps_app.py            # GPSVisualizerPro (dashboard principale)
        └── task_action_editor.py # editor azioni per le task
```


## Come e' organizzato il codice

### `core/`

Cose stabili e usate ovunque: configurazione, palette, helper geometrici,
gestione delle dipendenze opzionali (Windows-only). Questo e' l'unico modulo
"di base", senza dipendenze interne, importabile da chiunque.

### `io_input/`

Input simulato di basso livello: scan-code Windows tramite `SendInput`.
Among Us usa DirectInput per leggere la tastiera, quindi funziona solo
con `SendInput` a livello scan-code (non `keybd_event`, non `pyautogui`).

### `pathfinding/`

A* su una griglia di celle "calpestabili" — il bot si muove solo dove un
giocatore umano e' effettivamente passato (registrato dal mapper).
Include corner-cutting prevention, hitbox a croce, string-pulling e
penalita' per stare lontani dai muri.

### `game_io/`

Lettura della memoria di Among Us tramite `pymem`. Due classi:
posizione del player e lista task attive. Gli offset sono per la build
attuale del gioco — vanno aggiornati a ogni patch maggiore.

### `managers/`

Persistenza CRUD su file JSON: zone, POI, task. Ogni manager carica
dal proprio file all'init e salva ad ogni modifica.

Il `TaskManager` ha anche una responsabilita' speciale: genera file `.py`
autonomi nella cartella `tasks_exec/` quando si predispone una task per
l'esecuzione. Ogni file generato include inline il motore di esecuzione
e puo' essere lanciato standalone con `python task_xxx.py`.

### `execution/`

Due cose, separate apposta:

- `runtime.py`: motore "live" usato dal pulsante **Test** dell'editor.
  Dipende da `pyautogui`, `win32gui`, ecc. — gira solo su Windows.
- `task_template.py` + `task_template.txt`: il template che viene scritto
  in cima ai file generati nei `tasks_exec/`. E' una stringa di testo
  raw, NON viene eseguita dal codice principale. Cosi' i file generati
  sono autonomi e non hanno dipendenze sul package.

### `ui/`

Le due finestre DearPyGui:

- `gps_app.py`: la dashboard principale (`GPSVisualizerPro`). E' una
  "god class" molto grossa (~5300 righe, 164 metodi) — e' lasciata in
  un unico file perche' tutti i suoi metodi condividono lo stato in
  modo molto fitto. In cima al file c'e' un commento "mappa dei metodi"
  per orientarsi.
- `task_action_editor.py`: la finestra secondaria per registrare le
  azioni di una task (click, drag, zone).


## File di dati

I JSON e i `.pt` (modelli YOLO) devono stare nella **cartella di lavoro**
da cui lanci `python main.py`. I path sono definiti in
`among_us_gps/core/config.py` (classe `GPSConfig`) e sono relativi.

Se vuoi cambiare i path (es. spostarli in una sottocartella `data/`),
modifica solo `GPSConfig` — non c'e' piu' bisogno di toccare il codice.


## Aggiungere nuove funzionalita'

Alcune ricette comuni:

### Nuova soglia di pathfinding

Aggiungi un attributo a `core/config.py` -> `GPSConfig` e usalo in
`pathfinding/pathfinder.py`. Cosi' resta tunabile in un solo posto.

### Nuovo tipo di azione per le task

Va aggiunto in DUE posti, perche' le task girano in due ambienti:

1. `among_us_gps/execution/runtime.py` -> dentro `esegui_azioni()`,
   cosi' funziona il pulsante **Test** dell'editor.
2. `among_us_gps/execution/task_template.txt` -> dentro la `esegui_azioni`
   inline del template, cosi' funziona quando il file `.py` generato
   viene lanciato come subprocess.

Le due implementazioni sono separate apposta: il template e' autonomo
e non importa nulla dal package, mentre il runtime usa import diretti.

### Nuovo manager (es. eventi, scoreboards, ecc.)

Crea `among_us_gps/managers/<nome>_manager.py` sul modello di
`PoiManager`, esportalo da `managers/__init__.py`, e instanzialo
dentro `GPSVisualizerPro.__init__` (vedi gli altri manager).

### Nuovo pannello UI

I pannelli laterali sono costruiti in `_costruisci_pannello()` dentro
`ui/gps_app.py`. Aggiungi un `dpg.collapsing_header` con i tuoi widget
e i relativi callback `_on_*` come metodi di `GPSVisualizerPro`.


## Compatibilita' con i file gia' generati

I file gia' presenti in `tasks_exec/` (generati dalla versione monolitica)
**continuano a funzionare** senza modifiche. Sono completamente autonomi e
non importano nulla dal nuovo package.

Quando l'utente preme nuovamente "predisponi esecuzione" su una task,
il file viene rigenerato dal nuovo `TaskManager` con lo stesso template
(verificato bit-per-bit identico al raw originale, 45.974 byte).


## Note

- Tutto il codice e' stato spostato per modulo ma **non riscritto**:
  la logica e' invariata. Solo gli import sono stati riarrangiati e le
  classi/funzioni hanno docstring piu' dettagliate dove mancavano.
- Le righe 855-1890 dell'originale `main.py` (il template raw del file
  generato) sono ora un asset di testo separato (`task_template.txt`)
  e non vengono piu' analizzate dall'IDE come codice del progetto.
  Questo elimina i "falsi duplicati" di `_extract_pure_shape` ed
  `esegui_azioni` che apparivano nel `main.py` originale.
