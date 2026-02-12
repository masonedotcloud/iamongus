# File di asset

Documentazione dei file binari e JSON usati dal bot.
Questi non possono contenere commenti al loro interno (sono binari o
JSON puro), quindi sono descritti qui.

---

## Modelli YOLO (`*.pt`)

File PyTorch contenenti pesi addestrati per il rilevamento visivo.
Vengono caricati via `ultralytics.YOLO("nome.pt")` e usati per
fare inferenza su screenshot del gioco catturati con `mss`.

| File | Cosa rileva | Usato in |
|------|-------------|----------|
| `arrow.pt` | Frecce di navigazione (es. il navigatore in Weapons, Reactor) | `execution/runtime.py` |
| `nav.pt` | Generico "naviga" (varianti di frecce, indicatori) | `execution/runtime.py` |
| `foglie.pt` | Foglie da rimuovere nel minigioco "Clean O2 Filter" | `execution/runtime.py` |
| `asteroids.pt` | Asteroidi da colpire in "Clear Asteroids" | `execution/runtime.py` |
| `vent.pt` | Bocchette di aerazione (vent) | `execution/runtime.py` |
| `porte.pt` | Porte chiuse del livello (filtrate dalle "zone porte") | `ui/mixins/yolo_scanner.py` |
| `yolo_players.pt` | Altri giocatori sulla mappa (color-blind detection) | `ui/mixins/yolo_scanner.py` |

I modelli sono caricati on-demand e tenuti in cache. Il primo accesso
e' lento (~1 secondo per modello), gli accessi successivi sono
istantanei.

**Per addestrare nuovi modelli**: vedi documentazione Ultralytics
(`yolo train data=... model=...`). I modelli del bot usano
architetture YOLOv8 nano/small per restare leggeri.

---

## Mappa e configurazione livello

### `mappa_skeld.json`

Lista delle celle della mappa "calpestabili" (zone dove un giocatore
puo' effettivamente stare). Generato dal **mapper** (uno script
separato che registra la posizione del giocatore mentre si muove).

Formato:
```json
{
  "celle": [
    [12.5, -3.2],
    [12.5, -2.7],
    ...
  ],
  "step": 0.5
}
```

`celle` = lista di coordinate (x, y) dove il giocatore e' passato.
`step` = passo della griglia (default 0.5 unita' di gioco).

Il `Pathfinder` usa queste celle per costruire il grafo per A*.

### `zone_skeld.json`

Aree della mappa nominate a mano dall'utente (es. "Cafeteria",
"MedBay"). Sono poligoni con nome, colore e identificativi di gioco.

Formato:
```json
{
  "zone_list": [
    {
      "id": 1,
      "nome": "Cafeteria",
      "colore": "#E74C3C",
      "punti": [[10.0, -5.0], [15.0, -5.0], ...],
      "id_zona_gioco": 14,
      "id_padre": null
    }
  ]
}
```

`punti` = poligono in coordinate di gioco (chiuso, ultimo punto =
primo). `id_zona_gioco` = identificativo numerico opzionale che
collega la zona a una zona del gioco (per matching automatico delle
task).

### `door_zones_skeld.json`

Aree dove **ignorare** le porte rilevate da YOLO. Stesso formato di
`zone_skeld.json` ma usate come filtro: una porta rilevata dentro
una "zona porta" viene ignorata (es. perche' e' una porta sempre
aperta o non pertinente al gameplay).

### `poi_skeld.json`

Punti di interesse generici sulla mappa (es. "Vent in Electrical",
"Admin Panel"). Diversi dalle task perche' non sono task di gioco,
ma riferimenti utili per la navigazione manuale.

Formato:
```json
{
  "next_id": 4,
  "poi_list": [
    {
      "id": 1,
      "nome": "Vent Electrical",
      "x": -10.0, "y": -8.5,
      "icona": "vent",
      "colore": "#F39C12"
    }
  ]
}
```

---

## Task

### `task_registrate.json` (legacy, formato v2.0)

Vecchio formato monolitico: tutto in un solo file (struttura + azioni).
Usato solo dalla **migrazione automatica al primo avvio** della v2.1+.

Dopo la migrazione viene rinominato in `task_registrate.json.bak`.

### `tasks_dettagli.json` (formato v2.1)

Struttura delle task registrate, **senza azioni**.

```json
{
  "next_id": 59,
  "task_list": [
    {
      "id": 1,
      "nome": "Swipe Card",
      "x": 6.5,
      "y": -6.6,
      "tipo": 5,
      "id_stanza": 6,
      "id_zona": 0,
      "id_zona_locale": 19,
      "nome_zona": "Admin",
      "id_padre": null,
      "vitale": false,
      "due_giocatori": false,
      "lunghezza": "Short",
      "cooldown": 0.0,
      "fasi": [
        {"nome": "Card swipe", "x": 6.5, "y": -6.6}
      ],
      "alternativi": []
    },
    ...
  ]
}
```

