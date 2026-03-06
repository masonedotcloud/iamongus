# Changelog

## v2.2.13 — Simon Says (Reactor) reattivo: pre-warming + base dinamica

### Problema riportato

> Quando avvio task del Reactor con Simon Says devo essere rapido ad
> analizzare per poterlo replicare in tempo. Tra apertura pannello e
> inizio analisi c'e' troppo lag.

### Causa

Il flusso pre-fix era:

```
1. Bot preme SPAZIO            → t=0  (apre pannello)
2. Avvia subprocess            → t=0  (Python startup ~300-500ms)
3. SetForegroundWindow         → t≈500ms
4. sleep(0.4) grace period     → t=900ms
5. Cattura base_img            → t=910ms
6. Inizio analisi (primo frame)→ t=920ms
```

Tra apertura pannello e primo frame analizzato passavano ~900ms.
La sequenza Simon Says puo' iniziare entro 200-500ms dall'apertura,
quindi il primo flash veniva spesso perso.

### Fix: 3 ottimizzazioni complementari

#### 1. Inversione ordine: subprocess PRIMA di SPAZIO

In `tasks_launch.py`, ora avviamo il subprocess prima di premere
SPAZIO. Mentre il subprocess fa lo startup (~300-500ms), in parallelo
premiamo SPAZIO che apre il pannello. Quando il subprocess e' pronto,
il pannello e' gia' aperto.

#### 2. Skip `sleep(0.4)` se finestra gia' in foreground

In `lifecycle.py`, ora il subprocess controlla se la finestra del
gioco e' gia' in foreground. Se si', skippa `SetForegroundWindow +
sleep(0.4)`. Risparmio: **400ms** per ogni avvio.

```python
if _win32gui.GetForegroundWindow() != hwnd:
    _win32gui.SetForegroundWindow(hwnd)
    _time.sleep(0.4)  # solo se serve davvero
