# Among Us AI

Bot di navigazione e automazione per Among Us. Legge la posizione del
giocatore direttamente dalla RAM del gioco, mostra una mappa interattiva,
calcola percorsi A* per spostarti automaticamente, registra ed esegue
task semi-automatiche, rileva altri giocatori e porte chiuse via YOLO.

> **Importante**: questo strumento usa input simulato a livello scan-code
> e lettura della RAM del processo del gioco. Funziona solo su **Windows**
> e richiede che Among Us sia in esecuzione.

---

## Indice

1. [Sezione utente](#sezione-utente) — come si installa e si usa
2. [Sezione sviluppatore](#sezione-sviluppatore) — come e' fatto dentro

---

# Sezione utente

## Installazione rapida

1. Estrai lo zip in una cartella (es. `C:\Bot\bot_among_us_ai\`).
2. Apri un prompt nella cartella e installa le dipendenze:
   ```
   pip install -r requirements.txt
   ```
3. Avvia il bot:
   ```
   python main.py
   ```

Al primo avvio, se hai un `task_registrate.json` di una vecchia versione,
il bot lo migra automaticamente nel nuovo formato (vedi sotto).

## Cosa fa il bot

In una partita di Among Us, mentre il bot e' aperto, vedi una finestra
con tre zone:

```
+------------------------------------+--------------------+
|                                    |                    |
|  Mappa del livello                 |  Pannello          |
|  (canvas con omino, scia,          |  laterale          |
|   task da fare, percorso A*)       |  (controlli)       |
|                                    |                    |
+------------------------------------+--------------------+
|  X: 12.3   Y: -4.5   FPS: 60   Mode: follow ...        |
+----------------------------------------------------------+
```

Il bot:

1. **Mostra la tua posizione in tempo reale** sulla mappa (palla verde
   al centro, con scia che si accumula muovendoti).
2. **Mostra le task da fare**, lette direttamente dalla memoria del
   gioco (cerchio colorato con icona).
3. **Calcola un percorso A***: cliccando sulla mappa o su una task,
   si genera una linea che mostra come arrivarci passando solo per
   zone calpestabili.
4. **Si muove automaticamente al posto tuo** se attivi
   "Auto-movimento": il bot preme W/A/S/D simulando i tasti.
5. **Esegue task pre-registrate**: se hai gia' "insegnato al bot"
   come fare una task (registrando i click con l'editor azioni),
   puoi avviarla con un bottone e lui la fa da solo.
6. **Rileva altri giocatori** vicini e porte chiuse tramite YOLO
   (visione artificiale).

## Pannello laterale: cosa c'e'

In cima sempre visibile:

- **Modalita' telecamera**: Segui (centra il giocatore), Libera (pan
  con tasto centrale del mouse), Tutta (zoom out per vedere tutto).
- **Zoom della mappa**: Riduci / Aumenta / Predefinito.
- **Auto-movimento**: checkbox per attivare lo spostamento
  automatico, riepilogo dello stato (target, numero waypoint nel
  percorso), bottone Annulla.

Sotto, una **TabBar** con 5 tab:

| Tab | Cosa contiene |
|-----|---------------|
| **Zone** | Aree definite a mano sulla mappa (Cafeteria, MedBay, ecc.). Bottoni per disegnare, modificare, navigare. Sotto-sezione "Zone porte" per filtrare le porte rilevate da YOLO. |
| **Task** | Task lette dalla RAM (in tempo reale) + Task registrate (salvate dall'utente con azioni custom). Bottone per la finestra di gestione padre/figlia (ereditarieta' delle azioni). |
| **POI** | Punti di interesse generici (Vent, Admin Panel, ecc.). |
| **Vista** | Cosa mostrare sulla mappa: griglia, scia, mirino, HUD. Configurazione del rilevamento YOLO. Smoothing della telecamera. |
| **Stats** | Distanza percorsa, tempo sessione, celle calpestabili, punti del trail. |

In fondo:
- **Scorciatoie da tastiera** (collassabile).

## Scorciatoie da tastiera

| Tasto | Azione |
|-------|--------|
| F | Telecamera "Segui giocatore" |
| R | Telecamera "Libera" (pan con tasto centrale) |
| O | Telecamera "Panoramica mappa" |
| G | Mostra/nascondi griglia |
| T | Mostra/nascondi scia (trail) |
| C | Mostra/nascondi mirino centrale |
| H | Mostra/nascondi HUD |
| P | Mostra/nascondi percorso A* |
| M | Abilita/disabilita auto-movimento |
| N | Disegna nuova zona |
| **F4** o **FINE (END)** | **Ferma TUTTO subito** (auto-move, esecuzione task, scanner YOLO) |
| Click sinistro | Imposta destinazione (calcola percorso A* da li') |
| Click destro / ESC | Annulla operazione corrente |
| Rotellina mouse | Zoom della mappa |
| Tasto centrale + drag | Pan della mappa |

## Come si registra una task

1. Avvicinati alla task in gioco (es. "Swipe Card" in Admin).
2. Nella tab "Task", se la task non e' in elenco "Task registrate",
   selezionala dalle "Task in memoria" e clicca "Registra nuova".
3. Aprilo con "Modifica task" e clicca "Modifica azioni" per aprire
   l'editor.
4. Nell'editor: clicca sui pulsanti come "Avvia click semplice" o
   "Avvia drag" e poi clicca sulla preview dello screenshot del gioco
   per registrare le coordinate.
5. Quando hai finito, "Salva e chiudi".
6. Dal pannello principale: "Genera file .py" produce il file
   autonomo dentro `tasks_exec/` che il bot esegue per fare la task.

## Modalita' Auto-Quest (esegui tutte)

Il bottone **Esegui automaticamente tutte le task** in tab "Task":

- Sceglie la task piu' vicina in elenco "Task in memoria".
- Naviga li' con A*.
- Lancia il file `.py` autonomo che simula i click del minigioco.
- Quando finisce, ricontrolla la RAM per vedere se la task e' "done"
  e passa alla prossima.

Tutto fermabile in qualsiasi momento con **F4** o **FINE**.

## File JSON di configurazione

Il bot legge dati da diversi file JSON nella cartella radice:

| File | Contenuto |
|------|-----------|
| `mappa_skeld.json` | Coordinate delle celle "calpestabili" (dove un giocatore puo' stare). Generato dal mapper. |
| `zone_skeld.json` | Zone nominate a mano (poligoni con nome e colore). |
| `door_zones_skeld.json` | Zone porte (filtro per il rilevamento YOLO). |
| `poi_skeld.json` | Punti di interesse (POI). |
| `tasks_dettagli.json` | Struttura delle task registrate (id, nome, posizione, fasi, alternativi, parent). |
| `tasks_esecuzione/task_<id>.json` | Azioni di una specifica task (un file per ogni task). |
| `task_registrate.json` | Vecchio formato monolitico. Solo per la migrazione automatica al primo avvio. |

## File generati

| File / cartella | Contenuto |
|---|---|
| `tasks_exec/` | File `.py` autonomi per ogni task (eseguibili via `python tasks_exec/task_001_xxx.py`). Generati dal bottone "Genera file .py" e usati a runtime quando si lancia una task. |
| `task_registrate.json.bak` | Backup del file legacy creato al primo avvio dopo la migrazione. |

## File di asset

| File | Cosa e' |
|------|---------|
| `arrow.pt`, `nav.pt`, `foglie.pt`, `asteroids.pt`, `vent.pt`, `porte.pt`, `yolo_players.pt` | Modelli YOLO (PyTorch) per il rilevamento visivo: freccia di navigazione, gli "ostacoli" del minigioco asteroidi, le foglie da rimuovere in O2, i vent, le porte chiuse, gli altri giocatori sulla mappa. |
| `requirements.txt` | Dipendenze Python (`pymem`, `pyautogui`, `dearpygui`, `numpy`, `opencv-python`, `pywin32`, `mss`, `ultralytics` per YOLO). |

---

# Sezione sviluppatore

## Architettura ad alto livello

Il bot e' un'applicazione DearPyGui (DPG) single-process che orchestra
piu' thread:

- **Thread principale** (DPG): rendering, input, callback UI.
- **Thread RAM**: legge a 60 Hz la posizione e la lista task del
  giocatore via `pymem`.
- **Thread YOLO**: scanner periodico che cattura screenshot e fa
  inferenza per rilevare altri giocatori e porte chiuse.
- **Subprocess**: quando si avvia una task, il bot lancia un altro
  processo Python (un file in `tasks_exec/`) che simula i click del
  minigioco.

```
                 main.py
                    |
                    v
        GPSVisualizerPro.run()
                    |
        +-----------+-----------+
        |           |           |
     thread      thread     thread principale
      RAM        YOLO       (DPG event loop)
        |           |           |
        v           v           v
       pymem    OpenCV +    rendering canvas,
   read_float   torch       mouse/key callback,
                            menu+pannello UI
                    |
                    v
        utente avvia una task
                    |
                    v
       subprocess.Popen(["python",
                         "tasks_exec/task_001_xxx.py",
                         "--step", "0"])
                    |
                    v
              click su task
              minigioco via SendInput
```

## Struttura del package

```
bot/
+-- main.py                       # entry point: 14 righe, chiama run()
+-- requirements.txt              # dipendenze Python
+-- *.json                        # mappa, zone, POI, task
+-- *.pt                          # modelli YOLO
+-- tasks_exec/                   # file .py generati per ogni task
+-- tasks_esecuzione/             # JSON azioni per ogni task
+-- among_us_ai/                  # package vero e proprio
    +-- core/
    |   +-- config.py             # GPSConfig + Colors (palette)
    |   +-- geometry.py           # point_in_polygon, hex_to_rgba, ...
    |   +-- stop_flag.py          # singleton globale per F4/END
    |   +-- win_deps.py           # import opzionali Windows
    +-- io_input/
    |   +-- key_controller.py     # SendInput a livello scan-code
    +-- pathfinding/
    |   +-- pathfinder.py         # A* su griglia + string-pulling
    +-- game_io/
    |   +-- memory_reader.py      # lettura RAM via pymem
    +-- managers/
    |   +-- task_manager.py             # FACADE
    |   +-- task_dettagli_manager.py    # CRUD struttura
    |   +-- task_esecuzione_manager.py  # CRUD azioni
    |   +-- zone_manager.py             # zone nominate
    |   +-- poi_manager.py              # punti di interesse
    +-- execution/
    |   +-- runtime.py            # motore "live" per il pulsante Test
    |   +-- task_template.py      # path del package motore (_motore_pkg)
    |   +-- _motore_pkg/          # motore modulare (copiato in tasks_exec/_motore/)
    |   +-- task_writer.py        # genera i thin wrapper .py delle task
    +-- ui/
        +-- app.py                # GPSVisualizerPro (init+frame+run)
        +-- editor.py             # TaskActionEditor (lifecycle)
        +-- mixins/               # 19 mixin GPSVisualizerPro
        +-- editor_mixins/        # 7 mixin TaskActionEditor
```

## Le tre classi principali

### `GPSVisualizerPro` (`ui/app.py`)

E' la classe principale. **Eredita da 19 mixin** che dividono i metodi
per tema (rendering, pathfinding, popup, ecc.). Ogni mixin contiene
solo metodi: lo stato `self.*` e' inizializzato qui in `__init__`.

```python
class GPSVisualizerPro(
    MemorySyncMixin, MapLoaderMixin, UISetupMixin, YoloScannerMixin,
    InputCallbacksMixin, AutoMoveMixin, AutoQuestMixin, ZonesMixin,
    TasksListMixin, TasksLaunchMixin, TasksProcessMixin,
    TasksPopupsRegisterMixin, TasksPopupsEditMixin, TasksPopupsSubitemMixin,
    DialogsMixin, PoiMixin, RenderingWorldMixin, RenderingEntitiesMixin,
    MiscMixin,
):
    def __init__(self): ...
    def aggiorna_frame(self): ...
    def run(self): ...
```

Solo `__init__`, `aggiorna_frame` e `run` stanno in `app.py`. Tutti i
~110 metodi rimanenti sono nei mixin.

### `TaskActionEditor` (`ui/editor.py`)

Finestra secondaria per registrare le azioni di una task (click, drag,
zone YOLO, sequenze). Anch'essa **eredita da 7 mixin**:
`EditorUIMixin`, `EditorStartActionsMixin`, `EditorSequenceMixin`,
`EditorCanvasInputMixin`, `EditorDrawingMixin`, `EditorListPanelMixin`,
`EditorSaveTestMixin`. Solo `__init__`, `apri`, `chiudi`,
`aggiorna_frame` stanno in `editor.py`.

### `TaskManager` (`managers/task_manager.py`)

E' una **facade** che delega a due sub-manager:

- `TaskDettagliManager`: CRUD struttura task (id, nome, posizione,
  fasi, alternativi, parent_id).
- `TaskEsecuzioneManager`: CRUD azioni e stato di esecuzione di
  ciascuna task.

L'API pubblica del `TaskManager` e' invariata rispetto al monolite
originale: i mixin chiamano `self.task_mgr.aggiungi(...)`,
`self.task_mgr.imposta_azioni(...)`, ecc. senza sapere che dietro le
quinte ci sono due manager.

## Pattern dei mixin

Tutti i mixin seguono lo stesso pattern. Esempio:

```python
# among_us_ai/ui/mixins/zones.py

"""
Gestione delle zone nominate e delle zone porta (UI).

Mixin di GPSVisualizerPro: metodi separati per organizzazione, ma
condividono lo stato self.* della classe principale.
"""

from ._imports import *


class ZonesMixin:
    def _start_new_zone_mode(self):
        self.zone_drawing_mode = True
        # ...

    def _refresh_zone_list(self):
        # ...
```

Lo `import *` carica tutti i simboli del facade `_imports.py`:
`dpg`, `time`, `math`, `os`, `GPSConfig`, `Colors`, `np`, `cv2`,
`TaskManager`, `ZoneManager`, `Pathfinder`, ecc. Cosi' nei mixin non
c'e' bisogno di ripetere 30 import in ogni file.

## Come aggiungere una funzionalita'

### Un nuovo bottone nel pannello

1. Apri `among_us_ai/ui/mixins/ui_setup.py`.
2. Trova il `with dpg.tab(label="...")` giusto.
3. Aggiungi `dpg.add_button(label="Mio bottone", callback=lambda *a: self._mio_callback())`.
4. Crea il metodo `_mio_callback` in un mixin appropriato. Se non
   sai dove, mettilo in `misc.py`.

### Un nuovo tipo di azione per le task

1. Aggiungi un metodo `_avvia_<nuova_azione>` in
   `editor_mixins/start_actions.py` che imposta lo stato della
   macchina (es. `self.stato = self.WAIT_NUOVA_AZIONE`).
2. Aggiungi la nuova costante di stato (`WAIT_NUOVA_AZIONE = "..."`)
   in `editor.py` (le costanti di classe in cima).
3. Gestisci il click in `editor_mixins/canvas_input.py`
   nella macchina a stati di `_canvas_mouse_down`.
4. Aggiungi il rendering dell'azione in
   `editor_mixins/drawing.py::_disegna_azione`.
5. Aggiungi l'esecuzione in `execution/runtime.py::esegui_azioni`
   (per il pulsante Test) **e** nel package `execution/_motore_pkg/`
   (per i file `.py` generati): aggiungi l'handler nel modulo della
   famiglia giusta e registralo nella dispatch map. Sono due posti
   distinti.

### Un nuovo manager

Crea `managers/<nome>_manager.py` sul modello di `PoiManager`,
esportalo da `managers/__init__.py`, instanzialo in
`GPSVisualizerPro.__init__` (in `ui/app.py`).

### Un nuovo gruppo di metodi UI

Crea `among_us_ai/ui/mixins/<nome>.py` con
`from ._imports import *` in cima e una classe `<Nome>Mixin`.
Aggiungi `from .mixins.<nome> import <Nome>Mixin` in `app.py` e
mettilo nelle basi di `GPSVisualizerPro`.

## File JSON: due formati

Le task sono in due file (formato v2.1):

```
tasks_dettagli.json:
{
  "next_id": 59,
  "task_list": [
    {
      "id": 1,
      "nome": "Swipe Card",
      "x": 6.5, "y": -6.6,
      "tipo": 5,
      "id_stanza": 6,
      "id_zona": 0,
      "id_zona_locale": 19,
      "nome_zona": "Admin",
      "id_padre": null,
      "vitale": false,
      "due_giocatori": false,
      "lunghezza": "Short",
      "fasi": [...],
      "alternativi": []
    },
    ...
  ]
}

tasks_esecuzione/task_001.json:
{
  "id": 1,
  "azioni": [
    {"tipo": "click", "x_rel": 0.5, "y_rel": 0.5, "durata": 0.2},
    ...
  ],
  "codice_personalizzato": false,
  "esecuzione": {
    "file": "tasks_exec/task_001_Swipe_Card.py",
    "stato": "idle",
    "parametri": {}
  }
}
```

`tasks_dettagli.json` e' "leggero" (~23 KB), cambia raramente. I file
in `tasks_esecuzione/` sono "pesanti" (azioni con poligoni, zone YOLO,
ecc.) e cambiano spesso quando si edita una task.

## Migrazione automatica al primo avvio

`TaskManager._migra_se_serve()` viene chiamato in `__init__`. Se:

- `tasks_dettagli.json` non esiste, **e**
- `task_registrate.json` esiste,

allora il manager:

1. Legge il vecchio formato monolitico.
2. Per ogni task, splitta in struttura (-> `tasks_dettagli.json`) e
   azioni (-> `tasks_esecuzione/task_<id>.json`).
3. Rinomina il vecchio file in `task_registrate.json.bak`.
4. Stampa un log:
   ```
   [Migrazione] Splitto 56 task da task_registrate.json...
   [Migrazione] Completata. Backup: task_registrate.json.bak
   ```

La migrazione accetta sia il formato `v2.0` (con `room_id`,
`parent_id`, `fratelli`) sia quello `v2.1` (con `id_stanza`,
`id_padre`, `alternativi`).

## Generazione del file `.py` per una task

`TaskManager.crea_file_esecuzione(id_task)` -> path del file generato.

1. Risolve l'ereditarieta': se la task ha `id_padre`, usa le azioni del
   padre.
2. Delega a `execution/task_writer.py::genera_file_esecuzione` che
   produce un thin wrapper con tre blocchi:
   - **header** (commento + marker versione + parsing argomenti CLI)
   - **meta_block** (dizionario `TASK_META` + costante `AZIONI`)
   - **call_block** (`import _motore` + `_motore.esegui_lifecycle(...)`)
   Il task_writer copia anche `_motore_pkg/` in `tasks_exec/_motore/`.
3. Il file risultante non importa nulla dal package `among_us_ai`:
   dipende solo dal package `_motore/` nella stessa cartella, ed e'
   eseguibile con `python tasks_exec/task_001_xxx.py --step 0`.

## Stop globale

Premere **F4** o **FINE (END)** in qualsiasi momento attiva il flag
`stop_flag.STOP` (singleton in `core/stop_flag.py`). Tutti i thread e i
loop di esecuzione lo controllano periodicamente e si fermano.

```python
# core/stop_flag.py
STOP = threading.Event()  # singleton globale

# nei mixin / runtime / template:
if stop_flag.STOP.is_set():
    return  # o break
```

## Convenzioni di codice

- **Italiano coerente** in business logic: campi JSON (`id_stanza`,
  `id_padre`, `alternativi`, `nome_zona`, ...), nomi metodi
  (`aggiungi`, `imposta_padre`, `naviga_a_zona`).
- **Inglese tecnico tenuto** dove e' gergo del dominio: tipi di azione
  (`click_poly`, `drag_zone`, `yolo_drag_all`), campi delle azioni
  (`poly`, `rect`, `rx`, `ry`, `keypad`, `lights`), `subprocess`,
  `_task_launch_*`.
- Tag DPG sono **stabili e snake_case** (`zone_listbox`,
  `mem_task_listbox`, `auto_state_label`): cambiarli rompe i
  `dpg.set_value()` sparsi nei mixin.
- Costanti `OFFSET_*` per gli offset RAM del gioco: in maiuscolo
  per chiarezza, non sono nomi di campo dei dati.

## Testing manuale

Non c'e' una test suite formale. Test consigliati per ogni modifica:

1. Avvia con `task_registrate.json` di esempio: la migrazione
   automatica deve produrre 56 task in `tasks_dettagli.json`.
2. Apri il pannello: tutti i 5 tab devono caricarsi senza errori
   nella console.
3. Genera un file `.py` di una task: `python tasks_exec/task_001*.py`
   non deve crashare.
4. F4 deve fermare istantaneamente qualunque thread/auto-move/task.

## Fonti & ringraziamenti

- DearPyGui: https://dearpygui.readthedocs.io/
- pymem: https://github.com/srounet/Pymem
- Ultralytics YOLO: https://docs.ultralytics.com/
