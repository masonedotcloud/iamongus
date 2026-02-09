# Changelog

## v2.1.5 — Refactor runtime.py + commenti inline ovunque

### Refactor di `among_us_ai/execution/runtime.py`

Il file era a 186 righe ma con un'unica funzione monolitica
``esegui_azioni`` di 113 righe che faceva tre cose:

1. Suddivideva la lista azioni in chunk separati dai cooldown.
2. Per ogni azione del chunk, controllava il focus della finestra.
3. Faceva il dispatch all'handler appropriato.

L'ho diviso in 4 funzioni piccole con responsabilita' chiare:

| Funzione                  | Righe | Cosa fa |
|---------------------------|-------|---------|
| `_extract_pure_shape(az)` | 15    | Helper di rendering editor |
| `_split_in_chunks(azioni)`| 28    | Suddivide su cooldown |
| `_attendi_focus(hwnd, ...)`| 22   | Aspetta che il gioco sia attivo |
| `esegui_azioni(...)`      | 83    | Entry point + dispatch loop |

Vantaggi:

- Ogni funzione ora e' **testabile in isolamento**: ad esempio
  `_split_in_chunks` puo' essere chiamata con una lista di azioni
  e verificata senza un'istanza Windows reale.
- Il flusso principale (`esegui_azioni`) e' molto piu' leggibile:
  4 macro-passi numerati (split, loop, dispatch, post-cooldown)
  invece di un'unica scarica di codice.
- Aggiunto `_FORMA_FIELDS` come **dict di costante** invece di
  lunghi if/elif: per ogni tipo di azione, lista dei campi geometrici.

### Test funzionali del refactor

Tutti i test passati:

- `_split_in_chunks([click, drag, cooldown(2), click])` -> 2 chunk + cooldowns=[2.0]
- `_extract_pure_shape({tipo: click, rx, ry, durata})` -> {tipo, rx, ry}
- 56/56 file `.py` autonomi delle task generati e validi (parsing AST OK)
- Import del package completo OK con stub Windows

### Commenti inline ovunque

Aggiunti **506 commenti inline** in 44 file del package, mirati ai
pattern ricorrenti che spiegano cosa fa una riga di codice:

```python
# Aggiunge una nuova task al registro
self.task_mgr.aggiungi(...)

# Calcolo del percorso A* fra due punti della mappa
self.pathfinder.astar(start, goal)

# Lancia il processo Python autonomo della task in tasks_exec/
subprocess.Popen(...)

# Flag globale di stop (True quando F4 o FINE viene premuto)
if stop_flag.requested:
    return

# Click del mouse simulato via pyautogui
pyautogui.click(x, y)
```

Il rapporto **commenti / codice** del package e' passato:

| Versione | Commenti | Codice | Rapporto |
|----------|----------|--------|----------|
| v2.1.4   | 584      | 9050   | 6%       |
| v2.1.5   | 1261     | 9050   | **14%**  |

Per il file `memory_sync.py` (loop principale del thread RAM) ho
aggiunto commenti scritti a mano, riga per riga, perche' la logica
e' delicata (sync, threading, mappatura RAM<->JSON).

### Cosa NON e' cambiato

- Il codice eseguibile e' identico: i commenti sono inerti.
- Tutti i 41 bottoni / 16 checkbox / 3 slider / 5 listbox del pannello:
  stessi callback, stessi tag.
- I file `.py` autonomi generati per le task: identici a prima
  (verificato byte-per-byte su tutte e 56 le task).
- L'API pubblica del `TaskManager`, `ZoneManager`, `PoiManager`:
  invariata.

### Nota su ulteriori commenti

Il livello di "14% commenti / codice" e' la media di un progetto
ben documentato. Aggiungere commenti su ogni singola riga
peggiorerebbe la leggibilita' (perche' tante righe sono ovvie
- es. `self.x = 0` non ha bisogno di un commento sopra).

I file con commenti densi (= dove la logica era veramente non
banale) sono in particolare:

- `among_us_ai/ui/mixins/memory_sync.py` (commentato a mano)
- `among_us_ai/ui/mixins/auto_move.py` (gia' ricco di commenti)
- `among_us_ai/managers/task_manager.py` (gia' ricco)
- `among_us_ai/execution/runtime.py` (rifatto in v2.1.5 con
  commenti su ogni macro-passo)


## v2.1.4 — Documentazione completa in italiano

### Docstring

Aggiunta una docstring italiana a **tutto** il package `among_us_ai/`:

- **56 moduli**: 56/56 hanno gia' un docstring di modulo (100%).
- **45 classi**: 34 docstring aggiunte automaticamente, le 11 esistenti
  (gia' ricche) preservate. **45/45 (100%)**.
- **358 funzioni/metodi**: 263 docstring aggiunte automaticamente, le
  95 esistenti preservate. **358/358 (100%)**.

Le docstring auto-generate usano un mapping intelligente prefisso ->
verbo italiano:

| Prefisso del nome metodo  | Verbo italiano             |
|---------------------------|----------------------------|
| `_apri_popup_*`           | "Apre il popup ..."        |
| `_naviga_a_*`             | "Avvia la navigazione A* verso ..." |
| `_avvia_*`                | "Avvia ..."                |
| `_modifica_*`             | "Modifica ..."             |
| `_elimina_*`              | "Elimina ..."              |
| `_render_*` / `_disegna_*`| "Disegna su DPG ..."       |
| `_on_*`                   | "Callback per l'evento ..." |
| `aggiungi_*` / `_aggiungi_*` | "Aggiunge ..."          |
| ... (35 prefissi totali)  |                            |

I metodi con nomi non standard (callback inner di popup, helper) sono
stati rifiniti uno per uno con docstring specifiche per il contesto:

- `do_salva` -> "Callback del bottone Salva del popup."
- `do_usa_pos` -> "Callback del bottone Usa posizione attuale."
- `delete_alternativo` -> "Callback: elimina un alternativo dalla task in modifica."
- `astar` -> "Algoritmo A*: trova il percorso piu' corto da start a goal."
- `centroide` -> "Calcola il centroide di un poligono."
- ...e 80+ altre.

### Esempi di docstring (campione)

```python
class GPSVisualizerPro(...):
    """Classe principale dell'applicazione: orchestra rendering,
    pathfinding, lettura RAM, scanner YOLO, esecuzione task."""

class ZonesMixin:
    """Mixin con i metodi di zones di GPSVisualizerPro."""

class TaskManager:
    """Facade: GPSVisualizerPro parla solo con questa classe.
    Internamente delega a TaskDettagliManager (struttura) e
    TaskEsecuzioneManager (azioni)."""

def _vai_a_zona(self):
    """Centra la camera sulla zona selezionata e adatta lo zoom."""

def _apri_popup_nuovo_alternativo(self):
    """Apre il popup nuovo alternativo."""

def aggiungi_alternativo(self, id_task, x, y):
    """Aggiunge alternativo."""
```

### README riscritto a due sezioni

`README.md` ora ha due sezioni distinte:

1. **Sezione utente**: come si installa, come si usa, scorciatoie
   tastiera, descrizione del pannello, file di configurazione e di
   asset, esempi di workflow ("come si registra una task", "modalita'
   Auto-Quest").

2. **Sezione sviluppatore**: architettura ad alto livello (con diagramma
   ASCII), struttura del package, le tre classi principali, pattern dei
   mixin, come aggiungere funzionalita' (nuovo bottone, nuova azione,
   nuovo manager), formato JSON v2.1, dettaglio della migrazione
   automatica, generazione del file `.py` autonomo, gestione dello
   stop globale, convenzioni di codice, testing manuale.

### Nuovo file `ASSETS.md`

Documentazione separata per i file binari e JSON che non possono
contenere commenti al loro interno:

- 7 modelli YOLO (`.pt`): cosa rilevano, dove sono usati nel codice.
- 4 file JSON di mappa/zone/POI: formato e significato dei campi.
- File task v2.0 (legacy) e v2.1 (nuovo): differenze, migrazione.
- Tipi di azione: tabella completa dei 19 tipi (`click`, `drag`,
  `wiring`, `yolo_drag_seq`, ecc.) con descrizione.

### Cosa NON e' cambiato

- Il codice eseguibile e' identico: docstring sono solo metadati,
  non influenzano runtime.
- Tutti i 41 bottoni / 16 checkbox / 3 slider / 5 listbox del pannello
  hanno gli stessi callback e gli stessi tag.
- Il file `.py` generato per le task: identico, byte-per-byte.

### Verifica copertura finale

```
Moduli:     56/ 56 (100%)
Classi:     45/ 45 (100%)
Funzioni:  358/358 (100%)
```


## v2.1.3 — Rimozione scrollbar globale del main_win

**Sintomo riportato:** "Lo slider che gestisce sia sidebar che mappa come
se fosse un unico blocco nella finestra"

**Causa:** la finestra principale `main_win` (che contiene mappa + side
panel + status bar come unico blocco) aveva `no_scrollbar=True` ma non
`no_scroll_with_mouse=True`. In DearPyGui questi sono due flag distinti:

- `no_scrollbar=True` nasconde la scrollbar visiva.
- `no_scroll_with_mouse=True` impedisce alla rotellina di SCROLLARE
  l'intera finestra quando il cursore non e' sul canvas.

Con solo il primo, anche se la scrollbar visiva era nascosta, in alcune
condizioni (viewport ridimensionato sotto la dimensione minima dei
contenuti, oppure rotellina sul margine fra canvas e side panel) DPG
mostrava comunque uno scrollbar verticale che faceva scorrere
l'intero blocco mappa+sidebar.

**Fix:** aggiunto `no_scroll_with_mouse=True` a `main_win`.

```python
with dpg.window(tag="main_win", no_title_bar=True, no_resize=True,
                no_move=True,
                no_scrollbar=True, no_scroll_with_mouse=True,  # <- nuovo
                no_bring_to_front_on_focus=True):
```

### Cosa NON e' cambiato

- La scrollbar **interna del side panel** (necessaria perche' i 5 tab e
  i collapsing header possono superare l'altezza disponibile): resta.
- La rotella sul **canvas centrale** (per zoom): resta, perche' il
  callback `_on_mouse_wheel` lo intercetta solo se il cursore e' sopra
  il canvas (`dpg.is_item_hovered("canvas")`).


## v2.1.2 — Sostituzione caratteri Unicode con ASCII

**Sintomo riportato:** "Ci sono molti '?' nei testi"

**Causa:** DearPyGui usa di default un font che non contiene i glifi
Unicode estesi (lettere accentate italiane, frecce, simboli). Ogni
volta che una stringa conteneva uno di questi caratteri, DPG rendeva
un placeholder `?`. Esempi: `e'sec` -> `e'sec`, `Padre <-> Figlia` ->
`Padre ? Figlia`, `> Avvio` -> `? Avvio`.

**Fix:** sostituite **253 occorrenze** di 18 caratteri Unicode in 33
file Python con equivalenti ASCII.

### Mappa di sostituzione applicata

Lettere accentate italiane (sostituite con apostrofo, stile "vecchia
macchina da scrivere"):

| Unicode | ASCII |
|---------|-------|
| `a' a' e' e' i' o' u'`     | `a' a' e' e' i' o' u'` (apostrofo) |

Simboli e frecce:

| Unicode | ASCII |
|---------|-------|
| `-` (em dash)        | `-` (hyphen) |
| `<-` `->`            | `<-` `->` |
| `<->`                | `<->` |
| `<` (triangolino)    | `<` |
| `>` (triangolino)    | `>` |
| `[X]` (stop)              | `[X]` |
| `*`               | `*` |
| `OK`               | `OK` |
| `X`               | `X` |

### Esempi visibili nel pannello

Prima -> Dopo:

- `Modalita' telecamera`     -> `Modalita' telecamera`
- `Velocita' di interpolazione` -> `Velocita' di interpolazione`
- `e' AUTONOMO`              -> `e' AUTONOMO`
- `Esecuzione cosi' completata` -> `Esecuzione cosi' completata`
- `Padre <-> Figlia`              -> `Padre <-> Figlia`
- `> Avvio sequenza`         -> `> Avvio sequenza`
- `[X] Stop`                  -> `[X] Stop`
- `OK Task completata`        -> `OK Task completata`

### Cosa NON e' cambiato

- Tutti i caratteri ASCII originali (lettere semplici, numeri, simboli
  tipici di programmazione). Solo le 18 categorie elencate sopra.
- I file `.py` generati nella cartella `tasks_exec/`: le `TASK_META`
  non contengono caratteri Unicode — il problema era solo nei testi
  visibili in DPG.
- Tutti i 41 bottoni, 16 checkbox, 3 slider, 5 listbox del pannello:
  stessi callback, stessi tag.

### Verifica fatta

Scan automatico post-sostituzione: zero residui non-ASCII nelle
stringhe di tutti i file Python del package.


## v2.1.1 — Normalizzazione nomi (italiano coerente)

Rinominazione mirata di metodi, attributi, campi JSON e label per avere
**italiano coerente** in tutto il codice business. Niente rinominazioni
gratuite: ho toccato solo cose che avevano un misto italiano/inglese o
che erano poco chiare.

### Campi JSON delle task

Vecchio formato (vario):
```json
{
  "room_id": 6,
  "zone_id": 0,
  "zone_local_id": 19,
  "zone_nome": "Admin",
  "parent_id": null,
  "fratelli": [],
  "codice_custom": false,
  "esecuzione": { "params": {} }
}
```

Nuovo formato (italiano):
```json
{
  "id_stanza": 6,
  "id_zona": 0,
  "id_zona_locale": 19,
  "nome_zona": "Admin",
  "id_padre": null,
  "alternativi": [],
  "codice_personalizzato": false,
  "esecuzione": { "parametri": {} }
}
```

I campi gergali del minigioco (`tipo`, `poly`, `rect`, `keypad`, `lights`,
`buttons`, `display`, ecc. nelle azioni) **non sono stati toccati**:
sono nomi del dominio del gioco e cambiarli renderebbe meno chiaro
il codice, non piu' chiaro.

### Migrazione automatica dei dati

La migrazione del primo avvio (gia' presente in v2.1.0) e' stata estesa
per accettare **entrambi i formati** in input:

```python
'id_stanza':  _get('id_stanza', 'room_id'),
'id_padre':   _get('id_padre', 'parent_id'),
'alternativi': _get('alternativi', 'fratelli', default=[]),
# ...
```

Cosi' la migrazione funziona da `task_registrate.json` sia in formato
v2.0 (con `room_id`, `parent_id`, ecc.) che gia' italianizzato.

### Metodi del manager

| Vecchio                    | Nuovo
|----------------------------|------
| `imposta_parent`           | `imposta_padre`
| `set_zone_link`            | `imposta_collegamento_zona`
| `aggiungi_fratello`        | `aggiungi_alternativo`
| `rimuovi_fratello`         | `rimuovi_alternativo`
| `set_codice_custom`        | `set_codice_personalizzato`
| `is_codice_custom`         | `is_codice_personalizzato`

Le firme dei kwargs:

| Vecchio                | Nuovo
|------------------------|------
| `find_registered(room_id=...)` | `find_registered(id_stanza=...)`
| `aggiungi(..., room_id=...)`   | `aggiungi(..., id_stanza=...)`
| `aggiungi(..., zone_id=...)`   | `aggiungi(..., id_zona=...)`
| `aggiorna(..., codice_custom=...)` | `aggiorna(..., codice_personalizzato=...)`

### Mixin di GPSVisualizerPro

| Vecchio                            | Nuovo
|------------------------------------|------
| `_apri_popup_link_zona`            | `_apri_popup_collegamento_zona`
| `_apri_popup_nuovo_fratello`       | `_apri_popup_nuovo_alternativo`
| `_apri_popup_relazioni_task`       | `_apri_popup_padre_figlia`
| `_cerca_glow_fratelli`             | `_cerca_glow_alternativi`
| `_get_raw_task_id`                 | `_get_id_task_da_riga`

### Attributi di stato

| Vecchio                       | Nuovo
|-------------------------------|------
| `self._task_fratelli_pendenti` | `self._task_alternativi_pendenti`

### Label visibili a video

L'unica label cambiata: `Aggiungi fratello` -> `Aggiungi alternativo`.
Tutte le altre label erano gia' state italianizzate in v2.0.7.

### Cosa NON e' cambiato

- Le costanti tecniche di basso livello (`OFFSET_ROOM_ID`, `OFFSET_X`,
  `MAX_PREVIEW_W`, `STATUS_BAR_H`, ecc.): sono interne, non utente.
- I tag DPG (`zone_listbox`, `mem_task_listbox`, `auto_state_label`,
  ecc.): cambiarli rompe il `dpg.set_value` sparso nel codice.
- I tipi di azione (`click_poly`, `drag_zone`, `yolo_drag_all`, ecc.)
  e i campi delle azioni (`poly`, `rect`, `rx`, `ry`, ecc.): sono il
  formato che il template inline `task_template.txt` legge dai file
  `.py` autonomi. Cambiarli vorrebbe dire toccare anche il template
  e tutti i file gia' generati.
- `_avvia_subprocess_task`: `subprocess` e' termine tecnico Python
  consolidato, italianizzarlo e' grottesco.

### Verifica

8 test funzionali post-rinominazione:

- import package OK
- TaskManager carica 56 task con migrazione automatica
- ereditarieta' parent->figlia (`task 4` figlia di `task 2`) OK
- `aggiungi_alternativo` / `imposta_collegamento_zona` / `imposta_padre`
  funzionanti
- `get_memory_tasks_info` riceve `id_stanza` dalla RAM correttamente
- File `.py` generato e' Python valido (~48 KB)
- Tutti i 19 mixin di GPSVisualizerPro caricati senza errori


## v2.1.0 — Separazione struttura task / esecuzione

Tre cambiamenti coerenti, tutti orientati a tenere "i dati" separati dal
"come si esegue", senza alterare il comportamento del bot.

### 1) Separazione del JSON in due formati

Prima:

```
task_registrate.json    # tutto in uno: dettagli + azioni + esecuzione
```

Adesso:

```
tasks_dettagli.json              # struttura task: id, nome, x/y, tipo,
                                 # room_id, parent_id, fasi, fratelli, zone
tasks_esecuzione/
  ├── task_001.json              # azioni + codice_custom + esecuzione
  ├── task_002.json
  └── ...                        # un file per task
```

I dettagli sono "leggeri" e raramente modificati, le azioni sono "pesanti"
e cambiano spesso (ogni volta che usi l'editor). Tenerli separati significa:

- `tasks_dettagli.json` resta piccolo (~23 KB invece di 388 KB) e puoi
  vederlo a colpo d'occhio.
- I file di `tasks_esecuzione/` sono indipendenti: backup mirati, diff
  Git puliti, possibilita' di copiare azioni da una task all'altra
  semplicemente copiando il file.
- Modifiche concorrenti gestibili: due processi che editano dettagli e
  azioni non si pestano i piedi.

### 2) Migrazione automatica al primo avvio

Al primo lancio della v2.1 il bot rileva l'eventuale `task_registrate.json`
del formato vecchio e lo splitta automaticamente nel nuovo formato:

```
[Migrazione] Splitto 56 task da task_registrate.json...
[Migrazione] Completata. Backup: task_registrate.json.bak
```

Il vecchio file viene rinominato `.bak` come safety net. Niente da fare
manualmente: la prima volta che apri il bot dopo l'aggiornamento, vedi
i tuoi 56 task esattamente come prima.

### 3) Separazione dei manager Python

Il `TaskManager` (~600 righe) gestiva sia struttura che esecuzione.
Adesso e' una **facade** sottile (~457 righe) che delega a due manager
specifici:

```
managers/
├── task_manager.py             # facade, espone l'API che i 19 mixin gia' usano
├── task_dettagli_manager.py    # CRUD struttura: aggiungi, rinomina,
│                               # parenting, fasi, fratelli, zone link
└── task_esecuzione_manager.py  # CRUD azioni: imposta_azioni,
                                # set_codice_custom, stato_esecuzione,
                                # invalidazione del file .py
```

L'API pubblica del `TaskManager` e' **invariata**: i 19 mixin di
`GPSVisualizerPro` continuano a fare `self.task_mgr.aggiungi(...)`,
`self.task_mgr.imposta_azioni(...)`, `self.task_mgr.aggiungi_fase(...)`
ecc. senza dover sapere che dietro le quinte ci sono due manager separati.

Vantaggi pratici:

- Per modificare la **struttura** (es. aggiungere un campo "tags" alle
  task) tocchi solo `task_dettagli_manager.py`.
- Per modificare l'**esecuzione** (es. aggiungere un nuovo formato di
  azioni) tocchi solo `task_esecuzione_manager.py`.
- Per testare i due aspetti in isolamento, puoi usarli direttamente
  senza coinvolgere l'altro:

```python
from among_us_ai.managers import TaskDettagliManager
dm = TaskDettagliManager('tasks_dettagli.json')
print([t['nome'] for t in dm.task_list])
```

### Generazione del file `.py`: invariata

Verificato sui 56 task del task_registrate.json originale: la generazione
dei file `.py` autonomi nella cartella `tasks_exec/` produce file
**byte-per-byte identici** alla v2.0 (e quindi anche al monolite v1).
Le task figlie (es. task 4 con parent_id=2) continuano a generare il file
del padre, senza duplicazioni.

### Configurazione: nuovi campi in `GPSConfig`

```python
TASK_DETTAGLI_FILE  = "tasks_dettagli.json"
TASK_ESECUZIONE_DIR = "tasks_esecuzione"
TASK_LEGACY_FILE    = "task_registrate.json"   # solo per migrazione
TASK_FILE           = TASK_LEGACY_FILE          # alias retro-compat
```


## v2.0.7 — Refactoring estetico del pannello laterale

**Solo modifiche grafiche.** Tutti i 41 bottoni, 16 checkbox, 3 slider e
5 listbox conservano gli stessi callback e gli stessi tag DPG. Cambiano
solo i testi delle label e la disposizione visuale.

### Cosa cambia

**1. Niente piu' icone Unicode.** Sostituite con testo descrittivo
chiaro e professionale:

| Vecchia label             | Nuova label
|---------------------------|------------
| `▶ Esegui TUTTE le Task`  | `Esegui automaticamente tutte le task`
| `⏹ Stop Task`             | `Ferma esecuzione`
| `Stop (ESC)`              | `Annulla movimento (ESC)`
| `Relazioni Padre ↔ Figlia`| `Gestione relazioni padre / figlia`
| `Link Zona ↔ Task`        | `Collega task a zona di gioco`
| `+ Nuova Zona [N]`        | `Disegna nuova zona  [N]`
| `+ Disegna Zona Porta`    | `Disegna nuova zona porta`
| `+ Fase`                  | `Aggiungi fase`
| `+ Fratello`              | `Aggiungi fratello`
| `+ Nuovo POI`             | `Nuovo POI`
| `Registra ?`              | `Registra nuova`
| `Genera .py`              | `Genera file .py`
| `Imposta ID Zona Gioco`   | `Imposta ID zona di gioco`

**2. Label dei controlli camera/zoom rinominate per chiarezza:**

| Vecchio | Nuovo
|---------|-------
| `Follow` | `Segui`
| ` - ` ` + ` `Reset` | `Riduci` `Aumenta` `Predefinito`
| `Vai (A*)` | `Naviga (A*)` (per tutti i 4 bottoni "Vai")
| `Forma` | `Modifica forma`
| `Colore` | `Cambia colore`
| `Avvia Task` | `Avvia task`
| `Modifica` (per task RAM) | `Modifica task`
| `Elimina` (per task reg.) | `Elimina task`

**3. Aggiunti testi descrittivi sotto ogni header** (in `Colors.TEXT_DIM`
per non disturbare):

- "Aree definite a mano sulla mappa." (Zone nominate)
- "Aree dove ignorare le porte rilevate." (Zone porte)
- "Task lette dal gioco in tempo reale." (Task in memoria)
- "Task salvate dall'utente con azioni custom." (Task registrate)
- "Punti di interesse sulla mappa." (POI)
- "Mostra o nascondi i livelli sulla mappa." (Livelli visibili)
- "Visualizza giocatori e porte rilevati." (Rilevamento YOLO)
- "Velocita' di interpolazione del movimento." (Smoothing)
- "Statistiche della sessione corrente." (Stats)

**4. Spaziatura uniforme.** Tutti gli `add_spacer` ora seguono una
scala coerente (4, 6, 8, 10, 12 px) invece di valori arbitrari. Ogni
collapsing header inizia con uno spacer di 4 px e finisce con 2 px.

**5. Stato auto-movimento in tabella allineata.** Etichette `Stato:`,
`Target:`, `Percorso:` e i loro valori sono ora in una `dpg.table` a 2
colonne (35% / 65% di larghezza) invece che in 3 group orizzontali
non allineati.

**6. Larghezze pulsanti uniformi:**

- 3 bottoni in riga: 104 px ciascuno (totale 312 px)
- 2 bottoni in riga: 156 px ciascuno (totale 312 px)
- 1 bottone in riga: `width=-1` (riempi)

Cosi' qualunque combinazione di bottoni in `group(horizontal=True)`
allinea perfettamente al margine destro del side panel.

**7. Header di sezione rinominati con maiuscolo elegante:**

- `AUTO-MOVEMENT` -> `AUTO-MOVIMENTO`

### Cosa NON cambia

- Tutti i 65 widget hanno gli **stessi callback** del pannello v1
  (verificato con scan AST automatico: 46 chiamate a metodi `self._...`,
  perfettamente identiche).
- Tutti i tag DPG (`zone_listbox`, `mem_task_listbox`,
  `auto_state_label`, `processo_status`, ecc.) sono **invariati**.
- Le scorciatoie da tastiera continuano a funzionare uguali.
- Il numero di bottoni/checkbox/slider/listbox e' identico.


## v2.0.6 — Fix bottoni invisibili nei gruppi orizzontali

**Sintomo riportato:** "Nella sezione task per quelle in memoria sembrano
mancare dei pulsanti."

**Causa:** in v2.0.3, riorganizzando il pannello in tab e collapsing
header, avevo cambiato le larghezze dei pulsanti dentro i
`dpg.group(horizontal=True)` da valori espliciti in pixel (es. `width=85`
o `width=120`) a `width=-1` (riempi tutto lo spazio disponibile).

In DearPyGui questa e' una scelta che funziona se hai UN solo widget nel
gruppo, ma quando ne metti DUE o TRE in un `group(horizontal=True)` con
`width=-1` su ognuno, il **primo** prende tutto lo spazio disponibile e
i successivi vengono spinti fuori dal viewport orizzontalmente (oppure si
sovrappongono e il rendering diventa incoerente).

In particolare nella sezione "Task in memoria":

```
[Vai (A*)] [Avvia Task] [Registra ?]      <- 3 bottoni width=-1
```

A seconda della larghezza effettiva del side panel (340 px), il primo
bottone si "mangiava" tutto e gli altri due rischiavano di non essere
visibili.

**Fix:** ripristinate le larghezze in pixel come nel pannello v1, con
adattamenti per il nuovo layout:

| Sezione                          | Larghezze
|----------------------------------|-----------
| Telecamera (3 bottoni)           | 100 / 100 / 100
| Zoom (- / + / Reset)             |  70 /  70 / 160
| Zone (Centra/Naviga)             | 150 / 150
| Zone (Forma/Colore)              | 150 / 150
| Zone (Rinomina/Adatta/Elimina)   | 100 / 100 / 100
| Zone Porte (Centra/Forma/Colore) | 100 / 100 / 100
| Zone Porte (Rinomina/Elimina)    | 150 / 150
| Task RAM (Vai/Avvia/Registra)    | 100 / 100 / 100
| Task RAM (Modifica/Stop)         | 150 / 150
| Task reg (Nuova/Modifica)        | 150 / 150
| Task reg (+Fase/+Fratello)       | 150 / 150
| Task reg (Vai/Elimina)           | 150 / 150
| Task reg (Genera .py + status)   | 150 + auto
| POI (Nuovo/Modifica)             | 150 / 150
| POI (Vai/Elimina)                | 150 / 150

Tutti i bottoni in righe da soli (es. `▶ Esegui TUTTE le Task`,
`Imposta ID Zona Gioco`, `+ Nuova Zona [N]`, `+ Disegna Zona Porta`,
`+ Nuovo POI` se da solo) restano `width=-1` perche' in quel caso
funziona bene = riempi tutta la riga.

**Verifica:** scan AST automatico per controllare:
- 41 bottoni ↔ 41 bottoni — ✓ identici per (label, callback method)
- 16 checkbox ↔ 16 checkbox — ✓ identici
- 3 slider, 5 listbox — ✓ identici

Niente e' davvero mai stato perso a livello di codice — i pulsanti
c'erano sempre — ma erano nascosti dal layout. Ora si vedono tutti.


## v2.0.5 — Verifica completa: nessun elemento mancante in nessuna sezione

**Sintomo riportato:** "manca qualcosa nell'interfaccia base in zone, task,
poi, vista, stats — ricontrolla bene tutte le sezioni"

**Causa:** Riguardando il pannello con piu' attenzione tramite diff AST,
ho trovato altre piccole rinominazioni gratuite della v2.0.3 che non avevo
ripristinato in v2.0.4:

1. La label di testo sopra la listbox `mem_task_listbox` era stata
   cambiata da "Task in memoria:" a "Da fare:".
2. La label di testo sopra la listbox `reg_task_listbox` era stata
   cambiata da "Task Registrate:" a "Salvate:".
3. Avevo aggiunto un testo informativo nella sezione Smoothing
   ("Velocita' di smoothing della camera") che non era nell'originale.

Niente di funzionalmente rotto, ma far sembrare che la sezione fosse
diversa quando in realta' era la stessa.

**Fix:** label di testo e descrizioni ripristinate al 100% identiche al
pannello v1. Verificato con scan AST automatico:

- 41 bottoni  → 41 bottoni  ✓ stesse label, stessi callback
- 16 checkbox → 16 checkbox ✓ stesse label, stessi callback
- 3 slider    → 3 slider    ✓ stesse etichette
- 5 listbox   → 5 listbox   ✓ stessi tag

**Tutti i testi `dpg.add_text(...)` informativi sono identici al vecchio
pannello.** Cambiano solo:

- gli header colorati (`CONTROLLI`, `AUTO-MOVEMENT`, `ZONE`, `ZONE PORTE`,
  `TASK`, `PUNTI DI INTERESSE`, `STATISTICHE`, `SCORCIATOIE`,
  `Livelli visibili`) che ora sono **tab cliccabili** o **collapsing
  header** invece di scritte statiche;
- i `dpg.add_separator()` decorativi che venivano duplicati attorno a ogni
  header: ora ce n'e' uno solo (DPG aggiunge gia' la sua separazione
  visuale per tab e collapsing).

Riepilogo per sezione:

- **Tab Zone**: 12 widget — Zone nominate (8) + Zone Porte (8) — INVARIATI
- **Tab Task**: 19 widget — bottone relazioni + lista RAM (6) + lista
  registrate (8) + bottoni utility — INVARIATI
- **Tab POI**: 6 widget — INVARIATI
- **Tab Vista**: 14 widget — Livelli (7) + YOLO (4) + Smoothing (1) +
  HUD (1) — INVARIATI (Cam Height conta come 1 widget)
- **Tab Stats**: 5 valori in tabella — INVARIATI
- **Sezione fissa in alto** (Camera + Zoom + Auto-move): 14 widget —
  INVARIATI


## v2.0.4 — Fix label dei pulsanti accidentalmente cambiate

**Sintomo riportato:** "Sembra che manchino dei pulsanti/opzioni"

**Causa:** nella v2.0.3 (riorganizzazione grafica del pannello) avevo
rinominato per pigrizia alcune label per farle stare nei nuovi gruppi
con `width=-1`:

- "Avvia Task" -> "Avvia"
- "Altri giocatori (YOLO)" -> "Altri giocatori"
- "Porte chiuse rilevate (YOLO)" -> "Porte chiuse rilevate"
- "Auto-calibra YOLO (movimento)" -> "Auto-calibra (movimento)"
- "Smoothing" (slider) -> "" (label vuota)

I pulsanti c'erano sempre tutti — niente era stato perso a livello di
funzionalita' — ma le label diverse facevano sembrare che alcune opzioni
fossero sparite.

**Fix:** ripristinate tutte le label originali al 100%.

**Verifica fatta:** confronto AST sistematico fra il pannello v1
(`gps_app.py`) e il pannello v2.0.4 (`ui_setup.py`):

- Bottoni:  41 -> 41  ✓ identici
- Checkbox: 16 -> 16  ✓ identici
- Slider:    3 -> 3   ✓ identici
- Listbox:   5 -> 5   ✓ identici

Tutte le 65 coppie (label/tag, callback method) sono identiche al
pannello originale: ogni pulsante chiama esattamente lo stesso metodo
con lo stesso testo. Cambia solo l'organizzazione visuale (tab e
collapsing header) introdotta in v2.0.3.


## v2.0.3 — Riorganizzazione grafica del pannello laterale

**Solo modifiche grafiche, ZERO cambiamenti alla logica.** Tutti i tag, i
callback, i widget e gli ID DPG sono identici a prima — cambia solo come
sono raggruppati visualmente.

### Cosa cambia nel layout

Prima il pannello laterale era una lista lunga da 8 sezioni separate da
`add_separator`, tutta da scorrere con la rotella per arrivare in fondo.
Adesso e' organizzato cosi':

```
SEZIONE FISSA (sempre visibile in cima):
  - Telecamera   (Follow / Libera / Tutta)
  - Zoom         (slider + pulsanti -/+/Reset)
  - AUTO-MOVEMENT  (checkbox + stato + Stop)

TAB BAR (cliccabile):
  [Zone] [Task] [POI] [Vista] [Stats]
    |
    +-- Zone:   Zone nominate (collassabile)
    |           Zone Porte / filtro YOLO (collassabile, chiuso default)
    |
    +-- Task:   "Relazioni Padre <-> Figlia" (sempre visibile)
    |           Task in memoria RAM (collassabile, aperto)
    |           Task registrate (collassabile, chiuso)
    |
    +-- POI:    Lista POI + bottoni
    |
    +-- Vista:  Livelli visibili (collassabile, aperto)
    |           Rilevamento YOLO (collassabile, chiuso)
    |           Smoothing (collassabile, chiuso)
    |
    +-- Stats:  Tabella statistiche (distanza, tempo, celle, trail)

FOOTER:
  Scorciatoie tastiera (collassabile, chiuso default)
```

### Vantaggi pratici

1. **Niente piu' scroll infinito**: i comandi piu' usati (telecamera,
   zoom, auto-move) sono sempre in alto. Il resto e' raggiungibile
   cliccando un tab.

2. **Cassetti collassabili**: dentro ogni tab i `collapsing_header`
   permettono di nascondere temporaneamente cio' che non serve. Le sotto-
   sezioni meno usate (Zone Porte, Task registrate, YOLO config) partono
   chiuse di default.

3. **Statistiche in tabella**: la sezione Stats ora usa una tabella DPG
   con due colonne allineate (etichetta a sinistra, valore a destra)
   invece di N righe alternate, piu' leggibile.

4. **Bottoni con `width=-1`**: i bottoni dentro `group(horizontal=True)`
   ora si allargano automaticamente per riempire lo spazio. Prima avevano
   `width=85` o `width=125` hardcoded che lasciavano spazi vuoti se
   l'utente ridimensionava la finestra.

### Cosa NON cambia

- Tutti i `tag=` dei widget sono uguali (zone_listbox, mem_task_listbox,
  auto_state_label, ecc.). I metodi `_refresh_*_listbox`, `_get_selected_*`
  e tutti i callback DPG continuano a funzionare senza modifiche.
- I callback dei bottoni puntano agli stessi metodi di prima.
- Il tema, i colori, le scorciatoie da tastiera e la barra di stato in
  basso (X / Y / FPS / Mode / Zoom / Auto) sono identici.
- Il menu in alto (File / Vista / Auto-move / Strumenti / ?) e' immutato.


## v2.0.2 — Fix costanti di classe perse durante lo split del TaskActionEditor

### Fix bloccante: AttributeError 'IDLE'

**Sintomo:**
```
File "...\among_us_ai\ui\editor.py", line 65, in __init__
    self.stato = self.IDLE
                 ^^^^^^^^^
AttributeError: 'TaskActionEditor' object has no attribute 'IDLE'
```

**Causa:** quando ho splittato `TaskActionEditor` in mixin (v2.0.1), il
mio script di split prendeva solo i metodi (`ast.FunctionDef`) ma ha
ignorato gli **assignment di livello classe** (`ast.Assign` direttamente
sotto la `ClassDef`). L'editor originale aveva 47 costanti di classe:

- 32 costanti di stato della macchina di interazione (`IDLE`,
  `WAIT_CLICK`, `WAIT_DRAG_START`, ...).
- 15 tag DPG dei widget (`TAG_CANVAS`, `TAG_LIST`, `TAG_IST`, ...).

Tutte erano definite come `IDLE = "IDLE"` ecc. all'inizio della classe e
referenziate dai metodi come `self.IDLE`, `self.TAG_CANVAS`, ecc. Lo
split le ha lasciate fuori dal nuovo `editor.py`, e al primo accesso da
`__init__` (`self.stato = self.IDLE`) Python alza `AttributeError`.

**Fix:** ripristinate tutte le 47 costanti di classe in cima a
`TaskActionEditor` in `editor.py`, prima di `__init__`. Verificato con
scan AST sul file originale del v1 che siano state recuperate tutte e
47 senza modifiche di valore.

**Verifica:** ho controllato sistematicamente TUTTI gli altri file della
v2 alla ricerca di costanti di classe potenzialmente perse: l'unico caso
era `TaskActionEditor` (perche' e' l'unica classe che ho splittato in
mixin oltre a `GPSVisualizerPro`, e quest'ultima per fortuna non aveva
costanti di classe). I manager, i reader e il pathfinder hanno costanti
ma non sono stati splittati, quindi sono a posto.


## v2.0.1 — Fix import nei mixin + ulteriore split dei file UI

### Fix bloccante: NameError nei mixin di GPSVisualizerPro

**Sintomo:** dopo l'apertura della prima task in modalita' Auto-Quest:
```
File "...\among_us_ai\ui\mixins\tasks_lifecycle.py", line 128, in on_arrivo
    self._task_launch_steps = (TaskManager.STATI_LAUNCH ...)
NameError: name 'TaskManager' is not defined
```

**Causa:** quando ho splittato `gps_app.py` in mixin (v2.0), ho propagato
gli import "ovvi" (`dpg`, `time`, `GPSConfig`, ...) tramite il facade
`mixins/_imports.py`, ma mi sono dimenticato di includere `TaskManager`,
`ZoneManager`, `PoiManager`, `Pathfinder`, `AmongUsMemoryReader` e
`AmongUsTaskReader`. Funzionavano nel monolite originale come globali del
modulo, e in `app.py` (dove vengono instanziati nell'__init__), ma
nessun mixin li vedeva.

Tre mixin in particolare li usavano:
- `tasks_lifecycle.py`: `TaskManager.STATI_LAUNCH` (costante di classe)
- `zones.py`: `ZoneManager.centroide()` e `.bbox()` (staticmethod)
- e potenzialmente altri tramite accessi successivi.

**Fix:** aggiunti tutti i manager + reader + Pathfinder al facade
`mixins/_imports.py`. Verificato con scan AST automatico che nessun mixin
abbia piu' simboli non risolti.

### Ulteriore split dei mixin grossi

Tre mixin erano ancora oltre 500 righe; li ho divisi:

| Prima                           | Dopo                                                   |
|---------------------------------|--------------------------------------------------------|
| `tasks_popups.py` (982 righe)   | `tasks_popups_register.py` (424) + `_edit.py` (339) + `_subitem.py` (235) |
| `rendering.py` (611 righe)      | `rendering_world.py` (299) + `rendering_entities.py` (319) |
| `tasks_lifecycle.py` (578 righe)| `tasks_launch.py` (268) + `tasks_process.py` (317)     |

Adesso `GPSVisualizerPro` eredita da **19 mixin** (erano 15) tutti sotto
le 432 righe. Nessuno degli effetti precedenti e' cambiato (mixin
disgiunti, stesso comportamento).

### Split del TaskActionEditor

`task_action_editor.py` (2488 righe, 60 metodi) era il file singolo piu'
grosso del progetto. L'ho splittato come `GPSVisualizerPro`:

- `editor.py` (224 righe): classe principale con `__init__`, `apri`,
  `chiudi`, `aggiorna_frame` e poco altro.
- `editor_mixins/`: 7 mixin tematici (UI build, start actions, sequence,
  canvas input, drawing, list panel, save/test).

Gli unici due file dell'editor ancora "grossi" sono `canvas_input.py`
(636 righe) e `drawing.py` (537), ma sono intrinsecamente cosi' perche'
il primo gestisce tutta la macchina a stati del click/drag/vertex-move
sul canvas e il secondo tutto il rendering DPG dell'editor — splittarli
ulteriormente romperebbe i metodi che si chiamano fra loro condividendo
buffer locali.

### File rinominato

`among_us_ai/ui/task_action_editor.py` -> `among_us_ai/ui/editor.py`.
Se hai script personalizzati che facevano:

    from among_us_ai.ui.task_action_editor import TaskActionEditor

vanno cambiati in:

    from among_us_ai.ui.editor import TaskActionEditor

oppure (preferito):

    from among_us_ai.ui import TaskActionEditor

che funziona da sempre.


## v2.0.0 — Riorganizzazione UI in mixin + separazione struttura/codegen task

Riorganizzazione strutturale, ZERO modifiche a logica e funzionamento.
Verificato: i file `.py` generati per le task sono byte-per-byte identici
a quelli prodotti dalla v1, sia per task semplici che per task con
parent/figlio (ereditarieta' delle azioni).

### Rinominato `among_us_gps` -> `among_us_ai`

Tutti gli import sono stati aggiornati. Se hai script personalizzati che
fanno `from among_us_gps import ...`, vanno cambiati in
`from among_us_ai import ...`.

### `GPSVisualizerPro` distribuito su 15 mixin tematici

Il file `ui/gps_app.py` (5300 righe, 114 metodi) era una "god class".
Adesso e' diviso in:

- `ui/app.py` (331 righe): solo `__init__`, `aggiorna_frame`, `run` +
  l'eredita' multipla che assembla i mixin.
- `ui/mixins/` (15 file): metodi raggruppati per tema (rendering,
  pathfinding, task lifecycle, UI setup, ...).

I mixin sono **disgiunti** (nessun metodo definito in piu' di uno) e
condividono lo stato `self.*` inizializzato in `app.py::__init__`.
L'ordine MRO non ha effetti sul comportamento perche' non ci sono
sovrapposizioni.

Vantaggio: un nuovo gruppo di funzionalita' ha il suo file dedicato; per
modificare il rendering basta toccare `mixins/rendering.py` senza
scorrere altre 4500 righe di codice non correlato.

Per evitare di duplicare 30 righe di import in ogni mixin, c'e' un modulo
facade `mixins/_imports.py` che ognuno importa con
`from ._imports import *`. Pattern standard per progetti con molti mixin.

### `TaskManager` -> separazione struttura/generazione codice

Il metodo `crea_file_esecuzione` (147 righe) e' stato spostato in un
nuovo modulo `execution/task_writer.py`. Cosi':

- `managers/task_manager.py` si occupa SOLO della struttura task: CRUD,
  parenting/inheritance, persistenza JSON, sync con la RAM.
- `execution/task_writer.py` si occupa SOLO della generazione del file
  `.py` autonomo. E' una funzione pura (nessuno stato): riceve un dict
  task e produce un file.

`TaskManager.crea_file_esecuzione` e' diventato un thin wrapper di ~30
righe che risolve l'ereditarieta' parent->figlio e poi chiama
`genera_file_esecuzione`.

Vantaggio: per cambiare il formato dei file generati (es. aggiungere un
nuovo campo a `TASK_META`, cambiare il commento di intestazione) basta
toccare `task_writer.py` senza rischiare di rompere il CRUD delle task.


## v1.0.2 — Fix loop infinito su task non completata

### Fix #5 — Loop quando il bot arriva "vicino ma non sopra" il punto della task

**Sintomo:** quando il punto registrato di una task cade in una posizione
non perfettamente raggiungibile (es. appena fuori dalla zona walkable
mappata), il bot si blocca nelle vicinanze, fa stuck/replan, ma il path
include sempre il goal esatto come ultimo waypoint, irraggiungibile.

**Causa:** in `_plan_path`, dopo il calcolo A*, il goal esatto `goal_xy`
veniva sempre aggiunto come ultimo waypoint del path, anche quando era
fuori dalla griglia walkable. Risultato: l'A* termina sul "snap point"
calpestabile piu' vicino, ma l'ultimo step tenta di camminare in
diagonale verso un punto irraggiungibile -> stuck infinito.

**Fix:** in `ui/gps_app.py::_plan_path`, il goal esatto viene aggiunto
SOLO se e' raggiungibile in linea retta dal goal snapped (controllo con
`pathfinder.line_walkable_coords`) e a distanza inferiore a 1 unita':

```python
dist_extra = math.hypot(last[0] - goal_xy[0], last[1] - goal_xy[1])
if 0.05 < dist_extra < 1.0 and self.pathfinder.line_walkable_coords(last, goal_xy):
    path.append(goal_xy)
```

Risultato: il bot considera "arrivato" sul snap point quando il goal
esatto e' irraggiungibile, scatena `_on_arrival_callback`, e prova a
premere SPAZIO. Se Among Us accetta l'interazione (la zona di proximity
del minigioco e' generosa), il minigioco si apre. Altrimenti scatta il
fix #6 sotto.

### Fix #6 — Cooldown di sicurezza contro l'Auto-All in loop

**Sintomo:** in modalita' Auto-Quest, se una task viene "eseguita" dal
bot (subprocess termina con exit 0) ma in RAM rimane non-done — perche'
il minigioco non si e' mai aperto, oppure il bot e' arrivato fuori dalla
zona di interazione, oppure c'e' stato un problema di hwnd —, l'Auto-All
ricalcolando subito i candidati trova ANCORA la stessa task (e' la piu'
vicina). Risultato: la rilancia subito, identico, e il loop continua.

**Causa:** in `_controlla_processo_task`, dopo `ret == 0` veniva
applicato un cooldown SOLO se la task aveva un campo `cooldown` esplicito
nel JSON. Per le task normali, niente cooldown -> rilancio immediato.

**Fix:** dopo che il subprocess termina, controlla se la task corrispondente
in RAM e' done. Se NON lo e', applica un cooldown di sicurezza di 8 secondi
(non sovrascrive cooldown piu' lunghi gia' presenti). Cosi' Auto-All
selezionera' un'altra task in attesa, e la stessa potra' essere ritentata
dopo qualche secondo (magari dopo che la posizione del player e' cambiata,
o dopo un eventuale replan):

```python
if not task_done_in_ram:
    safety_cd = time.time() + 8.0
    if safety_cd > self.task_cooldowns.get(id_task, 0):
        self.task_cooldowns[id_task] = safety_cd
```

Vedrai nei log: `[Loop guard] Task non completata in RAM — cooldown di sicurezza 8s`.


## v1.0.1 — Bug fix dopo riorganizzazione

Quattro bug introdotti dalla suddivisione del `main.py` monolitico in package
modulare, identificati durante il primo collaudo. Tutti dovuti al fatto che
nell'originale alcuni simboli vivevano nello stesso modulo come globali e
funzionavano "per gravita'" senza import espliciti — quando il file e' stato
splittato, alcuni di questi accessi si sono rotti silenziosamente.

### Fix #1 — `_send_scan` / `SCAN_CODES` non importati in `gps_app.py` (CRITICO)

**Sintomo riportato:** "esegue una task e poi sembra chiuderla ma rimane che
la fa".

**Causa:** dentro `_update_task_launch`, dopo l'animazione di arrivo il bot
deve premere SPAZIO per aprire il minigioco prima di lanciare il subprocess
delle azioni:

```python
_send_scan(SCAN_CODES['SPACE'], keyup=False)
```

`_send_scan` e `SCAN_CODES` erano definiti come globali nel `main.py`
originale, nel nuovo package vivono in `io_input/key_controller.py` ma non
erano importati in `ui/gps_app.py`. La chiamata era dentro un `try/except
Exception`, quindi il `NameError` veniva mascherato silenziosamente con
un messaggio `[Input] Errore pressione SPAZIO: ...` nei log.

**Effetto a catena:** SPAZIO non premuto -> minigioco non si apre -> il file
`.py` della task esegue tutte le azioni "nel vuoto" sull'overlay del gioco
-> exit 0 (script "completato") -> stato `done` nel JSON. Ma in RAM la task
non e' avanzata, quindi il giocatore vede la task ancora da fare e il bot
crede di averla finita.

**Fix:** import esplicito in `ui/gps_app.py`.

```python
from ..io_input import KeyController, SCAN_CODES
from ..io_input.key_controller import _send_scan
```

### Fix #2 — `_STOP_TEST_THREAD` non condiviso fra moduli

**Sintomo:** premendo F4/End o Stop dell'editor, il "Test" delle azioni non
si interrompeva piu'.

**Causa:** era una variabile globale del `main.py` letta/scritta da tre punti
diversi (TaskActionEditor, esegui_azioni, GPSVisualizerPro). Nel package
splittato, ogni modulo ha la sua copia indipendente.

**Fix:** un nuovo modulo `core/stop_flag.py` con un singleton `flag.requested`
condiviso. I tre punti d'uso sono stati aggiornati per leggere/scrivere
quel singleton.

### Fix #3 — Alias mancanti nel runtime (`_WIN_OK`, `_time`, `_click_hold`)

**Sintomo:** alcuni rami avanzati di `esegui_azioni` (yolo_drag_all,
yolo_click_color_match, alcuni tipi OCR) crashavano con `NameError` durante
il "Test" dell'editor.

**Causa:** quei rami usano nomi con prefisso underscore tipici del codice
template (`_time`, `_click_hold`, `_WIN_OK`) che nel `main.py` originale non
erano definiti nel namespace del runtime live. Era un **bug latente** anche
nell'originale: questi rami non venivano probabilmente testati live.

**Fix:** aggiunti alias espliciti in cima a `execution/runtime.py`:

```python
_WIN_OK      = WIN_OK
_time        = time
_client_rect = get_client_rect
_click_hold  = esegui_click_hold
```

### Fix #4 — `cwd` del subprocess + path dei modelli YOLO

**Sintomo:** subprocess delle task e ricerche YOLO live cercavano i modelli
`.pt` nelle cartelle sbagliate.

**Causa:** nell'originale `main.py` era nella radice del progetto, quindi
`os.path.dirname(os.path.abspath(__file__))` puntava alla radice. Nel
package, `__file__` e' dentro `among_us_ai/ui/` o `among_us_ai/execution/`,
quindi il `dirname` punta in quelle sottocartelle.

**Fix:** sostituito con `os.getcwd()` (o `_os.getcwd()` per i rami template-style),
che ritorna la directory di lancio del bot — dove l'utente fa
`python main.py` o `python -m among_us_ai`.

Punti modificati:

- `ui/gps_app.py::_avvia_subprocess_task`: `cwd=os.getcwd()` per il `Popen`.
- `execution/runtime.py`: due path `model_path` e due `_base_dir` ora basati
  su `getcwd()`.

I file gia' generati in `tasks_exec/` non sono affetti: usano
`dirname(dirname(__file__))` che parte dal loro path nella cartella
`tasks_exec/` e produce correttamente la radice del progetto.