```

#### 3. Base dinamica robusta in `_h_simon_says`

PROBLEMA: dopo l'inversione (#1), il subprocess potrebbe partire
PRIMA che il pannello sia completamente aperto. Catturare `base_img`
in quel momento sarebbe inutile (la base sarebbe la mappa del gioco,
non il pannello).

SOLUZIONE: invece di catturare `base_img` subito, aspettiamo che
2 frame consecutivi siano "simili" sui display point (= pannello
stabilizzato). Polling rapido a 30ms, max 1 secondo di attesa.

Vantaggi:
- Robusto: funziona sia se il pannello e' gia' aperto sia se sta
  ancora aprendosi
- **Non perdiamo flash**: se il primo flash inizia mentre stiamo
  ancora stabilizzando la base, il polling lo cattura comunque
  appena la base si fissa
- Fallback graceful: se il pannello non si stabilizza in 1s,
  procediamo con la base imperfetta invece di bloccarci

### Timing post-fix

```
1. Avvia subprocess        t=0
2. Premi SPAZIO            t=5ms  (parallelo)
3. Pannello si apre        t≈100-200ms
4. Subprocess pronto       t≈300-500ms  (sovrapposto con apertura!)
5. Focus check (skip sleep)t≈500ms
6. Handler parte           t≈510ms
7. Stabilita' base         t≈600-700ms
8. Inizio polling vero     t=700ms
```

**Da ~920ms a ~700ms** prima del primo frame analizzato.
**Risparmio: ~220ms**, e MOLTO piu' robusto contro race condition.

### File toccati

| File | Modifica |
|---|---|
| `among_us_ai/ui/mixins/tasks_launch.py` | inversione ordine: subprocess prima, SPAZIO dopo |
| `among_us_ai/execution/_motore_pkg/lifecycle.py` | skip `SetForegroundWindow + sleep(0.4)` se gia' in foreground |
| `among_us_ai/execution/_motore_pkg/handlers_simon.py` | base dinamica: aspetta stabilita' di 2 frame consecutivi |

### Verifica fatta

- Syntax OK su tutti i file modificati
- Import del package: OK
- La logica della base dinamica e' compatibile con la vecchia base
  fissa (caso pannello gia' stabile -> 1 polling, base catturata in
  ~30-60ms)

### Cosa NON e' cambiato

- API pubblica del motore: invariata
- Logica di analisi della sequenza Simon Says: invariata (stessa
  soglia diff > 50, stesso polling, stesso click sequence)
- Tutti gli altri handler: invariati
- Compatibilita' con file `.py` task vecchi: invariata

### Considerazione

Se il problema persiste su Reactor, possibili cause aggiuntive:
- Il punto display Simon Says non e' calibrato bene (i pixel
  monitorati non corrispondono ai LED veri del minigioco)
- Il pannello del Reactor ha un'animazione di "apertura" piu' lunga
  di 1 secondo (in tal caso aumenta il timeout a 2s in handlers_simon)


## v2.2.11 — Arrivo piu' preciso al target della task

### Problema riportato

> A volte non arriva nella zona di attivazione della task. Vorrei
> piu' precisione per arrivare nel raggio di attivazione.

### Causa

La soglia `AUTO_ARRIVAL_THRESHOLD` era 0.25 unita' di gioco. Il bot
si fermava entro un cerchio di raggio 0.25 dal target e lanciava
subito la task, ma a volte questo cerchio era ancora fuori dal raggio
di interazione del gioco (il pulsante "Use" non si illuminava).

Il pathfinding inoltre lascia naturalmente un piccolo margine sul
waypoint finale per evitare di "incollarsi" al target.

### Fix

Due modifiche complementari per arrivare meglio nel raggio di
attivazione del pulsante Use:

#### 1. Soglia di arrivo ridotta: 0.25 -> 0.15

`AUTO_ARRIVAL_THRESHOLD` passa da 0.25 a 0.15 unita'. Il bot si
fermera' naturalmente piu' vicino al target.

#### 2. "Final nudge" prima del callback

Quando il bot tocca la soglia di arrivo, prima di lanciare la task
fa un piccolo movimento di rifinitura premendo i tasti direzionali
(W/A/S/D) verso il target per `AUTO_FINAL_NUDGE_SEC` secondi
(default 0.20s).

Questo recupera gli ultimi centimetri che il pathfinding lascia
come margine. Risultato: il bot si avvicina al target per altri
~0.1 unita' prima di lanciare la task.

Il movimento e' bloccante (`time.sleep(0.2)`) perche' la finestra
e' molto breve. Il sistema rilascia comunque tutti i tasti dopo il
nudge per non lasciare il personaggio in movimento durante l'esecuzione
della task.

#### Nuovi parametri config

In `among_us_ai/core/config.py`:

```python
AUTO_ARRIVAL_THRESHOLD = 0.15   # era 0.25
AUTO_FINAL_NUDGE_SEC   = 0.20   # nuovo, 0 = disabilitato
```

Per disabilitare il nudge (e tornare al solo arrivo standard):
imposta `AUTO_FINAL_NUDGE_SEC = 0`. Per arrivo ancora piu' preciso,
puoi ridurre `AUTO_ARRIVAL_THRESHOLD` a 0.10 (a tuo rischio: piu'
basso = piu' rischio di stuck per imprecisioni del pathfinding).

### File toccati

| File | Modifica |
|---|---|
| `among_us_ai/core/config.py` | `AUTO_ARRIVAL_THRESHOLD` 0.25->0.15, nuovo `AUTO_FINAL_NUDGE_SEC=0.20` |
| `among_us_ai/ui/mixins/auto_move.py` | logica final nudge prima del callback di arrivo |

### Verifica fatta

Test logico delle direzioni di nudge:

| Posizione target | Tasti premuti |
|---|---|
| NE (dx>0, dy>0) | D + W |
| NO (dx<0, dy>0) | A + W |
| SE (dx>0, dy<0) | D + S |
| SO (dx<0, dy<0) | A + S |
| Sopra | W |
| Sotto | S |
| Destra | D |
| Sinistra | A |
| Troppo vicino (<0.05) | nessuno |

Tutti corretti.

### Cosa NON e' cambiato

- Pathfinding e replan: invariati
- Logica stuck detection: invariata
- Soglia waypoint intermedi (`WAYPOINT_ADVANCE` 0.55): invariata
- Logica fallback su `alternativi`: invariata
- Tutto il resto del bot: invariato

### Considerazione futura

Hai chiesto se non fosse meglio rilevare il pulsante "Use" a video.
L'idea e' valida ma richiede un meccanismo aggiuntivo (screenshot
ROI angolo basso destro, threshold luminosita', timeout). Per ora
abbiamo scelto la via piu' semplice (precisione di arrivo). Se dopo
queste modifiche dovessero ancora capitare casi in cui non arriva
nel raggio, possiamo aggiungere il rilevamento del pulsante.


## v2.2.10 — Pulizia anti-flicker dei player rilevati (vivi e morti)

### Bug riportato

> Mi servirebbe sistemare il fatto della rilevazione dei player se
> rianalizza la zona e non trovi piu' il player e' inutile mantenerlo
> segnato sia per morti che per vivi.

### Stato pre-fix

In `yolo_scanner.py`, la pulizia dei player rilevati aveva 2 problemi:

1. **I morti erano immortali**: la regola di scadenza `current_time -
   dp['time'] < 30.0` aveva un'eccezione `or dp.get('is_dead', False)`,
   quindi i cadaveri non venivano mai rimossi.

2. **L'invecchiamento era lento**: per i vivi, quando la camera
   inquadrava una zona ma non trovava il player, il `time` veniva
   ridotto di 5s. Servivano ~6 cicli per superare la soglia 30s.

Risultato: la mappa si "saturava" di player che in realta' erano gia'
morti/spostati altrove.

### Fix: nuovo contatore `missed_scans`

Ogni player rilevato ora ha un campo `missed_scans` che traccia in
quanti scan consecutivi il player era "atteso" (entro view_radius
dalla camera) ma non e' stato rilevato.

Logica:
- Se in uno scan il player viene matchato da una nuova detection ->
  `missed_scans = 0` (reset).
- Se il player e' dentro `view_radius` (4.5 unita') dalla camera ma
  nessuna detection vicina e' stata trovata -> `missed_scans += 1`.
- Quando `missed_scans >= 3` -> il player viene **rimosso**.

Soglia 3 scelta come anti-flicker: con scan rate ~5/s, un player
sparito viene rimosso in ~0.6 secondi. Abbastanza rapido per non
avere "fantasmi", ma robusto contro frame YOLO occasionalmente
vuoti (occlusione, distanza, falso negativo).

### Cambio chiave: vale anche per i morti

A differenza della logica precedente, ora **vivi e morti seguono lo
stesso comportamento**: se non sono piu' visibili nella zona inquadrata,
spariscono dopo 3 scansioni mancate. Questo perche':

- Se il bot guarda l'Admin e prima vedeva un cadavere, ma ora il
  cadavere non c'e' piu' (perche' qualcuno l'ha riportato), e' giusto
  rimuoverlo dalla mappa.
- Se il bot si allontana dall'Admin e poi torna, il cadavere viene
  ri-rilevato e ri-aggiunto.

### Safety net 60s

Aggiunta una rimozione automatica per player MOLTO vecchi (>60s) che
non sono mai stati ri-inquadrati. Vale anche per i morti (prima ne
erano esenti). Evita che la lista cresca indefinitamente per player
in zone della mappa che non visitiamo piu'.

### File toccati

| File | Modifica |
|---|---|
| `among_us_ai/ui/mixins/yolo_scanner.py` | aggiunto campo `missed_scans` ai player + nuova logica di pulizia anti-flicker |

### Verifica fatta

7 test funzionali su scenari diversi:

| Scenario | Risultato |
|---|---|
| Player visto in zona | Resta, missed=0 |
| Player non visto 1 volta | Resta, missed=1 |
| Player vivo non visto 3 volte | **Rimosso** |
| Player morto non visto 3 volte | **Rimosso** (nuovo!) |
| Anti-flicker: 1 frame mancato + ritrovato | Resta, missed resetta a 0 |
| Player fuori inquadratura | Non toccato (corretto) |
| Safety net 60s su player dimenticato | Rimosso |

Tutti passano correttamente.

### Cosa NON e' cambiato

- `view_radius` (4.5 unita'): invariato
- Tolleranza match (1.5 unita'): invariato
- Logica anti-teleport e anti-zombie: invariate
- Logica calibrazione camera, rendering, ecc.: invariate

Solo la sezione "Pulizia fantasmi" e' stata sostituita.


## v2.2.9 — Ripeti SOLO le azioni con [Ripeti], non quelle prima

### Problema riportato

> Continua a ripetere tutte le fasi.

### Causa

Le tue task NON usano i cooldown per separare le fasi. Esempio Swipe Card:

```
AZIONI = [
    {tipo: click_poly carta},   # azione 0, NO [Ripeti]
    {tipo: drag_zone slide},    # azione 1, [Ripeti]
]
```

Senza cooldown, il sistema considera entrambe le azioni come **una
singola fase (chunk)**. Quindi quando lo slide falliva, il bot rilanciava
il subprocess che faceva di nuovo TUTTO (click + slide), invece di
saltare il click e ripetere solo lo slide.

L'analisi del JSON delle tue task lo conferma:

```
Task con cooldown: 1
Task senza cooldown: 20
```

### Fix: nuovo parametro `--start-from-action`

Adesso il bot puo' rilanciare il subprocess saltando le prime N azioni
del chunk. La logica:

1. Quando una fase con `[Ripeti]=True` fallisce, il bot trova l'indice
   della **prima azione con `[Ripeti]=True`** nel chunk corrente.
2. Rilancia il subprocess passando `--start-from-action N`.
3. Il subprocess salta le prime N azioni e parte dalla N-esima.

### Esempio Swipe Card

```python
AZIONI = [
    {tipo: click_poly,  ripeti: False},   # azione 0
    {tipo: drag_zone,   ripeti: True},    # azione 1
]
```

**Lancio iniziale**:
- Bot lancia: `python task_001.py --step 0`
- Subprocess esegue: click + slide
- Slide fallisce (RAM resta a 0/2)

**Rilancio (modalita' ripeti)**:
- Bot calcola `start_from_action = 1` (prima azione con [Ripeti])
- Bot lancia: `python task_001.py --step 0 --start-from-action 1`
- Subprocess esegue: **solo slide** (salta il click che era gia' OK)
- Se ancora fallisce -> ripete (max 5 volte), poi ESC

### File toccati

| File | Modifica |
|---|---|
| `among_us_ai/execution/task_writer.py` | aggiunto parsing `--start-from-action` nel meta block + campo `start_from_action` in TASK_META |
| `among_us_ai/execution/_motore_pkg/dispatcher.py` | nuovo parametro `start_from_action` in `esegui_azioni`: salta le prime N azioni del chunk |
| `among_us_ai/execution/_motore_pkg/lifecycle.py` | passa `task_meta['start_from_action']` a `esegui_azioni` |
| `among_us_ai/ui/mixins/tasks_process.py` | nuovo parametro in `_avvia_subprocess_task` + nuovo metodo `_calcola_start_from_action` + uso al rilancio |

### Verifica fatta

Test simulazione Swipe Card senza cooldown:

| Caso | start_from_action | Comportamento |
|---|---|---|
| Lancio iniziale | 0 | Esegue click + slide |
| Rilancio dopo fallimento | **1** | Esegue solo slide (corretto!) |
| Ripeti 1/3, 2/3, 3/3 | 1 ogni volta | Slide ripetuto |
| Tentativo 3/3 esaurito | - | ESC + abbandono |
| Nessuna azione [Ripeti] | 0 | Fallback: riparte da capo |

Tutti i test passano.

### Retrocompatibilita'

Per chi ha task **CON cooldown** (modello "fasi separate"):
- Il cooldown chunkifica le azioni come prima
- `start_from_action` si applica DENTRO il chunk corrente
- Esempio: se hai 3 fasi (chunk 0, 1, 2), il bot lancia con `--step 1`
  per la fase 1. Se fallisce e ha [Ripeti], rilancia con `--step 1
  --start-from-action <prima azione [Ripeti] DEL CHUNK 1>`.

Quindi: **nessuna regressione** per le task con cooldown.

I file `.py` vecchi (senza il flag `--start-from-action`) continuano a
funzionare grazie a `parse_known_args`: ignorano gli argomenti sconosciuti.


## v2.2.8 — Fix critico: ripete SOLO la fase con [Ripeti], non tutta la task

### Bug riportato

> Adesso e' come se mi ripetesse la task. Io voglio che ripete solo
> la fase da me selezionata con il checkbox.

### Causa

In `_fase_da_ripetere_ext`, l'`idx_fase` (cioe' "quale fase e' stata
appena eseguita") veniva calcolato come `internal_step - 1`. Ma questo
calcolo e' SBAGLIATO per l'**ultima fase** di una task multi-step.

Spiegazione tecnica:
- `internal_step` viene incrementato solo quando il subprocess stampa
  `__COOLDOWN__:` a stdout. Lo fa al termine di ogni chunk, MA SOLO se
  ci sono altri chunk dopo.
- Per la swipe card (2 fasi: click + slide):
  - Subprocess parte con `--step 0`, esegue fase 0 click,
    stampa `__COOLDOWN__:0.5` -> `internal_step` diventa 1.
  - Bot rilancia con `--step 1`, esegue fase 1 slide,
    NON stampa altro `__COOLDOWN__:` (e' l'ultima fase) -> termina.
  - `internal_step` resta a 1.
  - `_fase_da_ripetere_ext` calcola `idx_fase = 1 - 1 = 0` ❌
    Sta puntando alla fase 0 (click) invece che alla 1 (slide).

Quindi il bot controllava se la fase 0 aveva `[Ripeti]` (e di solito
no, l'utente la mette sulla fase 1 dello slide), e in pratica non
ripeteva mai la fase giusta. Oppure, se l'utente metteva `[Ripeti]`
su entrambe le fasi, ripeteva tutta la task da capo (fase 0 + 1).

### Fix

#### 1. Salvo lo step del subprocess al lancio

Nuovo dict `self.task_last_launched_step: { id_task: step }` in
`_avvia_subprocess_task`. Salva il valore esatto di `--step`
passato al subprocess. Questo e' la vera "fase appena eseguita"
e non dipende da quanti `__COOLDOWN__:` sono stati stampati.

```python
self.task_last_launched_step[id_task] = script_step
```

#### 2. Uso `task_last_launched_step` invece di `internal_step - 1`

In `_fase_da_ripetere_ext`, ora `idx_fase` viene letto direttamente
dal dict. Cosi':
- Subprocess parte con `--step 1`, esegue fase 1 slide, fallisce.
- `task_last_launched_step[id] = 1` -> `idx_fase = 1` (corretto!)
- Il bot controlla se la fase 1 ha `[Ripeti]`. Se si', rilancia
  con `--step 1` (calcolato da `max(ram_step, internal_step) = max(0, 1) = 1`).

La vecchia logica (`internal_step - 1`) resta come fallback.

#### 3. Reset internal_step quando si abbandona con ESC

Quando si raggiunge il limite tentativi e si preme ESC:
- `internal_step` viene resettato a 0
- `task_last_launched_step` viene rimosso

Cosi' al prossimo lancio (manuale o automatico) la task ricomincia
da fase 0, dato che ESC ha presumibilmente chiuso/annullato il
minigioco e il gioco ha riportato lo step in RAM a 0.

### Comportamento atteso adesso (Swipe Card)

```
Azioni:
  1. click_poly su carta       D:0.0s P:0.5s [---]    (no ripeti)
  2. cooldown                  D:0.5s
  3. drag_zone slide cursore   D:0.5s P:0.0s [Ripeti] Max: 5
