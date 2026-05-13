# Among Us AI Bot

Bot di navigazione e automazione per Among Us. Legge la posizione del
giocatore direttamente dalla RAM del gioco, mostra una mappa interattiva,
calcola percorsi A* per spostarti automaticamente, registra ed esegue
task semi-automatiche, rileva altri giocatori e porte chiuse con la
visione artificiale (YOLO).

> **Importante**: lo strumento usa input simulato a livello scan-code e
> lettura della RAM del processo del gioco. Funziona solo su **Windows**
> e richiede che Among Us sia in esecuzione.

> **⚠️ Disclaimer — Progetto a scopo esclusivamente didattico**
>
> Questo repository nasce come **esercizio di studio** su visione
> artificiale (YOLO), lettura della memoria di processo, pathfinding A* e
> costruzione di interfacce desktop. È pubblicato a fini **educativi e
> dimostrativi**.
>
> **Non è inteso come un cheat** e non deve essere usato per ottenere
> vantaggi sleali in partite online, pubbliche o competitive: farlo è
> scorretto verso gli altri giocatori e quasi certamente viola i Termini
> di Servizio di *Among Us* (Innersloth). Usalo solo in **partite private
> con amici consenzienti**, in locale, o semplicemente per leggere e
> studiare il codice.
>
> Il progetto non è affiliato né approvato da Innersloth. *Among Us* è un
> marchio dei rispettivi proprietari. L'autore declina ogni
> responsabilità per usi impropri o per eventuali conseguenze (incluse
> sospensioni o ban dell'account) derivanti dall'uso di questo software,
> fornito "così com'è" senza alcuna garanzia.

---

## Indice

1. [Sezione utente](#sezione-utente) — installazione e uso
2. [Sezione sviluppatore](#sezione-sviluppatore) — com'e' fatto dentro

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

Al primo avvio, se hai un `task_registrate.json` di una vecchia
versione, il bot lo migra automaticamente nel nuovo formato (vedi la
sezione sviluppatore).

## Cosa fa il bot

Mentre il bot e' aperto durante una partita, vedi una finestra divisa
in tre zone: la mappa del livello (con l'omino, la scia, le task e il
percorso A*), un pannello laterale di controlli e una barra di stato in
basso.

Le sue funzioni principali:

- **Posizione in tempo reale** sulla mappa, letta dalla memoria del
  gioco, con scia che si accumula muovendoti.
- **Task da fare** mostrate dove si trovano, lette direttamente dalla
  RAM.
- **Percorso A***: cliccando sulla mappa o su una task, il bot calcola
  un percorso che passa solo per le zone calpestabili.
- **Auto-movimento**: il bot cammina al posto tuo premendo W/A/S/D
  simulati.
- **Esecuzione delle task**: dopo aver "insegnato" al bot come fare una
  task (registrando i click con l'editor azioni), puoi farla eseguire
  in automatico.
- **Riconoscimento stato di gioco**: il bot capisce se sei in lobby, in
  partita, in votazione, vivo o fantasma, e si comporta di conseguenza.
- **Rilevamento di altri giocatori e porte chiuse** tramite YOLO.

## Stato del gioco e comportamento automatico

Il bot legge dalla RAM la fase corrente della partita e adatta il suo
comportamento:

- **Menu / pre-lobby**: resta fermo, non pianifica nulla.
- **In partita (vivo)**: esegue il giro delle task.
- **Votazione / meeting**: se era a meta' di una task, la abbandona
  subito (preme ESC per chiudere il minigioco) e aspetta. Finito il
  meeting, riprende da solo.
- **Morte (fantasma)**: riparte il giro in modalita' fantasma; da morto
  i percorsi vanno in linea retta perche' si attraversano i muri.

## Modalita' "Avvia tutte le task" (Auto-All)

E' la modalita' automatica completa: il bot sceglie da solo la prossima
task, ci naviga, la esegue e passa alla successiva, in loop.

- Sceglie la task in base a un punteggio che bilancia distanza e
  priorita'. Con l'opzione **"Percorso piu' breve"** (attiva di default)
  va sempre alla task piu' vicina, per fare meno strada.
- I **sabotaggi** (task "vitali": Reactor, O2, Lights, Comms) hanno
  priorita' assoluta. Se durante il viaggio verso un sabotaggio questo
  viene risolto, il bot se ne accorge, abbandona quel target e
  ricalcola il giro.
- Quando una task finisce, ricontrolla la RAM per vedere se risulta
  completata e passa alla prossima.

Si avvia e si ferma con il tasto **F4** o con il bottone nel pannello.

## Reset partita e auto-reset

- **Reset partita** (tasto **F5** o menu Strumenti): azzera tutti gli
  stati di progresso (task in corso, cooldown, navigazione, dati di
  sessione) senza toccare le task registrate, le zone, i POI o la
  mappa. Utile per ripartire puliti.
- **Auto-reset tra le partite** (checkbox nel menu Strumenti): se
  attivo, il bot esegue il reset automaticamente quando rileva l'inizio
  di una nuova partita.

## Scorciatoie da tastiera

Alcune scorciatoie sono globali (funzionano anche con il gioco in primo
piano), altre solo quando la finestra del bot e' attiva.

### Tasti globali

| Tasto | Azione |
|-------|--------|
| **F1** | Apri/chiudi la preview del giro Auto-All (pannello sinistro) |
| **F2** | Apri/chiudi il pannello Intelligence (pannello destro) |
| **F4** | Avvia / ferma tutte le task (Auto-All). Premuto durante una task, la ferma e annulla. |
| **F5** | Reset partita |
| **FINE (END)** | Stop d'emergenza: ferma tutto immediatamente |

### Tasti con finestra del bot attiva

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
| F3 | Abilita/disabilita Anti-AFK |
| Click sinistro | Imposta destinazione (calcola il percorso A* fin li') |
| Click destro / ESC | Annulla l'operazione corrente |
| Rotellina mouse | Zoom della mappa |
| Tasto centrale + drag | Pan della mappa |

## Pannello laterale

In cima, sempre visibili: le modalita' telecamera (Segui / Libera /
Panoramica), lo zoom della mappa e i controlli dell'auto-movimento.

Sotto, una barra a schede:

| Scheda | Contenuto |
|--------|-----------|
| **Zone** | Aree definite a mano sulla mappa (Cafeteria, MedBay, ...). Bottoni per disegnare, modificare e navigare. Include il filtro "Zone porte" per il rilevamento YOLO. |
| **Task** | Task lette dalla RAM in tempo reale + task registrate dall'utente con azioni personalizzate. Da qui si avvia "tutte le task" e si apre la gestione padre/figlia (ereditarieta' delle azioni). |
| **POI** | Punti di interesse generici (Vent, Admin Panel, ...). |
| **Vista** | Cosa mostrare sulla mappa (griglia, scia, mirino, HUD), configurazione YOLO e smoothing della telecamera. |
| **Stats** | Distanza percorsa, tempo di sessione, celle calpestabili, punti del trail. |

Nel menu in alto, la voce **Strumenti** raccoglie reset partita,
auto-reset, "percorso piu' breve", calibrazione del pulsante Use e
pulizia di trail/statistiche.

## Come si registra una task

1. Avvicinati alla task in gioco (es. "Swipe Card" in Admin).
2. Nella scheda "Task", se non e' tra le "Task registrate",
   selezionala dalle "Task in memoria" e clicca "Registra nuova".
3. Aprila con "Modifica task" e poi "Modifica azioni" per entrare
   nell'editor.
4. Nell'editor scegli un'azione (es. "Avvia click semplice" o "Avvia
   drag") e clicca sulla preview dello screenshot del gioco per
   registrarne le coordinate.
5. "Salva e chiudi" al termine.
6. Dal pannello principale, "Genera file .py" produce il file
   autonomo in `tasks_exec/` che il bot esegue per fare la task.

## Calibrazione del pulsante "Use"

Per eseguire una task il bot deve aprire il minigioco. Lo fa cliccando
il pulsante **Use** in basso a destra: per sapere dove cliccare (e per
capire quando il pulsante e' acceso) serve una calibrazione una tantum.

Dal menu **Strumenti → Calibra pulsante 'Use'**, segui le istruzioni
per selezionare l'area del pulsante. Senza calibrazione il bot usa un
fallback (pressione del tasto SPAZIO), meno preciso.

## File di configurazione

Il bot legge alcuni file JSON dalla cartella radice:

| File | Contenuto |
|------|-----------|
| `mappa_skeld.json` | Celle "calpestabili" della mappa (dove un giocatore puo' stare). |
| `zone_skeld.json` | Zone nominate a mano (poligoni con nome e colore). |
| `door_zones_skeld.json` | Zone porte per il filtro del rilevamento YOLO. |
| `poi_skeld.json` | Punti di interesse. |
| `tasks_dettagli.json` | Struttura delle task registrate (id, nome, posizione, fasi, alternativi, padre). |
| `tasks_esecuzione/task_<id>.json` | Azioni di una specifica task (un file per task). |
| `use_button_calibration.json` | Calibrazione del pulsante Use (creata dallo strumento). |
| `dati_memoria/script.json` | Dump opzionale degli indirizzi RAM: se presente, il bot lo usa per configurarsi (utile dopo un aggiornamento del gioco). |

## File di asset

I file `.pt` sono i modelli YOLO (PyTorch) per il riconoscimento visivo:
freccia di navigazione, gli ostacoli del minigioco asteroidi, le foglie
da rimuovere in O2, i vent, le porte chiuse e gli altri giocatori sulla
mappa. `requirements.txt` elenca le dipendenze Python (`pymem`,
`pyautogui`, `dearpygui`, `numpy`, `opencv-python`, `pywin32`, `mss`,
`Pillow`, `easyocr` e `ultralytics` per YOLO).

## Avvertenza e uso responsabile

Lo ripetiamo perché è importante: questo è un **progetto didattico**, non
uno strumento pensato per barare.

- **Non usarlo in partite online o pubbliche.** Automatizzare il gioco
  rovina l'esperienza agli altri e viola i Termini di Servizio.
- **Contesto consigliato**: partite private con amici d'accordo, ambienti
  di test locali, oppure studio del codice senza eseguirlo.
- **Nessuna garanzia**: il software è fornito "as is"; l'uso è a tuo
  rischio e l'autore non risponde di ban, malfunzionamenti o altri danni.
- Rispetta sempre il gioco, gli altri giocatori e i creatori (Innersloth).

---

# Sezione sviluppatore

## Architettura ad alto livello

Il bot e' un'applicazione DearPyGui (DPG) a processo singolo che
orchestra piu' thread:

- **Thread principale (DPG)**: rendering, input, callback della UI e il
  loop di aggiornamento per frame.
- **Thread RAM**: legge in continuo la posizione e la lista delle task
  via `pymem`.
- **Thread YOLO**: scanner periodico che cattura screenshot e fa
  inferenza per rilevare altri giocatori e porte chiuse.
- **Subprocess**: quando si avvia una task, il bot lancia un processo
  Python separato (un file in `tasks_exec/`) che simula i click del
  minigioco. Il subprocess viene preparato in anticipo (pre-warming) e
  attende un segnale "GO" sullo stdin: il bot lo invia subito dopo aver
  aperto il pannello della task.

## Organizzazione del codice

Il package `among_us_ai/` e' suddiviso per responsabilita':

- `core/` — configurazione (`config.py`: `GPSConfig` + palette
  `Colors`), helper geometrici, il flag di stop globale e gli import
  opzionali Windows.
- `io_input/` — controller della tastiera (SendInput a livello
  scan-code).
- `pathfinding/` — A* su griglia con string-pulling, piu' la variante
  in linea retta per i fantasmi.
- `game_io/` — lettura della RAM via `pymem`, con caricamento opzionale
  degli indirizzi da `dati_memoria/script.json`.
- `managers/` — `TaskManager` (facade) sopra i sub-manager di struttura
  ed esecuzione delle task, piu' i manager di zone e POI e il
  pianificatore del giro.
- `execution/` — il motore di esecuzione: `runtime.py` per il pulsante
  "Test" dell'editor e il package modulare `_motore_pkg/` (copiato in
  `tasks_exec/_motore/`) per i file generati. `task_writer.py` genera i
  thin wrapper `.py` delle task.
- `ui/` — l'applicazione: `app.py` (`GPSVisualizerPro`), `editor.py`
  (`TaskActionEditor`) e i rispettivi mixin in `mixins/` ed
  `editor_mixins/`.

## Le classi principali

### `GPSVisualizerPro` (`ui/app.py`)

E' la classe centrale. Eredita da un insieme di **mixin** (uno per
tema: rendering, pathfinding, popup, esecuzione task, ecc.) che
contengono solo metodi; lo stato `self.*` e' tutto inizializzato qui in
`__init__`. In `app.py` stanno solo `__init__`, `aggiorna_frame` e
`run`; il resto dei metodi e' nei mixin di `ui/mixins/`.

### `TaskActionEditor` (`ui/editor.py`)

Finestra secondaria per registrare le azioni di una task (click, drag,
zone YOLO, sequenze). Anch'essa eredita da una serie di mixin
(`editor_mixins/`); in `editor.py` stanno solo `__init__`, `apri`,
`chiudi` e `aggiorna_frame`.

### `TaskManager` (`managers/task_manager.py`)

E' una **facade** che delega a due sub-manager:

- `TaskDettagliManager` — CRUD della struttura task (id, nome,
  posizione, fasi, alternativi, padre).
- `TaskEsecuzioneManager` — CRUD delle azioni e dello stato di
  esecuzione di ciascuna task.

I mixin chiamano l'API pubblica del `TaskManager` senza sapere che
dietro ci sono due manager.

## Pattern dei mixin

Ogni mixin segue lo stesso schema: in cima `from ._imports import *`
(che porta `dpg`, `time`, `math`, `GPSConfig`, `Colors`, i manager,
ecc., evitando di ripetere gli import in ogni file) e una classe
`<Nome>Mixin` che contiene solo metodi `self.*`.

```python
# among_us_ai/ui/mixins/zones.py

"""Gestione delle zone nominate e delle zone porta (UI)."""

from ._imports import *


class ZonesMixin:
    def _start_new_zone_mode(self):
        self.zone_drawing_mode = True
        # ...
```

## Come aggiungere una funzionalita'

### Un nuovo bottone nel pannello

1. Apri `among_us_ai/ui/mixins/ui_setup.py`.
2. Trova la scheda giusta (`with dpg.tab(label="...")`).
3. Aggiungi `dpg.add_button(label="...", callback=lambda *a: self._mio_callback())`.
4. Crea `_mio_callback` in un mixin adatto (se non sai dove, `misc.py`).

### Un nuovo tipo di azione per le task

1. Aggiungi `_avvia_<nuova_azione>` in `editor_mixins/start_actions.py`
   che imposta lo stato della macchina.
2. Aggiungi la costante di stato in `editor.py`.
3. Gestisci il click in `editor_mixins/canvas_input.py`.
4. Aggiungi il rendering in `editor_mixins/drawing.py::_disegna_azione`.
5. Aggiungi l'esecuzione in **due** posti: `execution/runtime.py`
   (per il pulsante Test) e nel package `execution/_motore_pkg/` (per i
   file generati): nuovo handler nel modulo della famiglia giusta,
   registrato nella dispatch map.

### Un nuovo manager

Crea `managers/<nome>_manager.py` sul modello di `PoiManager`,
esportalo da `managers/__init__.py` e instanzialo in
`GPSVisualizerPro.__init__`.

### Un nuovo gruppo di metodi UI

Crea `among_us_ai/ui/mixins/<nome>.py` con `from ._imports import *` e
una classe `<Nome>Mixin`, poi aggiungilo alle basi di
`GPSVisualizerPro` in `app.py`.

## Formato delle task

Le task sono divise in due file:

- `tasks_dettagli.json` — struttura "leggera" (id, nome, posizione,
  tipo, stanza, padre, fasi, alternativi), cambia raramente.
- `tasks_esecuzione/task_<id>.json` — azioni "pesanti" (poligoni, zone
  YOLO, ...) e stato di esecuzione, cambiano spesso quando si edita una
  task.

## Migrazione automatica al primo avvio

`TaskManager` controlla all'avvio: se `tasks_dettagli.json` non esiste
ma esiste un `task_registrate.json` (vecchio formato monolitico), lo
splitta in struttura + azioni e rinomina il vecchio file in
`task_registrate.json.bak`. Accetta sia il formato `v2.0` sia il `v2.1`.

## Generazione del file `.py` di una task

`TaskManager.crea_file_esecuzione(id_task)` risolve l'eventuale
ereditarieta' delle azioni (padre → figlia), poi `task_writer.py`
produce un thin wrapper con tre blocchi: header (commento + marker di
versione + parsing CLI), dati (`TASK_META` + `AZIONI`) e chiamata al
motore (`import _motore` + `_motore.esegui_lifecycle(...)`). Il writer
copia anche `_motore_pkg/` in `tasks_exec/_motore/`. Il file risultante
dipende solo dal package `_motore/` accanto a se' ed e' eseguibile con
`python tasks_exec/task_001_xxx.py --step 0`.

## Stop globale

Lo stato di stop e' un singleton in `core/stop_flag.py` con un solo
attributo booleano `requested`, gestito tramite gli helper
`request_stop()` / `is_stop_requested()`. I thread e i loop di
esecuzione lo controllano periodicamente; il subprocess riceve anche un
messaggio `STOP` sullo stdin.

```python
# nei mixin / runtime:
if stop_flag.is_stop_requested():
    return  # o break
```

Il tasto **FINE (END)** forza lo stop immediato di tutto; **F4** ferma
la modalita' Auto-All (e con essa l'eventuale task in corso).

## Convenzioni di codice

- **Italiano** nella business logic: campi JSON (`id_stanza`,
  `id_padre`, `alternativi`, `nome_zona`, ...) e nomi di metodi
  (`aggiungi`, `imposta_padre`, `naviga_a_zona`).
- **Inglese tecnico** dove e' gergo del dominio: tipi di azione
  (`click_poly`, `drag_zone`, `yolo_drag_all`), campi delle azioni
  (`poly`, `rect`, `rx`, `ry`, `keypad`, `lights`), `subprocess`.
- I tag DPG sono stabili e in snake_case (`zone_listbox`,
  `mem_task_listbox`, ...): cambiarli rompe i `dpg.set_value()` sparsi
  nei mixin.
- Le costanti `OFFSET_*` sono gli offset RAM del gioco, in maiuscolo
  per distinguerle dai nomi di campo dei dati.

## Fonti

- DearPyGui: https://dearpygui.readthedocs.io/
- pymem: https://github.com/srounet/Pymem
- Ultralytics YOLO: https://docs.ultralytics.com/

## Licenza

MIT. Vedi il file [LICENSE](LICENSE).
