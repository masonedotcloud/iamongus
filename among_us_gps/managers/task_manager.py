"""
Gestione delle task registrate dall'utente con generazione di file Python
autonomi per la loro esecuzione.

Ogni task è un dict con metadati (id, nome, x/y, tipo RAM, room_id, fasi,
fratelli, vitale, due_giocatori, parent_id, azioni, esecuzione...).
La logica di ereditarietà permette ad una task figlia di "ereditare" le azioni
da una task padre senza duplicarle.

`crea_file_esecuzione()` produce un file .py autonomo dentro `tasks_exec/`
che può essere lanciato standalone (`python task_xxx.py`) o invocato come
sub-process dalla dashboard. Il motore di esecuzione runtime è incluso inline
nel file generato, caricato come testo da `execution/task_template.txt`.
"""

import json
import os

# Import diretto del solo modulo template — evita di caricare il runtime
# (che dipende da pyautogui/win32) per il TaskManager, che gli serve solo
# come "asset di testo" per generare i file in tasks_exec/.
from ..execution.task_template import get_motore_template


class TaskManager:
    """
    Gestisce le task registrate manualmente dall'utente.
    Formato task: {id, nome, x, y, fasi: [{nome, x, y}], note}
    Le coordinate sono in spazio di gioco.
    Il file tasks.json (da task_lista.py) viene usato per confronto.
    """

    TASKS_EXEC_DIR = "tasks_exec"   # cartella dove vengono creati i file .py per task

    # Step comuni di predisposizione (uguali per ogni task)
    STATI_SETUP = [
        ">> Avvio sequenza...",
        ">> Verifica file esecuzione...",
        ">> Caricamento parametri task...",
        ">> Navigazione verso obiettivo...",
        ">> Predisposizione completata ✓",
    ]

    # Step finali dopo la predisposizione
    STATI_LAUNCH = [
        ">> Collegamento al task node...",
        ">> Handshake completato ✓",
        ">> Task AVVIATA ✓",
    ]

    def __init__(self, task_file, tasks_def_file):
        self.task_file     = task_file
        self.tasks_def_file = tasks_def_file
        self.task_list     = []      # task personalizzate registrate dall'utente
        self.tasks_def     = {}      # {tid: info} dal tasks.json originale
        self.prossimo_id   = 1
        self._carica_def()
        self.carica()

    def _carica_def(self):
        """Carica il tasks.json originale (stesso formato di task_lista.py)."""
        if not os.path.exists(self.tasks_def_file):
            return
        try:
            with open(self.tasks_def_file, 'r') as f:
                raw = json.load(f)
            self.tasks_def = {int(k): v for k, v in raw.items()}
            print(f"Definizioni task caricate: {len(self.tasks_def)}")
        except Exception as e:
            print(f"Errore caricamento tasks.json: {e}")

    def carica(self):
        if not os.path.exists(self.task_file):
            return
        try:
            with open(self.task_file, 'r') as f:
                data = json.load(f)
            self.task_list = data.get('task_list', [])
            # prossimo_id calcolato al volo, non salvato nel JSON
            self.prossimo_id = max((t['id'] for t in self.task_list), default=0) + 1
            print(f"Task caricate: {len(self.task_list)}")
        except Exception as e:
            print(f"Errore caricamento task registrate ({e}).")

    def salva(self):
        try:
            with open(self.task_file, 'w') as f:
                # Salva rigorosamente SOLO l'array task_list. Nessun prossimo_id.
                json.dump({'task_list': self.task_list}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Errore salvataggio task ({e}).")

    def aggiungi(self, nome, x, y,
                 fasi=None, fratelli=None,
                 room_id=None, tipo=None,
                 zone_id=None, zone_local_id=None, zone_nome=None,
                 vitale=False, due_giocatori=False, cooldown=0.0, lunghezza="N/A"):
        """
        Crea e salva una task. La chiave univoca è data dalla coppia (tipo, room_id).
        Se vitale=True la task viene marcata come di importanza critica.
        Se due_giocatori=True la task richiede un secondo giocatore (es. Reattore).
        """
        task = {
            'id':            self.prossimo_id,
            'nome':          nome,
            'x':             float(x),
            'y':             float(y),
            'fasi':          fasi if fasi is not None else [],
            'fratelli':      fratelli if fratelli is not None else [],
            'tipo':          tipo,
            'room_id':       room_id,
            'zone_id':       zone_id,
            'zone_local_id': zone_local_id,
            'zone_nome':     zone_nome,
            'vitale':        bool(vitale),
            'due_giocatori': bool(due_giocatori),
            'cooldown':      float(cooldown),
            'lunghezza':     lunghezza,
            'codice_custom': False,
            # Relazione padre/figlia: se parent_id è valorizzato, la task
            # eredita le azioni dal padre. Le azioni locali (se presenti)
            # sovrascrivono interamente quelle del padre al momento della
            # generazione del file .py (override totale, non merge).
            'parent_id':     None,
            # Sequenza di azioni registrate dall'editor (click/drag/zone).
            # Ogni azione è un dict con chiave 'tipo' e i suoi parametri.
            'azioni':        [],
            # Predisposizione all'esecuzione: file .py associato e stato corrente
            'esecuzione': {
                'file':   None,   # path del file .py generato
                'stato':  'idle', # idle | ready | running | done | error
                'params': {},     # parametri extra passabili all'esecutore
            },
        }

        self.task_list.append(task)
        self.prossimo_id += 1
        self.salva()
        return task

    def imposta_azioni(self, id_task, azioni):
        """
        Sostituisce la lista azioni di una task (output dell'editor).
        Invalida il file .py della task stessa e di tutte le sue task figlie:
        - La task stessa ha azioni cambiate → il suo file è stantio
        - Le figlie che ereditano le azioni del padre → anche i loro file
          sono stantii e devono essere rigenerati al prossimo lancio
        Non rigenera automaticamente: il file viene creato a predisponi_esecuzione
        o su richiesta esplicita con "Genera .py".
        """
        for t in self.task_list:
            if t['id'] == id_task:
                t['azioni'] = list(azioni)
                # Invalida il file della task modificata
                if not t.get('codice_custom', False):
                    t.setdefault('esecuzione', {})['file']  = None
                    t.setdefault('esecuzione', {})['stato'] = 'idle'
                break
        # Invalida il file di tutte le figlie che ereditano (azioni proprie vuote)
        for figlia in self.get_figli(id_task):
            if not figlia.get('azioni') and not figlia.get('codice_custom', False):   # eredita: nessuna azione propria
                figlia.setdefault('esecuzione', {})['file']  = None
                figlia.setdefault('esecuzione', {})['stato'] = 'idle'
        self.salva()

    def imposta_parent(self, id_task, parent_id):
        """
        Collega una task a un padre (o scollega passando None).
        Rifiuta self-loop e catene: la task figlia può avere un solo
        livello di ereditarietà (padre -> figlia), non padre -> figlia -> nipote.
        Ritorna True se ok, False altrimenti.

        Invalida il riferimento al file .py esistente: cambiare il parent
        cambia le azioni ereditate, quindi qualsiasi file precedente sarebbe
        stantio. Il file viene rigenerato automaticamente al prossimo lancio
        (predisponi_esecuzione) o manualmente con "Genera .py".
        """
        if parent_id is not None:
            if parent_id == id_task:
                return False
            padre = self.get_by_id(parent_id)
            if padre is None:
                return False
            # Rifiuta se il candidato padre è a sua volta figlio di qualcuno
            if padre.get('parent_id') is not None:
                return False
        for t in self.task_list:
            if t['id'] == id_task:
                old_parent = t.get('parent_id')
                t['parent_id'] = parent_id
                # Invalida il file solo se il parent è effettivamente cambiato
                if old_parent != parent_id and not t.get('codice_custom', False):
                    exec_info = t.get('esecuzione', {})
                    exec_info['file']  = None   # forza rigenerazione al prossimo lancio
                    exec_info['stato'] = 'idle'
                    t['esecuzione'] = exec_info
                break
        self.salva()
        return True

    def get_figli(self, id_task):
        """Ritorna la lista delle task figlie di id_task."""
        return [t for t in self.task_list if t.get('parent_id') == id_task]

    def get_azioni_effettive(self, id_task):
        """
        Risolve le azioni effettive di una task considerando il padre:
          - Se la task ha azioni proprie (non vuote) -> usa quelle (override).
          - Altrimenti, se ha un parent_id valido -> usa le azioni del padre.
          - Altrimenti -> lista vuota.
        Ritorna anche l'id della task che ha FORNITO le azioni (util per debug).
        """
        t = self.get_by_id(id_task)
        if t is None:
            return [], None
        if t.get('azioni'):
            return list(t['azioni']), id_task
        parent_id = t.get('parent_id')
        if parent_id is not None:
            padre = self.get_by_id(parent_id)
            if padre is not None:
                return list(padre.get('azioni', [])), parent_id
        return [], None

    def crea_file_esecuzione(self, id_task):
        """
        Genera (o sovrascrive) il file .py associato alla task.
        Il file è AUTONOMO: contiene dati task + motore Bezier + esecutore
        che sa gestire tutti i tipi di azione (click, click_rect, click_poly,
        drag, drag_multi, drag_zone). Può essere lanciato da riga di comando
        con 'python task_xxx.py' per debug, oppure importato dalla dashboard
        che ne chiama run_task(ctx).
        Ritorna il path del file creato, oppure None in caso di errore.
        """
        # Se la task eredita, delega la generazione al padre
        t_azioni, _src_id = self.get_azioni_effettive(id_task)
        if _src_id is not None and _src_id != id_task:
            return self.crea_file_esecuzione(_src_id)

        task = self.get_by_id(id_task)
        if task is None:
            return None

        # Non sovrascrivere mai se è attivato il flag custom
        if task.get('codice_custom', False):
            ex_file = task.get('esecuzione', {}).get('file')
            if ex_file and os.path.exists(ex_file):
                print(f"[TaskManager] Preservo file custom: {os.path.basename(ex_file)}")
                return ex_file

        os.makedirs(self.TASKS_EXEC_DIR, exist_ok=True)

        # Nome file sicuro: task_<id>_<nome_sanitizzato>.py
        nome_safe = "".join(c if c.isalnum() or c in "_- " else "_" for c in task['nome'])
        nome_safe = nome_safe.replace(" ", "_").strip("_")
        filename  = f"task_{task['id']:03d}_{nome_safe}.py"
        filepath  = os.path.join(self.TASKS_EXEC_DIR, filename)

        fasi_lines = ""
        for i, f in enumerate(task.get('fasi', [])):
            fasi_lines += (
                f"# Fase {i}: {f['nome']}  @ ({f['x']:.3f}, {f['y']:.3f})\n"
            )
        if not fasi_lines:
            fasi_lines = "# Nessuna fase registrata\n"

        # Valori pre-estratti per evitare accessi nidificati nella f-string
        t_id         = task['id']
        t_nome       = task['nome']
        t_x          = task['x']
        t_y          = task['y']
        t_zona       = task.get('zone_nome', 'N/A')
        t_tipo       = task.get('tipo')
        t_room_id    = task.get('room_id')
        t_vitale     = task.get('vitale', False)
        t_due_p      = task.get('due_giocatori', False)
        t_lunghezza  = task.get('lunghezza', 'N/A')
        t_fasi       = task.get('fasi', [])
        # Risolve padre/figlia: usa azioni proprie se presenti, altrimenti quelle del padre
        t_azioni, _src_id = self.get_azioni_effettive(id_task)
        t_parent_id  = task.get('parent_id')
        t_params     = task.get('esecuzione', {}).get('params', {})

        # Nome finestra di default (usato se ctx non lo fornisce)
        finestra_default = "Among Us"

        # Costruiamo il template in più blocchi: header + motore + main
        header = (
            "# =============================================================\n"
            "# FILE ESECUZIONE - generato automaticamente dalla dashboard\n"
            f"# Task ID    : {t_id}\n"
            f"# Nome       : {t_nome}\n"
            f"# Posizione  : ({t_x:.3f}, {t_y:.3f})\n"
            f"# Zona       : {t_zona}\n"
            f"# Tipo RAM   : {t_tipo}  |  Room ID: {t_room_id}\n"
            f"# Vitale     : {t_vitale}\n"
            f"# 2 Giocatori: {t_due_p}\n"
            f"# Parent ID  : {t_parent_id}"
            + (f"  (azioni ereditate)\n" if (t_parent_id is not None and _src_id == t_parent_id) else "\n")
            + f"# Azioni     : {len(t_azioni)}"
            + (f"  [dalla task padre {_src_id}]\n" if (_src_id is not None and _src_id != t_id) else "\n")
            + "# =============================================================\n"
            "# Il file è AUTONOMO: esegui 'python <file>' oppure importa e\n"
            "# chiama run_task(ctx). Modifica le azioni rieseguendo l'editor\n"
            "# dalla dashboard; le modifiche manuali a questo file saranno\n"
            "# sovrascritte al prossimo salvataggio.\n"
            "# =============================================================\n\n"
            "# --- Fasi registrate (ordine di esecuzione suggerito) ---\n"
            f"{fasi_lines}"
            "\n"
            "import time\n"
            "import math\n"
            "import random\n\n"
            "import sys\n"
            "import argparse\n\n"
            "# Estrai lo step passato dal TaskManager basato sulla RAM\n"
            "parser = argparse.ArgumentParser()\n"
            "parser.add_argument('--step', type=int, default=0)\n"
            "args, _ = parser.parse_known_args()\n"
            "CURRENT_STEP = args.step\n\n"
            "try:\n"
            "    import pyautogui\n"
            "    import win32gui\n"
            "    pyautogui.FAILSAFE = True\n"
            "    pyautogui.PAUSE = 0\n"
            "    _OK = True\n"
            "except Exception as _e:\n"
            "    print(f'[task] dipendenze mancanti: {_e}')\n"
            "    _OK = False\n\n"
        )

        meta_block = (
            "TASK_META = {\n"
            f"    'id':            {t_id!r},\n"
            f"    'nome':          {t_nome!r},\n"
            f"    'x':             {t_x:.3f},\n"
            f"    'y':             {t_y:.3f},\n"
            f"    'tipo':          {t_tipo!r},\n"
            f"    'room_id':       {t_room_id!r},\n"
            f"    'vitale':        {t_vitale!r},\n"
            f"    'due_giocatori': {t_due_p!r},\n"
            f"    'lunghezza':     {t_lunghezza!r},\n"
            f"    'parent_id':     {t_parent_id!r},\n"
            f"    'fasi':          {t_fasi!r},\n"
            f"    'params':        {t_params!r},\n"
            "    'step':          CURRENT_STEP,\n"
            "}\n\n"
            f"FINESTRA_DEFAULT = {finestra_default!r}\n\n"
            f"AZIONI = {t_azioni!r}\n\n"
        )

        # Motore di esecuzione: il file generato importa da main_modulare,
        # che è il file unico contenente tutta la logica del progetto.
        # Motore di esecuzione INLINE — completamente autonomo.
        # Il file generato non dipende da nessun modulo esterno.
        # Funziona con main.py, main_modulare.py o standalone.
        # Motore di esecuzione: caricato da template esterno
        # (execution/task_template.txt). Il file generato NON dipende da
        # nessun modulo esterno: include il motore inline ed e' autonomo.
        motore_block = get_motore_template()

        template = header + meta_block + motore_block

        try:
            with open(filepath, 'w', encoding='utf-8') as fh:
                fh.write(template)
            print(f"[TaskManager] File esecuzione creato: {filepath}")
            return filepath
        except Exception as e:
            print(f"[TaskManager] Errore creazione file esecuzione: {e}")
            return None

    def predisponi_esecuzione(self, id_task):
        """
        Azioni comuni di predisposizione che vengono eseguite per OGNI task
        prima che parta la logica specifica:
          1. Rigenera SEMPRE il file .py — questo garantisce che le azioni
             siano sempre aggiornate, in particolare per le task figlie che
             ereditano le azioni dal padre: se il file fosse riusato da una
             generazione precedente (prima che il parent_id fosse impostato
             o le azioni del padre fossero cambiate), conterrebbe AZIONI = []
             e la task eseguirebbe "nessuna azione registrata" pur avendo un
             padre con azioni valide.
          2. Imposta stato -> 'ready'
          3. Aggiorna il riferimento al file nel JSON
        Ritorna (filepath, log_messages) — log_messages è una lista di stringhe
        da mostrare nel popup animato.
        """
        task = self.get_by_id(id_task)
        if task is None:
            return None, ["!! Task non trovata"]

        log = []

        # 1. Rigenera sempre il file .py.
        # Nota: la rigenerazione è idempotente e costa ~10ms; è molto più
        # sicura del riuso del file stantio. In particolare risolve il caso
        # frequente: task figlia creata → file generato (AZIONI=[]) → parent
        # assegnato → lancio → file stantio eseguito → "nessuna azione".
        exec_info = task.setdefault('esecuzione', {
            'file': None, 'stato': 'idle', 'params': {}
        })
        azioni_eff, src_id = self.get_azioni_effettive(id_task)
        
        if src_id is not None and src_id != id_task:
            log.append(f">> Azioni ereditate dalla task padre [{src_id}] ({len(azioni_eff)} azioni)")
            log.append(f">> Eredito file esecuzione dal padre [{src_id}]...")
            target_task = self.get_by_id(src_id)
            if not target_task:
                log.append("!! Padre non trovato")
                exec_info['stato'] = 'error'
                self.salva()
                return None, log
        else:
            if azioni_eff:
                log.append(f">> Azioni proprie: {len(azioni_eff)}")
            else:
                log.append(">> Attenzione: nessuna azione registrata (né proprie né ereditate)")
            target_task = task
            src_id = id_task

        target_exec = target_task.setdefault('esecuzione', {
            'file': None, 'stato': 'idle', 'params': {}
        })

        if target_task.get('codice_custom', False) and target_exec.get('file') and os.path.exists(target_exec['file']):
            log.append(">> Codice custom: preservo il file esistente ✓")
            filepath = target_exec['file']
        else:
            log.append(">> Generazione file esecuzione...")
            filepath = self.crea_file_esecuzione(src_id)
            if filepath:
                log.append(f">> File pronto: {os.path.basename(filepath)} ✓")
                target_exec['file'] = filepath
            else:
                log.append("!! Errore creazione file esecuzione")
                exec_info['stato'] = 'error'
                self.salva()
                return None, log

        # 2. Aggiorna riferimento e stato nel JSON
        exec_info['file']  = filepath
        exec_info['stato'] = 'ready'
        self.salva()
        log.append(f">> Stato impostato: ready ✓")
        log.append(f">> Params: {exec_info.get('params', {})}")

        return filepath, log

    def imposta_stato_esecuzione(self, id_task, stato, params=None):
        """Aggiorna stato (idle|ready|running|done|error) e opzionalmente i params."""
        for t in self.task_list:
            if t['id'] == id_task:
                exec_info = t.setdefault('esecuzione', {
                    'file': None, 'stato': 'idle', 'params': {}
                })
                exec_info['stato'] = stato
                if params is not None:
                    exec_info['params'] = params
                break
        self.salva()

    def rimuovi(self, id_task):
        self.task_list = [t for t in self.task_list if t['id'] != id_task]
        self.salva()

    def aggiorna(self, id_task, nome, x, y, vitale=None, due_giocatori=None, codice_custom=None, cooldown=None, lunghezza=None):
        for t in self.task_list:
            if t['id'] == id_task:
                t['nome'] = nome
                t['x'] = float(x)
                t['y'] = float(y)
                if vitale is not None:
                    t['vitale'] = bool(vitale)
                if due_giocatori is not None:
                    t['due_giocatori'] = bool(due_giocatori)
                if codice_custom is not None:
                    t['codice_custom'] = bool(codice_custom)
                if cooldown is not None:
                    t['cooldown'] = float(cooldown)
                if lunghezza is not None:
                    t['lunghezza'] = str(lunghezza)
                break
        self.salva()

    def aggiungi_fase(self, id_task, nome_fase, x, y):
        for t in self.task_list:
            if t['id'] == id_task:
                t.setdefault('fasi', []).append({'nome': nome_fase, 'x': float(x), 'y': float(y)})
                break
        self.salva()

    def aggiungi_fratello(self, id_task, x, y):
        for t in self.task_list:
            if t['id'] == id_task:
                t.setdefault('fratelli', []).append({'x': float(x), 'y': float(y)})
                break
        self.salva()

    def set_zone_link(self, id_task, game_zone_id):
        """Collega una task a una zona tramite game_zone_id. None per scollegare."""
        for t in self.task_list:
            if t['id'] == id_task:
                if game_zone_id is None:
                    t.pop('zone_id', None)
                else:
                    t['zone_id'] = int(game_zone_id)
                break
        self.salva()

    def rimuovi_fase(self, id_task, idx_fase):
        for t in self.task_list:
            if t['id'] == id_task:
                fasi = t.get('fasi', [])
                if 0 <= idx_fase < len(fasi):
                    fasi.pop(idx_fase)
                break
        self.salva()

    def rimuovi_fratello(self, id_task, idx_fratello):
        for t in self.task_list:
            if t['id'] == id_task:
                fratelli = t.get('fratelli', [])
                if 0 <= idx_fratello < len(fratelli):
                    fratelli.pop(idx_fratello)
                break
        self.salva()

    def get_by_id(self, id_task):
        for t in self.task_list:
            if t['id'] == id_task:
                return t
        return None

    def is_registered(self, task_nome):
        """Controlla se una task con quel nome è già registrata."""
        nome_lower = task_nome.lower()
        for t in self.task_list:
            if t['nome'].lower() == nome_lower:
                return True
        return False

    def find_registered(self, tipo=None, room_id=None):
        """
        Cerca la task registrata corrispondente incrociando 
        sia il Task Type (tipo) che l'ID della stanza (room_id).
        Entrambi i valori devono coincidere.
        """
        if tipo is not None and room_id is not None:
            for t in self.task_list:
                if t.get('tipo') == tipo and t.get('room_id') == room_id:
                    return t
                    
        return None

    # ---- Confronto con memoria ----
    def get_memory_tasks_info(self, memory_tasks):
        """
        Scorre le task lette dalla RAM e le associa a quelle salvate nel tuo JSON
        passando i parametri per il controllo incrociato.
        """
        enriched = []
        for mt in memory_tasks:
            # Qui avviene l'incrocio: passiamo entrambi i parametri estratti dalla RAM
            reg = self.find_registered(
                tipo=mt.get('tipo'),
                room_id=mt.get('room_id')
            )
            
            # Aggiungiamo i dati al dizionario finale
            enriched.append({**mt, 'registrata': reg is not None, 'reg_task': reg})
            
        return enriched