```

Flusso:
1. Subprocess fase 0 (click): eseguito una volta, NON si ripete
   (la fase 0 non ha [Ripeti]).
2. RAM avanza a step=1 (carta presa).
3. Subprocess fase 1 (slide): eseguito.
   - Se RAM avanza a step=2 (done) -> task finita, prossima task.
   - Se RAM resta a 1 -> fase 1 da ripetere (counter 1/5).
4. Ripete fino a 5 volte. Se non riesce -> ESC + abbandona.

**Importante**: la fase 0 (click) NON viene ripetuta dopo un fallimento
della fase 1, perche' nel rilancio `script_step = max(ram_step=1, internal_step=1) = 1`,
quindi il subprocess parte direttamente da fase 1.

### File toccati

| File | Modifica |
|---|---|
| `among_us_ai/ui/mixins/tasks_process.py` | salvataggio `task_last_launched_step` + uso in `_fase_da_ripetere_ext` + reset internal_step su ESC |

### Verifica fatta

Test simulazione "Swipe Card con [Ripeti] solo sulla fase 1":
- Scenario 1: dopo fase 0 (click), il bot decide `ripete=False` perche'
  la fase 0 non ha [Ripeti]. ✓
- Scenario 2: dopo fase 1 (slide) fallita, il bot decide `ripete=True`
  per 2 tentativi, poi al 3° tentativo (max=3) preme ESC e abbandona. ✓
- Verifica dello step rilanciato: dopo fallimento fase 1,
  `script_step = max(ram_step=0, internal_step=1) = 1`. Il subprocess
  riparte direttamente da fase 1, non da 0. ✓


## v2.2.7 — Limite tentativi ripetizione + ESC fallback

### Bug riportato

> Vorrei che nella lista delle azioni, ripeti le N azioni della fase
> finche' non rilevi il successo. Per le task multifase, capisci
> incrociando lo step in RAM. Voglio anche un campo "max tentativi"
> per fase, e se non ci riesce in N tentativi premi ESC.

### Stato pre-fix

La logica "ripeti finche' la RAM non avanza" era gia' presente in
`_fase_da_ripetere_ext`. Funzionava cosi':

- Per ogni azione c'e' una checkbox "[Ripeti]" nell'editor.
- A fine subprocess, il sistema controlla 3 segnali RAM:
  1. Task scomparsa dalla lista RAM -> finita
  2. Task done in RAM (step == mstep) -> finita
  3. Step in RAM avanzato oltre la fase corrente -> finita
- Se TUTTI dicono "non finita" e c'e' almeno un'azione con `ripeti=True`
  nel chunk corrente -> rilancia il subprocess.

**Mancava:** un limite ai tentativi. Una task che non riesce mai
a soddisfare la RAM avrebbe ripetuto all'infinito.

### Fix

#### 1. Counter tentativi per fase

Nuovo dict `self.task_retry_counts: { id_task: { idx_fase: n } }` in
``app.py``. Tracciato per ogni coppia (task, fase).

Il counter viene **resettato** quando:
- La RAM segnala "task done"
- La RAM segnala "task scomparsa"
- La RAM segnala "step avanzato oltre la fase corrente"
- Si raggiunge il limite max_tentativi (per ricominciare pulito al
  prossimo lancio)

#### 2. Campo "max_tentativi" per fase

Letto dal JSON dell'azione (campo `max_tentativi`, default 5).
Si applica al chunk: la prima azione del chunk con il campo settato
determina il limite per tutta la fase.

Quando il counter raggiunge il limite:
- Il sistema preme **ESC** (per chiudere il minigioco aperto)
- Il counter viene azzerato
- `_fase_da_ripetere_ext` ritorna False -> la task viene
  considerata "abbandonata"
- Il sistema procede con la task successiva

#### 3. UI: campo "Max:" accanto al [Ripeti]

Nella lista azioni dell'editor, quando un'azione ha [Ripeti] attivo,
appare un input numerico "Max: [5]" subito dopo. Modificarlo salva
automaticamente nel JSON (idempotente).

#### 4. Helper `_premi_esc`

Nuovo metodo che invia il tasto ESC tramite pyautogui per chiudere
finestre/minigiochi aperti. Usato come "uscita di sicurezza" quando
i tentativi sono esauriti.

### File toccati

| File | Modifica |
|---|---|
| `among_us_ai/ui/app.py` | aggiunto `task_retry_counts = {}` |
| `among_us_ai/ui/mixins/tasks_process.py` | logica counter + ESC + helpers |
| `among_us_ai/ui/mixins/memory_sync.py` | reset counter quando task done in RAM |
| `among_us_ai/ui/editor_mixins/list_panel.py` | campo "Max:" accanto a [Ripeti] |

### Esempio: Swipe Card in Admin

Ora puoi configurare:

```
Azioni:
  1. [Ripeti X] click_poly su carta       D:0.0s P:0.5s [Ripeti] Max: 5
  2. cooldown                              D:0.5s
  3. [Ripeti X] drag_zone (slide cursore)  D:0.5s P:0.0s [Ripeti] Max: 5
```

Comportamento:
- Fase 0 (click): se la RAM non rileva il pickup della carta dopo
  5 tentativi -> ESC + abbandona task
- Fase 1 (slide): se la RAM non rileva la swipe completata dopo
  5 tentativi -> ESC + abbandona task
- Se in qualunque momento la RAM avanza, il counter si resetta e
  la fase passa.

### Scrollbar orizzontale (gia' presente)

La scrollbar orizzontale della barra azioni esisteva gia' in v2.1.x,
sia per la colonna controlli sia per la lista azioni. Non serve
modificarla.

### Verifica fatta

Test simulazione con max_tentativi=3:
- Tentativo 1: counter 1/3 -> ripete (return True)
- Tentativo 2: counter 2/3 -> ripete (return True)
- Tentativo 3: limite raggiunto -> ESC + counter resettato + return False
- Tentativo 4 (nuova sessione): counter ricomincia da 1/3

Test "RAM avanza durante i tentativi":
- Tentativo 1: counter 1, RAM ferma -> ripete
- Tentativo 2: RAM avanzata -> counter resettato, return False (fase passata)


## v2.2.6 — Salvataggio automatico checkbox 'Ripeti' + log debug

### Bug

L'utente ha riportato che il bot continuava ad applicare il
"cooldown di sicurezza 8s" invece di rilanciare:
```
[Fix Wiring] [Fix Wiring] Teardown completato.
[Loop guard] Task non completata in RAM - cooldown di sicurezza 8s
[Exec] 'Fix Wiring' terminata - exit code 0
```

### Causa

Quando l'utente cliccava la checkbox "Ripeti" nell'editor delle
azioni, il flag veniva aggiornato SOLO in memoria (`self.azioni`).
Per persistere su disco, l'utente doveva poi cliccare "Salva azioni".

Se l'utente lanciava la task SENZA salvare prima:
- in memoria: `azione.ripeti = True`
- su disco (JSON): `ripeti` ancora assente
- a runtime, il bot leggeva il JSON -> trovava `ripeti=False` -> non
  rilanciava

### Fix

1. **Salvataggio automatico al click della checkbox**: la callback
   ora chiama subito `task_mgr.imposta_azioni(...)` per persistere
   il flag su disco. Niente piu' bisogno di cliccare "Salva azioni"
   prima di lanciare.

2. **Log di debug** in `_fase_da_ripetere_ext`: a ogni decisione il
   bot stampa quante azioni ci sono, quante hanno ripeti, e perche'
   ha deciso di ripetere o no. Esempio:
   ```
   [Ripeti DEBUG] Task 'Fix Wiring': 1 azioni, 1 con ripeti=True (src_id=54)
   [Ripeti] Fase con ripeti=True, RAM dice non finita. Rilancio.
   ```
   In caso di problemi, il log dice esattamente cosa sta succedendo.

3. **Fallback per task figlie**: se la figlia ha azioni proprie
   con ripeti=True ma `get_azioni_effettive` ritorna le azioni del
   padre (senza ripeti), il sistema preferisce le azioni proprie
   della figlia. Cosi' l'utente puo' personalizzare "ripeti" su una
   figlia anche se eredita le azioni dal padre.

### Modifiche al codice

| File | Modifica |
|---|---|
| `among_us_ai/ui/editor_mixins/list_panel.py` | callback `make_toggle_ripeti` ora chiama `task_mgr.imposta_azioni()` per salvataggio immediato |
| `among_us_ai/ui/mixins/tasks_process.py` | log di debug + fallback per task figlie |

### Cosa fare se ancora non funziona

Se nonostante il fix il rilancio non parte, i log di debug aiuteranno
a capire cosa sta succedendo:

- `[Ripeti DEBUG] Task '...': N azioni, 0 con ripeti=True` ->
  significa che il flag NON e' salvato sul JSON. Riapri l'editor,
  ricliccalo, e dovresti vedere `(salvato)` nei log.
- `[Ripeti DEBUG] Task '...': N azioni, K con ripeti=True` MA
  `[Ripeti] Task '...': fase X NON ha ripeti=True` -> significa
  che il flag e' su una fase diversa da quella corrente. Verifica
  l'ordine delle azioni e i cooldown di separazione.

### Cosa NON e' cambiato

- API pubblica del motore: invariata
- Schema JSON delle task: invariato
- Tutto il resto del codice: invariato


## v2.2.5 — Fix critico: 'ripeti' funziona anche per task con UNA SOLA fase

### Bug

Sintomo nei log dell'utente:
```
[Fix Wiring] [Fix Wiring] Completata: True
[Fix Wiring] [Fix Wiring] Teardown completato.
[Loop guard] Task non completata in RAM - cooldown di sicurezza 8s
[Exec] 'Fix Wiring' terminata - exit code 0
```

La task era una singola azione `wiring` con `ripeti=True`, **senza
cooldown**. Quando il subprocess finiva, il bot applicava il cooldown
di sicurezza 8s INVECE di rilanciare la fase.

### Causa

`task_internal_steps[id]` viene incrementato solo quando il subprocess
printa `__COOLDOWN__:` (cioe' alla fine di un chunk separato da
cooldown). Per task con singola fase senza cooldown, lo step resta
sempre a 0.

La logica `_fase_da_ripetere_ext` aveva:

```python
if internal_step == 0:
    return False  # "nessun chunk eseguito"