| Campo | Significato |
|-------|-------------|
| `id` | Identificativo univoco (assegnato in ordine crescente) |
| `nome` | Nome leggibile |
| `x`, `y` | Posizione principale sulla mappa (in coordinate di gioco) |
| `tipo` | Tipo task come dichiarato nel gioco (numero, vedi `tasks.json`) |
| `id_stanza` | "Room ID" del gioco (combinazione tipo+stanza identifica la task) |
| `id_zona` / `id_zona_locale` / `nome_zona` | Collegamento alla zona nominata |
| `id_padre` | Se valorizzato, la task eredita le azioni dalla task padre |
| `vitale` | True = task da fare sempre per prima |
| `due_giocatori` | True = richiede due giocatori (es. fix wiring) |
| `lunghezza` | "Short", "Medium", "Long" — solo descrittivo |
| `cooldown` | Pausa minima tra esecuzioni (in secondi) |
| `fasi` | Step intermedi di una task multi-fase (es. "Submit Scan" ha "Wait" + "Press") |
| `alternativi` | Posizioni alternative dove la stessa task puo' essere completata |

### `tasks_esecuzione/task_<id>.json` (formato v2.1)

Un file per ogni task. Contiene azioni, codice custom flag e stato.

```json
{
  "id": 1,
  "azioni": [
    {"tipo": "click", "x_rel": 0.5, "y_rel": 0.5, "durata": 0.2},
    {"tipo": "drag", "start_rx": 0.2, "start_ry": 0.5,
                     "end_rx": 0.8, "end_ry": 0.5,
                     "durata": 0.5, "attesa": 0.3}
  ],
  "codice_personalizzato": false,
  "esecuzione": {
    "file": "tasks_exec/task_001_Swipe_Card.py",
    "stato": "idle",
    "parametri": {}
  }
}
```

| Campo | Significato |
|-------|-------------|
| `id` | Stesso `id` della task in `tasks_dettagli.json` |
| `azioni` | Lista delle azioni in ordine. Vedi tipi sotto. |
| `codice_personalizzato` | True = il file `.py` e' stato editato a mano, non sovrascrivere |
| `esecuzione.file` | Path del file `.py` generato (in `tasks_exec/`) |
| `esecuzione.stato` | `idle` / `setup` / `launch` / `running` / `done` / `error` |
| `esecuzione.parametri` | Parametri runtime (passati al subprocess) |

### Tipi di azione

I `"tipo"` di azione corrispondono ai pulsanti nell'editor azioni:

| Tipo | Cosa fa |
|------|---------|
| `click` | Click semplice in un punto del minigioco |
| `click_anomaly` | Click sull'unico elemento "diverso" (per minigiochi tipo "Detect Anomaly") |
| `click_poly` | Click su un poligono di punti in sequenza |
| `click_rect` | Click in un rettangolo (per "Stabilize Steering") |
| `click_until` | Click ripetuto finche' un check non passa |
| `cooldown` | Pausa fissa (in secondi) |
| `drag` | Trascinamento da A a B |
| `drag_hold` | Drag con tasto premuto piu' a lungo |
| `drag_multi` | Drag in sequenza su piu' punti |
| `drag_zone` | Drag che inizia in una zona, finisce in un'altra |
| `number_match` | Matching numerico (per "Stabilize Steering") |
| `ocr_keypad` | Lettura OCR di un keypad poi click |
| `simon_says` | Replay di una sequenza luminosa |
| `sync_click` | Click sincronizzato a un evento visivo |
| `wiring` | Cablaggio: collega L con R passando per C |
| `yolo_click_all` | Click su tutti gli oggetti rilevati da YOLO |
| `yolo_drag` | Drag basato su rilevamento YOLO |
| `yolo_drag_all` | Drag di tutti gli oggetti rilevati |
| `yolo_drag_seq` | Drag in sequenza di oggetti rilevati |

### `tasks.json`

Definizioni "originali" delle task del gioco (estratte dal codice
sorgente di Among Us / `task_lista.py` di un dump). Usate solo per
matching automatico nome <-> tipo+id_stanza quando il bot legge la RAM.

Se vuoto o mancante, il bot funziona lo stesso: i nomi delle task
saranno presi dalla RAM se possibile.

---

## File generati

### `tasks_exec/task_<id>_<nome>.py`

File Python autonomi generati dal bottone "Genera file .py" e dal
runtime quando si avvia una task. Contengono tre blocchi:

1. **header** (commento + parsing args CLI)
2. **TASK_META** + **AZIONI** (dati specifici della task)
3. **motore di esecuzione** (codice generico copiato da
   `among_us_ai/execution/task_template.txt`)

Eseguibili con `python tasks_exec/task_001_Swipe_Card.py --step 0`.
Non importano nulla dal package `among_us_ai`: sono completamente
autonomi.

**Il bot li sovrascrive ogni volta che modifichi le azioni** dal
pannello (a meno che `codice_personalizzato` sia True).

### `task_registrate.json.bak`

Backup automatico creato dalla migrazione al primo avvio. Da non
toccare: serve solo se vuoi tornare indietro al formato v2.0.