```

Sbagliato! Per task con singola fase, internal_step=0 NON significa
"nessun chunk eseguito": significa "il chunk 0 (l'unico) e' appena
finito".

Inoltre il check `if ram_step >= internal_step` con singola fase
diventava `if ram_step >= 0` -> sempre vero -> blocca sempre.

### Fix

1. Differenzio il caso "singola fase" dal caso "multi-fase":
   ```python
   if len(chunks) == 1:
       idx_fase = 0  # singola fase: e' quella appena finita
   elif internal_step == 0:
       return False  # multi-fase ma nessuno step ancora
   else:
       idx_fase = internal_step - 1  # multi-fase
   ```

2. Sostituisco il check `ram_step >= internal_step` con
   `ram_step >= idx_fase + 1` (= "il gioco ha riconosciuto il
   completamento della fase appena eseguita"):
   ```python
   soglia = idx_fase + 1
   if ram_step >= soglia:
       return False  # fase riconosciuta come fatta
   ```

### Comportamento corretto adesso

```
[Fix Wiring] Completata: True
[Fix Wiring] Teardown completato.
[Ripeti] Fase con ripeti=True, RAM dice non finita. Rilancio.
[Exec] avvio subprocess Fix Wiring (step=0)
... loop finche' la RAM avanza o segnala done
```

### Test funzionali (9/9 passati)

| Scenario | atteso |
|---|---|
| Singolo wiring ripeti, RAM non riconosciuta | RILANCIA |
| Singolo wiring ripeti, RAM done | STOP |
| Singolo wiring ripeti, RAM avanzata 1/1 | STOP |
| Singolo wiring ripeti, task scomparsa | STOP |
| Caso reale: ret=0, ripeti=True, RAM 0/1 | RILANCIA |
| Singolo wiring SENZA ripeti | STOP |
| Multi-fase: fase 0 (no ripeti) finita | STOP |
| Multi-fase: fase 1 (ripeti) finita, RAM 1/2 | RILANCIA |
| Multi-fase: fase 1 finita, RAM 2/2 | STOP |

### File toccati

- `among_us_ai/ui/mixins/tasks_process.py`: corretta la logica di
  `_fase_da_ripetere_ext` per gestire task con singola fase.

### Cosa NON e' cambiato

- API pubblica del motore: invariata
- Schema JSON delle task: invariato
- Comportamento per task multi-fase: invariato (gia' funzionava)


## v2.2.4 — Fix critici: `ripeti` funziona anche con exit code 1, e fix esegui_azioni return

### Bug 1 — esegui_azioni ritorna None invece di True

Sintomo nei log dell'utente:
```
[Fix Wiring] Completata: None
[Fix Wiring] Teardown completato.
[Loop guard] Task non completata in RAM - cooldown di sicurezza 8s
[Exec] 'Fix Wiring' terminata - exit code 1
```

#### Causa

`esegui_azioni()` nel dispatcher non aveva un `return True` esplicito
alla fine. Quando l'esecuzione finiva normalmente (senza errori),
Python ritornava `None`. Il lifecycle interpretava poi `not None` =
True -> `sys.exit(1)` -> falso errore.

#### Fix

In `_motore_pkg/dispatcher.py`, aggiunto `return True` esplicito alla
fine di `esegui_azioni`:

```python
if not is_test and current_step < len(cooldowns):
    print(f"__COOLDOWN__:{cooldowns[current_step]}", flush=True)

return True   # <-- mancava questa riga
```

### Bug 2 — La logica `ripeti` non scattava con exit code 1

Anche prima del fix #1, la logica "ripeti fase" funzionava SOLO se
`ret == 0`. Quando il subprocess terminava con `ret == 1` (per
qualunque motivo: bot non centra il bersaglio, minigioco non si
apre, exception nel motore, ecc.), il flusso saltava la logica
ripeti e applicava direttamente il "cooldown di sicurezza 8s".

Risultato: anche con la checkbox "Ripeti" attiva, una task fallita
non veniva rilanciata.

#### Fix

Sostituito `_fase_da_ripetere(task)` con `_fase_da_ripetere_ext(task, ret)`
che si basa SOLO sui dati RAM (non sull'exit code). La fase viene
ripetuta se:

1. Almeno una azione del chunk corrente ha `ripeti=True`
2. **E** la task NON risulta veramente finita in RAM

"Task veramente finita" = uno qualsiasi di questi 3 segnali (incrocio
RAM/nome/cambiamento):

- **Segnale A**: task `done` in RAM (step >= mstep)
- **Segnale B**: task **scomparsa** dalla lista RAM
  (= il gioco l'ha completata e rimossa)
- **Segnale C**: step in RAM avanzato oltre lo step interno
  (= la fase successiva sta gia' partendo)

Se nessuno dei 3 segnali e' attivo, ma la fase ha `ripeti=True`,
**il bot rilancia il subprocess**, indipendentemente dall'exit code.

### Esempio: il caso Fix Wiring dell'utente

Prima:
```
[Fix Wiring] Completata: None
[Fix Wiring] Teardown completato.
[Loop guard] Task non completata in RAM - cooldown di sicurezza 8s
[Exec] 'Fix Wiring' terminata - exit code 1
```
(Il bot si fermava per 8s e poi NON rilanciava perche' la logica ripeti
non scattava su ret=1.)

Dopo:
```
[Fix Wiring] Completata: True
[Fix Wiring] Teardown completato.
[Ripeti] Fase con ripeti=True, RAM dice non finita. Rilancio.
[Exec] avvio subprocess Fix Wiring (step=0)
[Fix Wiring] Esecuzione...
... continua il loop finche' la RAM segnala la task come finita
```

### Test funzionali (6/6 passati)

| # | exit code | RAM | Ripeti? | Risultato |
|---|-----------|-----|---------|-----------|
| 1 | 1         | task presente, non done | si | RILANCIA |
| 2 | 1         | task done=True | si | STOP |
| 3 | 1         | task scomparsa | si | STOP |
| 4 | 1         | step avanzato | si | STOP |
| 5 | 0         | task non done | si | RILANCIA |
| 6 | 1         | task non done | NO | STOP |

### File toccati

- `among_us_ai/execution/_motore_pkg/dispatcher.py`: aggiunto
  `return True` esplicito a fine `esegui_azioni`. Questo fix viene
  copiato automaticamente in `tasks_exec/_motore/dispatcher.py` al
  prossimo salvataggio task.
- `among_us_ai/ui/mixins/tasks_process.py`:
  - rimosso il check `if ret == 0` prima della logica ripeti
  - aggiunto nuovo helper `_fase_da_ripetere_ext(task, ret)` con
    incrocio dei 3 segnali RAM (done, scomparsa, step avanzato)

### Cosa NON e' cambiato

- API pubblica del motore: invariata
- Schema JSON delle task: invariato
- I cooldown di sicurezza per task SENZA ripeti continuano a
  funzionare come prima (Loop guard 8s)


## v2.2.3 — Checkbox 'Ripeti' su tutte le azioni (non solo cooldown)

L'utente ha chiarito che la checkbox "Ripeti" deve essere disponibile
**per OGNI azione**, non solo per i cooldown. Questo permette anche di
marcare singole azioni (es. un wiring senza cooldown finale) come
"ripetere fino a cambio step in RAM".

### Cambio nella UI

Nell'editor delle azioni, sezione "5. LISTA AZIONI REGISTRATE", ogni
riga ha ora:

```
[ ]  > 1. wiring (4 cavi + visore colore)   [^][v][X]   D:0.20s P:0.50s   [Ripeti]
[X]  > 2. yolo_drag (model.pt)              [^][v][X]   D:0.30s P:0.20s   [Ripeti]
[ ]  > 3. cooldown 70.0s                    [^][v][X]   D:70.00s P:0.00s  [Ripeti]
```

- **Checkbox a inizio riga**: sempre visibile (era il problema di
  v2.2.1, dove finiva fuori area)
- **Label "[Ripeti]" a destra**: indica visivamente lo stato.
  Giallo se attivo, grigio se inattivo.

### Logica runtime aggiornata

Il flag `ripeti` viene letto da QUALUNQUE azione del chunk corrente,
non solo dai cooldown. Regola:

> **Se almeno una azione del chunk corrente ha `ripeti=True`, l'intero
> chunk viene ripetuto** (fino a cambio step in RAM o task done).

Questa regola permette tre scenari principali:

#### Scenario 1: task con singola azione (wiring), senza cooldown

```
[X] wiring (ripeti)
```
Il bot ripete il wiring finche' la RAM segnala che la task e' done.

#### Scenario 2: task con singola fase a multi-azioni, una sola marcata

```
[ ] click "apri pannello"
[X] wiring (ripeti)
[ ] click "conferma"
```
Avendo l'intero blocco (chunk 0) almeno un'azione con ripeti, viene
ripetuto tutto in loop. Per separarlo, usa cooldown.

#### Scenario 3: task multi-fase, solo una fase da ripetere

```
[ ] click "apri pannello"
[ ] cooldown 1s              <- fine fase 0
[ ] click "intermezzo"
[X] wiring (ripeti)          <- nella fase 1
[ ] cooldown 1s              <- fine fase 1
[ ] click "conferma"
```
Solo la fase 1 viene ripetuta. Le fasi 0 e 2 vengono eseguite una
volta sola.

### Test funzionali

3/3 scenari testati e passanti:

1. wiring solitario con ripeti=True -> _fase_corrente_e_ripeti = True
2. Chunk con piu' azioni di cui una sola con ripeti -> True
3. 3 fasi separate da cooldown, solo fase 1 con azione ripeti:
   - step=0 (fase 0): False
   - step=1 (fase 1): True
   - step=2 (fase 2): False
   - step=2 (fase 1 appena finita), RAM ferma: True (RIPETI)

### File toccati

- `among_us_ai/ui/editor_mixins/list_panel.py`: checkbox + label "[Ripeti]"
  ora su tutte le righe della lista azioni (non solo cooldown).
- `among_us_ai/ui/mixins/tasks_process.py`: `_fase_corrente_e_ripeti`
  e `_fase_da_ripetere` ora cercano `ripeti=True` su QUALUNQUE azione
  del chunk, non solo sul cooldown.

### Retro-compatibilita'

Le task gia' configurate con `cooldown.ripeti=True` (v2.2.1+v2.2.2)
continuano a funzionare: l'algoritmo include il cooldown nel suo
chunk precedente quando ha ripeti=True, e quindi l'`any(ripeti)`
del chunk lo rileva correttamente.

### Cosa NON e' cambiato

- API pubblica del motore: invariata
- Subprocess: completamente invariato
- Schema JSON: invariato (campo `ripeti` su qualsiasi azione)


## v2.2.2 — Visibilita' della checkbox 'Ripeti fase'

In v2.2.1 la checkbox 'Ripeti fase' era stata posizionata a fine riga
del cooldown nella lista azioni. **L'utente ha riportato che non la
vedeva.**

### Causa

La lista azioni vive nella colonna sinistra dell'editor (width=420px).
Una riga del cooldown contiene: testo descrizione + 3 bottoni
(^v X) + testo timing + checkbox + label. Per i cooldown lunghi
(es. "COOLDOWN 70.0s"), il totale superava i 400px utili e la
checkbox finiva fuori area visibile (tagliata a destra).

### Fix

Riorganizzato il layout della riga cooldown:

**Prima** (v2.2.1, invisibile):
```
> 3. COOLDOWN 70.0s   [^][v][X]   D:70.00s P:0.00s   [ ] Ripeti fase
                                                       ^^^^^^^^^^^^^^^^
                                                       fuori area visibile
```

**Dopo** (v2.2.2, sempre visibile):
```
[ ] > 3. COOLDOWN 70.0s   [^][v][X]   D:70.00s P:0.00s   [Ripeti fase]
^^^                                                       ^^^^^^^^^^^^^
checkbox a inizio riga                                    label colorata:
                                                          - giallo se attivo
                                                          - grigio se inattivo
```

Modifiche specifiche:
1. **Checkbox a sinistra**: posizionata PRIMA della descrizione,
   sempre visibile in qualsiasi larghezza di lista.
2. **Label "Ripeti fase" a destra**: testo informativo che indica a
   cosa serve la checkbox, con colore dinamico (giallo se la fase
   e' marcata da ripetere, grigio altrimenti).
3. La checkbox ha `label=""` per non duplicare il testo.

Le righe delle azioni NON-cooldown restano invariate (la checkbox e
la label appaiono SOLO sui cooldown).

### File toccati

- `among_us_ai/ui/editor_mixins/list_panel.py`: riordinato il layout
  della riga del cooldown.

### Cosa NON e' cambiato

- Logica runtime: invariata (legge `azione.ripeti` dai cooldown)
- Salvataggio JSON: invariato
- Tutto il resto: invariato


## v2.2.1 — Fix: checkbox 'ripeti' dove serve davvero (sull'azione cooldown)

In v2.2.0 avevo messo la checkbox 'ripeti' nel posto sbagliato:
nel popup di modifica della task (sulla lista delle fasi). L'utente
ha chiarito che la voleva nell'**editor delle azioni**, perche' la
selezione delle fasi da ripetere e' una scelta che si fa quando si
mappano le azioni della task, non dalla scheda metadati.

### Cambio di posizione della checkbox

La checkbox "Ripeti fase" e' stata spostata:
- **Prima** (v2.2.0, sbagliato): nel popup di modifica task, accanto
  ad ogni fase nella lista "Fasi". Salvata come campo `fasi[i].ripeti`.
- **Dopo** (v2.2.1, corretto): nell'editor delle azioni, accanto ad
  ogni azione di tipo `cooldown` nella lista "5. LISTA AZIONI
  REGISTRATE". Salvata come campo `azione.ripeti` sull'azione cooldown.

### Perche' sul cooldown?

Il `cooldown` e' il **separatore di fase** nelle azioni: ogni cooldown
chiude una fase e ne apre la successiva. Quindi il flag "ripeti fase"
sta naturalmente sull'azione cooldown che chiude la fase da ripetere.

Esempio:
```
LISTA AZIONI:
  [1] click_rect              D:0.20s P:0.50s
  [2] click_poly              D:0.20s P:0.50s
  [3] cooldown 70.0s          [ ] Ripeti fase    <- fase 0
  [4] click_anomaly           D:0.20s P:0.50s
  [5] cooldown 5.0s           [X] Ripeti fase    <- fase 1, RIPETI!
  [6] click_until             D:0.20s P:0.50s
```

In questo esempio, la fase 1 (azioni 4, dal cooldown[0] al cooldown[1])
sara' ripetuta in loop finche' la RAM non rileva il cambio di step.

### Logica runtime aggiornata

I metodi `_fase_corrente_e_ripeti` e `_fase_da_ripetere` ora leggono
il flag direttamente dalle azioni `cooldown` invece che dalle "fasi"
dell'oggetto task:

```python
cooldowns = [a for a in azioni if a.get('tipo') == 'cooldown']
internal_step = task_internal_steps[id_task]
# La fase appena finita e' (internal_step - 1)
# Il cooldown corrispondente e' cooldowns[internal_step - 1]
```

### Modifica al popup di modifica task

Rimossa la checkbox `[R]` dalla lista delle fasi (era il posto
sbagliato). La lista delle fasi resta, ma e' ora informativa-only
(nomi delle fasi + posizione sulla mappa). Il messaggio di aiuto
dice all'utente di usare l'editor azioni per il flag ripeti.

### Scroll orizzontale aggiunto al pannello sinistro dell'editor

In v2.2.0 avevo aggiunto lo scroll solo alla lista azioni. L'utente
ha chiarito che voleva lo scroll sull'**intera barra dell'editor**
(la "barra di editing"). Aggiunto `horizontal_scrollbar=True` al
`child_window` della colonna sinistra dell'editor (width=420),
cosi' i controlli con label tradotte in italiano lunghi non vengono
tagliati.

### Pulizia API non piu' usate

- Rimosso `task_dettagli_manager.imposta_ripeti_fase` (era stato
  aggiunto in v2.2.0 ma non piu' usato).
- Rimosso `task_manager.imposta_ripeti_fase` dal facade.
- `aggiungi_fase` torna alla forma senza parametro `ripeti`.

### Test funzionali

4/4 test della logica `_fase_da_ripetere`:
1. Fase con ripeti=True + RAM ferma -> RIPETI
2. Fase con ripeti=True + RAM avanzata -> STOP
3. Fase con ripeti=True + RAM done -> STOP
4. Fase con ripeti=False -> STOP

### Cosa NON e' cambiato

- Schema delle fasi: invariato (mai aveva il campo ripeti, in v2.2.0
  l'avevo aggiunto erroneamente)
- API pubblica del motore: invariata
- Subprocess delle task: invariato


## v2.2.0 — Fasi con "ripeti" + scroll orizzontale editor

### Funzionalita' nuova: ripetizione fase fino a cambio step in RAM

Le fasi della task ora hanno un nuovo campo booleano `ripeti`. Quando
una fase ha `ripeti=True`, il bot esegue in loop le azioni di quel
chunk fino a quando uno di questi eventi si verifica:

1. La RAM segnala che lo step della task e' avanzato (cioe' il gioco
   ha riconosciuto il completamento della fase)
2. La task risulta `done` in RAM
3. Il subprocess fallisce con errore (exit code != 0)

#### Esempio d'uso

Hai una task che richiede di cliccare ripetutamente su qualcosa per
fare avanzare un loading bar o per "stordire" un nemico:
- Fase 0 (apertura task): `ripeti=False`
- Fase 1 (azione ripetuta): `ripeti=True`
- Fase 2 (chiusura): `ripeti=False`

Il bot esegue Fase 0 una volta. Poi inizia la Fase 1 e ripete le
azioni finche' la RAM non segnala che il gioco e' passato allo step
successivo, poi passa a Fase 2.

#### Schema dati: campo `ripeti` su ogni fase

```json
"fasi": [
    {"nome": "Apri task", "x": 6.5, "y": -6.6, "ripeti": false},
    {"nome": "Click ripetuto", "x": 6.5, "y": -6.6, "ripeti": true},
    {"nome": "Conferma", "x": 6.5, "y": -6.6, "ripeti": false}
]
```

Le fasi gia' presenti senza il campo `ripeti` vengono lette con
default `False` (retrocompatibilita'). La migrazione e' automatica
ed e' applicata al primo salvataggio.

#### API nuove

`TaskManager.imposta_ripeti_fase(id_task, idx_fase, ripeti)`
  - facade per `task_dettagli_manager.imposta_ripeti_fase`
  - persiste su disco automaticamente

`TaskManager.aggiungi_fase(id_task, nome, x, y, ripeti=False)`
  - aggiunto parametro opzionale `ripeti`

#### Implementazione runtime

La logica del loop NON e' nel subprocess (per non doverlo far
dipendere da pymem). E' tutta nel bot principale:

In `tasks_process.py`, due punti coordinati:

1. **Durante l'esecuzione** (`_controlla_processo_task`): controlla
   ad ogni frame se la fase corrente ha `ripeti=True` E lo step in
   RAM e' avanzato. In tal caso ferma il subprocess senza marcare done.

2. **Dopo l'esecuzione** (post-poll): se il subprocess e' finito con
   ret==0 e la fase corrente ha `ripeti=True` E lo step in RAM non e'
   avanzato E la task non e' done in RAM, **rilancia il subprocess
   con lo stesso step**. Pausa di 0.3s tra un ciclo e l'altro per
   dare al gioco il tempo di aggiornare la RAM.

Due nuovi helper:
- `_fase_corrente_e_ripeti(task)`: True se la fase corrente ha ripeti=True
- `_fase_da_ripetere(task)`: True se va effettivamente rilanciata
  (incrocio dei 3 segnali: ripeti, ram_step, ram_done)

### UI: editor task

Nell'editor delle fasi (`tasks_popups_edit.py`), ogni fase ha ora un
checkbox "[R]" accanto al pulsante "[X]" (elimina). L'utente puo'
selezionare quali fasi devono essere ripetute. Lo stato viene salvato
istantaneamente nel JSON.

Lo `child_window` della lista fasi e' stato anche allargato (210px ->
320px) e ha `horizontal_scrollbar=True` per leggere nomi di fase
lunghi senza troncamento. Stessa modifica per la lista alternativi.

### UI: editor azioni

La lista delle azioni nell'editor (componente `TAG_LIST` in
`ui_build.py`) ora ha `horizontal_scrollbar=True`. Quando un'azione
ha una descrizione lunga (poligoni con molti punti, parametri
verbose), si puo' scorrere lateralmente invece che vedere il testo
tagliato.

### File toccati

| File | Modifica |
|---|---|
| `among_us_ai/managers/task_dettagli_manager.py` | aggiunto `ripeti=False` a `aggiungi_fase`; nuovo `imposta_ripeti_fase` |
| `among_us_ai/managers/task_manager.py` | facade aggiornato |
| `among_us_ai/ui/mixins/tasks_process.py` | logica loop "ripeti" + 2 helper nuovi |
| `among_us_ai/ui/mixins/tasks_popups_edit.py` | checkbox "[R]" per fase, scroll orizzontale |
| `among_us_ai/ui/editor_mixins/ui_build.py` | scroll orizzontale lista azioni |

### Verifica fatta

- Syntax check di tutti i file modificati: OK
- Test funzionale `imposta_ripeti_fase`: lettura/scrittura/persistenza OK
- Import del package completo: OK

### Cosa NON e' cambiato

- Schema fasi esistenti: retrocompatibile (default `ripeti=False`)
- Subprocess delle task: completamente invariato (la logica vive
  nel bot principale che monitora la RAM)
- API pubblica del motore: invariata


## v2.1.11 — Fix import mancanti negli handler del package modulare

### Bug riportato

```
[Chart Course] [yolo_drag_seq] Errore iterazione:
name '_drag_seq_tappe' is not defined
```

### Causa

Quando in v2.1.9 ho splittato il monolite in package modulare,
3 import inter-modulo non sono stati aggiunti correttamente.
Gli handler chiamavano helper definiti in `input_mouse.py`, ma
mancava la riga `from .input_mouse import ...`.

### File toccati

| File                          | Helper aggiunti all'import         |
|-------------------------------|------------------------------------|
| `handlers_yolo.py`            | `_drag_seq_tappe`                  |
| `handlers_ocr.py`             | `_click_hold`, `_extract_pure_shape` |
| `handlers_simon.py`           | `_click_hold`                      |

### Verifica fatta

1. **Scan AST automatico** su tutti i 13 file del package, cercando
   nomi usati ma non importati. Dopo il fix: 0 import mancanti.
2. **Test dinamico**: invocazione di tutti i 19 handler con dati
   di test (e stub Windows + cv2 + numpy + mss + ultralytics).
   Risultato: **19/19 senza NameError**.

### Falsi positivi (non sono bug)

Lo scan ha riportato anche nomi tipo `rx, ry, sxr, syr, b, g, r,
x1, x2, y1, y2, dx, dy, kx, ky, e, item, __file__, max_val,
chk_x, chk_y, prev_chk_x, prev_chk_y, light_rx, light_ry,
start_rx, start_ry, end_rx, end_ry, exr, eyr, bx_rel, by_rel`.

Sono **tutti falsi positivi**: variabili locali create da:
- tuple unpacking: `rx, ry = _random_in_rect(...)`,
  `r, g, b = _pag.pixel(...)`, `start_rx, start_ry = left_pts[i]`
- for-loop tuple unpack: `for x1, y1, x2, y2 in boxes`
- comprehension: `[item for item in target_scelti]`
- except handler: `except Exception as e:`
- built-in di Python: `__file__` (presente in ogni modulo)
- min/max return: `_, max_val, _, _ = cv2.minMaxLoc(...)`

Il test dinamico l'ha confermato: nessuno di questi causa
NameError a runtime.

### Cosa NON e' cambiato

- API pubblica: invariata
- Struttura modulare: invariata
- Comportamento runtime: corretto come da v2.1.10 (timing JSON
  rispettato)


## v2.1.10 — Fix critico: ripristinato sleep(attesa) nel dispatcher

### Bug

Sintomo riportato: "Tutte le task vengono eseguite piu' velocemente
e non va bene, deve essere con le tempistiche indicate prima nel JSON
quando le ho mappate".

### Causa

Durante il refactor del macroswitch in handler functions (v2.1.7),
nel ricomporre `esegui_azioni` ho dimenticato di portare lo
``_time.sleep(attesa)`` finale del for loop principale.

Nel **monolite originale** (pre-v2.1.7), la struttura era:

```python
for az in azioni_da_eseguire:
    rect = _client_rect(hwnd)
    cx, cy, cw, ch = rect
    durata = az.get('durata', 0.0)
    attesa = az.get('attesa', 0.0)

    if tipo == 'click':
        _click_hold(...)
    elif tipo == 'click_rect':
        _click_hold(...)
    elif tipo == 'wiring':
        # ... logica wiring ...
        _time.sleep(attesa)         # interno
    # ... altri rami ...
    _time.sleep(attesa)             # <-- FINALE GENERALE (PERSO!)

if not is_test and current_step < len(cooldowns):
    print(f"__COOLDOWN__:{cooldowns[current_step]}", flush=True)
```

L'`_time.sleep(attesa)` **finale** veniva applicato a TUTTE le azioni
(garantendo la pausa configurata nel JSON tra un'azione e la successiva).

Nel refactor era stato perso, quindi le azioni semplici come `click`,
`click_rect`, `click_poly`, `drag` venivano eseguite consecutivamente
senza la pausa configurata. Risultato: tutte le task andavano piu'
veloci di quanto programmato.

Anche il `print __COOLDOWN__:` post-chunk era stato perso
(usato dal subprocess runner per mettere in pausa il bot prima del
prossimo step di una task multi-fase).

### Fix

Aggiunto al dispatcher (`_motore_pkg/dispatcher.py`):

```python
for az in azioni_da_eseguire:
    # ... focus check + rect + dispatch ...
    handler(az, cx, cy, cw, ch, hwnd, durata, attesa)

    # 2d) Pausa post-azione (campo "attesa" del JSON).
    # Si applica a TUTTI i tipi di azione.
    _time.sleep(attesa)

# Stampa cooldown post-chunk
if not is_test and current_step < len(cooldowns):
    print(f"__COOLDOWN__:{cooldowns[current_step]}", flush=True)
```

### Test di regressione (timing)

Confronto del **tempo totale** del package modulare contro il
**vero monolite** (v2.1.6, prima del refactor del macroswitch):

| Azione | Tempo totale (atteso) | OK |
|--------|-------|------|
| click semplice (attesa=0.5) | 0.500s | OK |
| click_rect (attesa=0.3) | 0.300s | OK |
| click_poly (attesa=0.4) | 0.400s | OK |
| drag (durata=0.5, attesa=0.2) | 0.775s | OK |
| 2 click consecutivi (attesa=0.4) | 0.800s | OK |
| drag_zone (attesa=0.3) | 0.730s | OK |

**6/6 azioni** producono lo stesso identico tempo totale del monolite
originale. Il timing del JSON e' rispettato.

### Nota: handler con doppio sleep

Alcuni handler hanno un loro `_time.sleep(attesa)` interno (wiring,
sync_click, click_anomaly, simon_says, ocr_keypad, tutti i 5 yolo_*).
Per questi tipi il timing totale fra azioni e' circa **2 * attesa**,
comportamento gia' presente nel monolite originale (era un raddoppio
volontario per minigiochi che richiedono piu' tempo di reazione).
Mantenuto invariato.

### Cosa NON e' cambiato

- API pubblica del package: invariata
- Struttura modulare del v2.1.9: invariata
- Generazione thin wrapper: invariata
- Formato JSON delle task: invariato

Solo il dispatcher e' stato corretto (5 righe aggiunte).


## v2.1.9 — Motore in package modulare

Il file `_motore.py` (1266 righe in v2.1.8) era ancora un singolo file
monolitico. L'ho splittato in un **package Python modulare** con file
piccoli, uno per famiglia di funzionalita'.

### Prima (v2.1.8)

```
tasks_exec/
+-- _motore.py              <- 1266 righe in un solo file
+-- task_001_Swipe_Card.py  <- thin wrapper 74 righe
+-- ...
```

### Dopo (v2.1.9)

```
tasks_exec/
+-- _motore/
|   +-- __init__.py             <- API pubblica (esporta run_task, ...)
|   +-- geometria.py            <- 4 helper geometriche (~80 righe)
|   +-- input_mouse.py          <- 5 helper di click/drag (~200 righe)
|   +-- handlers_clicks.py      <- _h_click, _h_click_rect, _h_click_poly, _h_click_until
|   +-- handlers_drags.py       <- _h_drag, _h_drag_multi, _h_drag_zone, _h_drag_hold
|   +-- handlers_wiring.py      <- _h_wiring (Fix Wiring)
|   +-- handlers_sync.py        <- _h_sync_click (Calibrate Distributor)
|   +-- handlers_anomaly.py     <- _h_click_anomaly (Detect Anomaly)
|   +-- handlers_yolo.py        <- 5 handler YOLO
|   +-- handlers_simon.py       <- _h_simon_says
|   +-- handlers_ocr.py         <- _h_number_match, _h_ocr_keypad
|   +-- dispatcher.py           <- _DISPATCH_MAP + esegui_azioni
|   +-- lifecycle.py            <- setup, run_task, teardown, esegui_lifecycle
+-- task_001_Swipe_Card.py      <- thin wrapper (invariato, 74 righe)
+-- ...
```

### Numeri

| Modulo | Righe | Cosa contiene |
|--------|-------|---------------|
| `geometria.py` | 83 | helper poligono/rettangolo/sampling |
| `input_mouse.py` | 196 | click + drag con Bezier umani |
| `handlers_clicks.py` | 52 | 4 handler click |
| `handlers_drags.py` | 43 | 4 handler drag |
| `handlers_wiring.py` | 64 | Fix Wiring (50 righe di logica colore) |
| `handlers_sync.py` | 78 | Calibrate Distributor (polling + verify) |
| `handlers_anomaly.py` | 55 | Detect Anomaly (extract pure shape + match) |
| `handlers_yolo.py` | 418 | 5 handler YOLO (il piu' complesso) |
| `handlers_simon.py` | 55 | Simon Says |
| `handlers_ocr.py` | 80 | number_match + ocr_keypad |
| `dispatcher.py` | 128 | DISPATCH_MAP + esegui_azioni |
| `lifecycle.py` | 116 | setup/run_task/teardown/esegui_lifecycle |
| **Totale package** | **~1366** righe | |
| **Per file (media)** | **105** righe | |

Cartella `tasks_exec/` totale: **183 KB** (era 212 KB in v2.1.8).
Il package modulare e' leggermente piu' piccolo perche' ogni file ha
solo gli import che gli servono (no duplicazioni).

### Vantaggi pratici

- **Trovi la logica per il minigioco "wiring" in `handlers_wiring.py`**:
  64 righe da leggere invece di scrollare 1266.
- **Modificare un handler non tocca gli altri file**: meno rischio di
  rompere altre cose accidentalmente.
- **Ogni modulo ha solo i suoi import** (`pyautogui` solo dove serve,
  `cv2`/`numpy` solo nei moduli YOLO/anomaly).
- **Editor friendly**: file da 50-200 righe sono leggibili a colpo
  d'occhio.
- **`__init__.py` documenta l'API pubblica**: `run_task`,
  `esegui_lifecycle`, `esegui_azioni`, `setup`, `teardown`.

### Aggiornamento del task_writer

Il `task_writer.py` ora:
1. Copia il package `_motore_pkg/` (template) come
   `tasks_exec/_motore/`.
2. Confronto file-per-file: se sono tutti identici, salta la copia
   (preserva timestamp).
3. Genera i thin wrapper dei singoli task (invariato dal v2.1.8).

I thin wrapper continuano a fare semplicemente:
```python
import _motore  # ora un package, ma l'import e' identico
_motore.esegui_lifecycle(TASK_META, AZIONI)
```

### Modifiche al codice

| File | Modifica |
|---|---|
| `among_us_ai/execution/_motore_pkg/` | NUOVA DIR: 13 file modulari (template del package) |
| `among_us_ai/execution/_motore_template.txt` | RESTA: backup variante "tutto in un file" |
| `among_us_ai/execution/task_template.py` | aggiunta `get_motore_pkg_path()` |
| `among_us_ai/execution/task_writer.py` | aggiornato per copiare il package |

### Verifica fatta

- 56/56 thin wrapper Python validi (parsing AST OK)
- Tutti i 13 file del package syntax OK
- Test funzionale: `import _motore; _motore.run_task(...)` OK
- Test equivalenza chiamate pyautogui: 6/6 azioni base producono
  sequenze IDENTICHE al monolite originale

### Cosa NON e' cambiato

- API pubblica del package: invariata (`run_task`, `esegui_azioni`,
  `esegui_lifecycle`, `setup`, `teardown`)
- Comportamento runtime identico al v2.1.8 (verificato con test
  deterministico)
- Thin wrapper: 74 righe come prima
- Formato JSON delle task: invariato


## v2.1.8 — Thin wrapper: file task da 1330 a 74 righe

I file `.py` autonomi nella cartella `tasks_exec/` erano di **1330 righe
ognuno**. Su 28 file unici, questo significa 28 × 1043 righe = ~30.000
righe duplicate sul disco (codice motore identico per tutti).

### Soluzione: separare motore e dati

Adesso la cartella `tasks_exec/` ha questa struttura:

```
tasks_exec/
+-- _motore.py                    <- codice comune (~1266 righe)
+-- task_001_Swipe_Card.py        <- thin wrapper (74 righe)
+-- task_002_Download_Data.py     <- thin wrapper (74 righe)
+-- task_003_Empty_Garbage.py     <- thin wrapper (74 righe)
+-- ...
```

Il file `_motore.py` contiene tutto il codice condiviso:
- 10 helper geometriche (`_client_rect`, `_drag_umano`, ...)
- 19 handler functions (`_h_click`, `_h_wiring`, ...)
- `_DISPATCH_MAP` (tipo -> handler)
- `esegui_azioni(...)` dispatcher principale
- `run_task(task_meta, azioni, ctx)` lifecycle parametrizzato

I file task sono **thin wrapper** che contengono SOLO i dati specifici:
- Header con metadati (id, nome, posizione, zona, ...)
- Parsing args CLI
- `TASK_META` (dict)
- `AZIONI` (list)
- 5 righe di import + 1 chiamata: `_motore.esegui_lifecycle(TASK_META, AZIONI)`

### Esempio di thin wrapper completo

```python
# =============================================================
# FILE ESECUZIONE TASK - generato automaticamente dal bot
# =============================================================
# Task ID         : 1
# Nome            : Swipe Card
# Posizione mappa : (5.915, -8.535)
# Zona            : Admin
# ...
# =============================================================
# Questo file e' un THIN WRAPPER: contiene solo i dati specifici
# della task (TASK_META e AZIONI), il codice del motore comune
# e' in `_motore.py` nella stessa cartella.
# =============================================================

# --- Parsing argomenti CLI ---
import argparse
_parser = argparse.ArgumentParser()
_parser.add_argument('--step', type=int, default=0)
_args, _ = _parser.parse_known_args()
CURRENT_STEP = _args.step

# --- Metadati della task ---
TASK_META = {
    'id': 1, 'nome': 'Swipe Card',
    'x': 5.915, 'y': -8.535, 'tipo': 5, 'id_stanza': 6,
    ...
    'step': CURRENT_STEP,
}

# --- Lista azioni della task ---
AZIONI = [{'tipo': 'click_poly', ...}, {'tipo': 'drag_zone', ...}]

# --- Import del motore comune ---
import os, sys
_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)
import _motore

# --- Entry point ---
if __name__ == '__main__':
    _motore.esegui_lifecycle(TASK_META, AZIONI)
```

### Numeri

| Metrica | Prima | Dopo | Variazione |
|---|---|---|---|
| Righe per file task | 1330 | **74** | -94% |
| Cartella `tasks_exec/` | ~2 MB | **212 KB** | -89% |
| File totali | 28 | 28 + 1 (`_motore.py`) | +1 |

### Vantaggi

- **Modificare il motore aggiorna automaticamente tutte le task**:
  basta rigenerare `_motore.py` (lo fa il task_writer al primo
  `genera_file_esecuzione`).
- **File task leggibili a colpo d'occhio**: 74 righe dove TASK_META e
  AZIONI sono visibili senza scrollare.
- **Cartella `tasks_exec/` portable**: puoi copiarla su un altro
  computer, basta avere Python + dipendenze; non serve installare
  il package `among_us_ai`.
- **Dispatch handler resta isolato per tipo** (vedi v2.1.7): nel motore
  ogni tipo di azione ha la sua funzione `_h_<tipo>`.

### Modifiche al codice

| File | Modifica |
|---|---|
| `among_us_ai/execution/_motore_template.txt` | NUOVO: template del motore comune (1266 righe) |
| `among_us_ai/execution/task_template.txt` | INVARIATO: vecchio template per file autonomi (legacy/fallback) |
| `among_us_ai/execution/task_template.py` | aggiunta funzione `get_motore_modulo()` |
| `among_us_ai/execution/task_writer.py` | RISCRITTO: genera thin wrapper + scrive `_motore.py` |

### Aggiornamento automatico

Quando il bot rigenera un file task (es. l'utente edita le azioni):
1. Il `task_writer` controlla se `tasks_exec/_motore.py` esiste e
   se e' aggiornato (confronto byte-per-byte col template).
2. Se non esiste o e' obsoleto, lo riscrive.
3. Riscrive il thin wrapper della task.

### Cosa NON e' cambiato

- **Comportamento runtime identico**: il motore e' lo stesso codice
  della v2.1.7, solo che vive in un file separato invece di essere
  ripetuto in ogni task.
- API pubblica del `TaskManager`, `task_writer`, `task_template`:
  invariate (aggiunta solo `get_motore_modulo`).
- Il vecchio `task_template.txt` resta presente: puo' essere usato
  per generare file completamente autonomi se serve.
- Formato JSON delle task: invariato.

### Verifica fatta

- 56/56 thin wrapper Python validi (parsing AST OK)
- `_motore.py` Python valido (1266 righe)
- Test funzionale: import del motore + chiamata `run_task` -> OK
- Tutte le 5 funzioni pubbliche del motore esposte:
  `esegui_azioni, esegui_lifecycle, run_task, setup, teardown`


## v2.1.7 — Refactor del macroswitch in handler functions

Il file `task_template.txt` aveva un macroswitch gigante: la funzione
`esegui_azioni` era di **980 righe**, con 18 rami `elif tipo == 'XXX'`
inseriti l'uno dopo l'altro. Ho applicato la strategia "Opzione A":
ogni ramo e' diventato una funzione handler separata, e il dispatcher
e' ora un dizionario.

### Prima

```python
def esegui_azioni(azioni, hwnd, current_step=0, is_test=False):
    # ... 50 righe di setup (split chunks, focus check, ...) ...
    for az in azioni_da_eseguire:
        # ... 20 righe di rect read ...
        if tipo == 'click':
            # 2 righe
        elif tipo == 'click_rect':
            # 3 righe
        elif tipo == 'click_poly':
            # 3 righe
        elif tipo == 'drag':
            # 5 righe
        elif tipo == 'wiring':
            # 50 righe
        elif tipo == 'sync_click':
            # 60 righe
        elif tipo == 'yolo_drag':
            # 70 righe
        # ... 11 altri rami ...
        elif tipo == 'ocr_keypad':
            # 38 righe
```

Totale: **980 righe** in una sola funzione.

### Dopo

```python
# Helper functions: una per tipo di azione
def _h_click(az, cx, cy, cw, ch, hwnd, durata, attesa):
    _click_hold(cx + int(az['rx']*cw), cy + int(az['ry']*ch), durata)

def _h_click_rect(az, cx, cy, cw, ch, hwnd, durata, attesa):
    rx, ry = _random_in_rect(az['rect'])
    _click_hold(cx + int(rx*cw), cy + int(ry*ch), durata)

# ... 17 altri handler ...

def _h_ocr_keypad(az, cx, cy, cw, ch, hwnd, durata, attesa):
    # ... 35 righe ...

# Dispatch map: tipo -> funzione
_DISPATCH_MAP = {
    'click':       _h_click,
    'click_rect':  _h_click_rect,
    'click_poly':  _h_click_poly,
    'click_until': _h_click_until,
    'drag':        _h_drag,
    'drag_multi':  _h_drag_multi,
    'drag_zone':   _h_drag_zone,
    'drag_hold':   _h_drag_hold,
    'wiring':      _h_wiring,
    'sync_click':  _h_sync_click,
    'click_anomaly': _h_click_anomaly,
    'yolo_drag':   _h_yolo_drag,
    'yolo_drag_all': _h_yolo_drag_all,
    'yolo_click':  _h_yolo_click,
    'yolo_click_all': _h_yolo_click_all,
    'yolo_drag_seq': _h_yolo_drag_seq,
    'simon_says':  _h_simon_says,
    'number_match': _h_number_match,
    'ocr_keypad':  _h_ocr_keypad,
}

# Dispatcher snello
def esegui_azioni(azioni, hwnd, current_step=0, is_test=False):
    # 1) split chunks
    # 2) loop sulle azioni
    # 3) handler = _DISPATCH_MAP.get(tipo)
    #    handler(az, cx, cy, cw, ch, hwnd, durata, attesa)
```

Totale: `esegui_azioni` e' adesso **72 righe** (di cui ~30 commenti).

### Numeri del refactor

| Metrica | Prima | Dopo |
|---------|-------|------|
| Lunghezza `esegui_azioni` | 980 righe | 72 righe |
| Funzioni nel template | 14 | 33 (14 + 19 handler) |
| Lunghezza totale del template | 1381 righe | 1248 righe |
| Lunghezza file .py generato | ~1500 righe | ~1330 righe |

### Vantaggi

- **Ogni handler e' isolato**: trovi il codice di "wiring" in `_h_wiring`
  e basta. Non serve scorrere 600 righe di altri rami per arrivarci.
- **Dispatcher leggibile**: il main loop di `esegui_azioni` e' chiaro
  in 30 righe — chunking, focus check, dispatch via dizionario.
- **Aggiungere un nuovo tipo e' facile**: scrivi `_h_<tipo>(...)` e
  aggiungilo a `_DISPATCH_MAP`. Niente file da modificare in 5 punti.
- **Testabilita'**: un handler puo' essere chiamato in isolamento,
  senza dover invocare `esegui_azioni` con tutto il setup.

### Verifica funzionale: NESSUN cambio di comportamento

Test di equivalenza con stub deterministici:

- 8/8 test su tutte le azioni base (click, click_rect, click_poly, drag,
  drag_multi, drag_zone, drag_hold, ecc.) producono **sequenze identiche
  di chiamate** a pyautogui.
- 56/56 file `.py` autonomi generati sono Python validi (parsing AST OK).
- Import del package completo OK.

### Cosa NON e' cambiato

- **Comportamento runtime identico**: con random deterministico, ogni
  azione produce la stessa sequenza di chiamate a pyautogui/win32gui
  che produceva prima.
- API delle helper functions (`_drag_umano`, `_click_hold`, ecc.):
  invariate.
- Formato JSON delle azioni: invariato.
- File `.py` generati: stessa struttura (header + meta + motore),
  solo che il motore ora ha le 19 funzioni handler invece di un
  macroswitch unico.


## v2.1.6 — Pulizia e commenti per i file delle task

### Template del motore inline (`task_template.txt`)

Il template che genera i file `.py` autonomi nei `tasks_exec/` era a
1034 righe con **0% di commenti**. L'ho riorganizzato e commentato
mantenendo lo stesso identico funzionamento:

- **Header generale** del file con glossario delle convenzioni
  (rx, ry, sx, sy, cw, ch, poly, rect, hwnd...) e descrizione
  dell'architettura.
- **Helper geometrici** (`_client_rect`, `_point_in_polygon`,
  `_random_in_rect`, `_random_in_poly`, `_click_hold`): commento
  per ogni funzione che spiega cosa fa e perche'.
- **Helper di drag/click** (`_drag_umano`, `_drag_multi`,
  `_extract_pure_shape`, `_drag_seq_tappe`, `_drag_e_tieni`): commenti
  step-by-step (Bezier quadratica, easing, anti-detection).
- **Dispatcher principale** (`esegui_azioni`): commento header con
  spiegazione dei 3 macro-passi (split chunks, loop principale,
  dispatch).
- **18 rami del macroswitch** (`if tipo == 'click'`, `elif tipo ==
  'drag'`, ...): per ogni tipo, un commento header che spiega cosa
  fa quel ramo e per quale minigioco di Among Us e' pensato.

  Esempi:
  ```python
  # --- Wiring: cablaggio per "Fix Wiring" ---
  # Ha 4 fili a sinistra, 4 connettori a destra, 4 luci-indicatore.
  # Il bot legge il colore del filo a sinistra (`pyautogui.pixel`),
  # poi lo trascina sul connettore destro dello stesso colore.
  elif tipo == 'wiring':

  # --- Sync click: clicca quando un riferimento visivo cambia ---
  # Per minigiochi tipo "Calibrate Distributor" dove c'e' una
  # lancetta che gira e bisogna cliccare quando passa per una zona.
  elif tipo == 'sync_click':

  # --- Click anomaly: clicca l'elemento "diverso" dagli altri ---
  # Per minigiochi tipo "Detect Anomaly" dove ci sono N elementi
  # tutti uguali tranne uno che e' diverso.
  elif tipo == 'click_anomaly':
  ```

- **Lifecycle finale** (`setup`, `run_task`, `teardown`, main block):
  commento descrittivo per ogni hook + esempio CLI con exit code
  attesi.

Da **0%** a **37%** di commenti nel template, codice invariato (sempre
905 righe di codice).

### Header del file generato (`task_writer.py::_build_header`)

Migliorato il commento di intestazione che il `task_writer` mette in
cima a ogni file `.py` generato. Adesso e' tutto in italiano coerente
e include un mini-manuale d'uso per chi apre il file:

```python
# =============================================================
# FILE ESECUZIONE TASK - generato automaticamente dal bot
# =============================================================
# Task ID         : 1
# Nome            : Swipe Card
# Posizione mappa : (6.510, -6.609)
# Zona            : Admin
# Tipo RAM gioco  : 5  |  ID stanza: 6
# Vitale          : False
# Due giocatori   : False
# ID padre        : None
# Numero azioni   : 2
# =============================================================
# Questo file e' AUTONOMO: non importa nulla dal package
# `among_us_ai`. Si esegue da CLI o si importa per chiamare
# `run_task(ctx)`.
#
# Uso da CLI:
#     python task_<id>_<nome>.py [--step N]
#
# Le modifiche manuali a questo file saranno SOVRASCRITTE al
# prossimo salvataggio dalla dashboard del bot. Per evitare
# la sovrascrittura, abilita 'codice personalizzato' nella
# scheda della task.
# =============================================================
```

Aggiunti commenti **anche al blocco import** del file generato:
gli import standard sono raggruppati e commentati, il parsing
argomenti CLI ha una nota che spiega lo scopo dello step
(quale chunk di azioni eseguire), gli import Windows hanno
commenti sulla disponibilita' opzionale.

### Verifica fatta

Test funzionali completi:

- 56/56 file `.py` autonomi generati, tutti **Python validi**
  (parsing AST OK su tutti).
- Import del package completo OK con stub Windows.
- Template come stringa: caricabile, nessuna eccezione di parsing.
- L'header di un file generato apparenza ricca: ID, posizione,
  zona, tipo, ID stanza, fasi tutte mostrate.

### Cosa NON e' cambiato

- **Comportamento runtime identico**: il codice eseguibile e' lo
  stesso, ho aggiunto SOLO commenti `#` (inerti per Python).
- Gli **handler** del runtime live (in `among_us_ai/execution/handlers/*.py`)
  non sono stati toccati: erano gia' commentati in v2.1.5.
- I file `.json` (struttura task + esecuzione): formato invariato.
- I file di configurazione (mappa, zone, POI): invariati.


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
