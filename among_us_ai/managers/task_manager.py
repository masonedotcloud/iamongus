"""
Facade ``TaskManager``: API unica per il resto del codice, internamente
delega a ``TaskDettagliManager`` (struttura) e ``TaskEsecuzioneManager``
(azioni / esecuzione).

Perche' una facade?

I 19 mixin di ``GPSVisualizerPro`` accedono al ``TaskManager`` con un'API
ricca che mescolava dettagli ed esecuzione. Se cambiassi quell'API, dovrei
modificare decine di chiamate sparse. La facade preserva l'API attesa:

    tm = TaskManager('tasks_dettagli.json',
                     'tasks_esecuzione/',
                     'tasks.json')
    tm.task_list           # lista di task "complete" (dettagli + esec)
    tm.aggiungi(...)       # crea sia dettagli che file esecuzione
    tm.imposta_azioni(...) # delegato a esecuzione_manager
    tm.imposta_padre(...) # delegato a dettagli_manager
    tm.crea_file_esecuzione(id) # genera il .py (immutato)

Migrazione automatica:
- Al primo avvio della v2.1, se esistono ``task_registrate.json`` ma NON
  ``tasks_dettagli.json``, i 56 task vengono splittati nei due nuovi
  formati e il vecchio file viene rinominato ``task_registrate.json.bak``
  per sicurezza.

Generazione del file ``.py`` per la task: identica a prima, delegata a
``execution.task_writer.genera_file_esecuzione``.
"""

import json
import os

from ..execution.task_writer import genera_file_esecuzione
from .task_dettagli_manager import TaskDettagliManager
from .task_esecuzione_manager import TaskEsecuzioneManager


class TaskManager:
    """
    Facade: ``GPSVisualizerPro`` parla solo con questa classe.
    """

    TASKS_EXEC_DIR = "tasks_exec"   # cartella dove sono i .py generati

    # Step comuni dell'animazione di lancio (UI usa questi valori)
    STATI_SETUP = [
        ">> Avvio sequenza...",
        ">> Verifica file esecuzione...",
        ">> Caricamento parametri task...",
        ">> Navigazione verso obiettivo...",
        ">> Predisposizione completata OK",
    ]
    STATI_LAUNCH = [
        ">> Collegamento al task node...",
        ">> Handshake completato OK",
        ">> Task AVVIATA OK",
    ]

    def __init__(self,
                 dettagli_file="tasks_dettagli.json",
                 esecuzione_dir="tasks_esecuzione",
                 tasks_def_file="tasks.json",
                 legacy_file="task_registrate.json"):
        """Inizializza l'istanza con i valori di default."""
        self.dettagli_file  = dettagli_file
        self.esecuzione_dir = esecuzione_dir
        self.tasks_def_file = tasks_def_file
        self.tasks_def      = {}

        # Migrazione (se serve) PRIMA di istanziare i sub-manager.
        self._migra_se_serve(legacy_file)

        self.dettagli  = TaskDettagliManager(dettagli_file)
        self.esecuzione = TaskEsecuzioneManager(esecuzione_dir)

        self._carica_def()

        # Compat: il resto del codice si aspetta tm.task_list e tm.prossimo_id.
        # Sono PROPERTY (vedi sotto), aggiornate in tempo reale.

    # ==================================================================
    # MIGRAZIONE da v2.0 (task_registrate.json) -> v2.1 (split)
    # ==================================================================

    def _migra_se_serve(self, legacy_file):
        """
        Se esiste ``task_registrate.json`` e NON esiste
        ``tasks_dettagli.json``, splitta il vecchio formato nei due
        nuovi. Backup atomico del vecchio file.
        """
        if not os.path.exists(legacy_file):
            return  # niente da migrare
        if os.path.exists(self.dettagli_file):
            return  # gia' migrato in passato
        try:
            with open(legacy_file, 'r', encoding='utf-8') as f:
                # Carica e deserializza JSON da file
                data = json.load(f)
        except Exception as e:
            print(f"[Migrazione] Impossibile leggere {legacy_file}: {e}")
            return

        old_list = data.get('task_list', [])
        if not old_list:
            return

        print(f"[Migrazione] Splitto {len(old_list)} task da {legacy_file}...")

        # Crea la directory (e i parent) se non esiste
        os.makedirs(self.esecuzione_dir, exist_ok=True)

        dettagli_list = []
        for t in old_list:
            # NB: leggo sia i nomi nuovi (v2.1) sia i nomi vecchi (v2.0)
            # cosi' la migrazione funziona sia da un task_registrate.json
            # del nuovo formato che da uno del vecchio formato.
            def _get(*keys, default=None):
                """Ritorna."""
                for k in keys:
                    if k in t:
                        return t[k]
                return default

            d = {
                'id':              t['id'],
                'nome':            t.get('nome', ''),
                'x':               float(t.get('x', 0)),
                'y':               float(t.get('y', 0)),
                'tipo':            t.get('tipo'),
                'id_stanza':       _get('id_stanza', 'room_id'),
                'lunghezza':       t.get('lunghezza', 'N/A'),
                'vitale':          bool(t.get('vitale', False)),
                'due_giocatori':   bool(t.get('due_giocatori', False)),
                'cooldown':        float(t.get('cooldown', 0.0)),
                'id_padre':        _get('id_padre', 'parent_id'),
                'fasi':            t.get('fasi', []),
                'alternativi':     _get('alternativi', 'fratelli', default=[]),
                'id_zona':         _get('id_zona', 'zone_id'),
                'id_zona_locale':  _get('id_zona_locale', 'zone_local_id'),
                'nome_zona':       _get('nome_zona', 'zone_nome'),
            }
            dettagli_list.append(d)

            # --- Scrivo il file di esecuzione per questa task ---
            esec_orig = t.get('esecuzione', {})
            # rinomino params -> parametri se presente
            if isinstance(esec_orig, dict) and 'params' in esec_orig and 'parametri' not in esec_orig:
                esec_orig = dict(esec_orig)
                esec_orig['parametri'] = esec_orig.pop('params')
            if not esec_orig:
                esec_orig = {'file': None, 'stato': 'idle', 'parametri': {}}

            e = {
                'id':                    t['id'],
                'azioni':                t.get('azioni', []),
                'codice_personalizzato': bool(_get('codice_personalizzato',
                                                   'codice_custom',
                                                   default=False)),
                'esecuzione':            esec_orig,
            }
            ep = os.path.join(self.esecuzione_dir,
                              f"task_{int(t['id']):03d}.json")
            try:
                with open(ep, 'w', encoding='utf-8') as f:
                    # Serializza su file in formato JSON
                    json.dump(e, f, indent=2, ensure_ascii=False)
            except Exception as ex:
                print(f"[Migrazione] Errore scrittura {ep}: {ex}")

        # Scrivo il file dei dettagli
        try:
            with open(self.dettagli_file, 'w', encoding='utf-8') as f:
                # Serializza su file in formato JSON
                json.dump(
                    {'task_list': dettagli_list},
                    f, indent=2, ensure_ascii=False,
                )
        except Exception as ex:
            print(f"[Migrazione] Errore scrittura {self.dettagli_file}: {ex}")
            return

        # Rinomino il vecchio file come backup
        backup = legacy_file + '.bak'
        try:
            if os.path.exists(backup):
                # Cancella il file dal disco
                os.remove(backup)
            os.rename(legacy_file, backup)
            print(f"[Migrazione] Completata. Backup: {backup}")
        except Exception as ex:
            print(f"[Migrazione] Errore rename backup: {ex}")

    def _carica_def(self):
        """Carica tasks.json (definizioni statiche di Among Us, opzionale)."""
        if not os.path.exists(self.tasks_def_file):
            return
        try:
            with open(self.tasks_def_file, 'r', encoding='utf-8') as f:
                # Carica e deserializza JSON da file
                raw = json.load(f)
            self.tasks_def = {int(k): v for k, v in raw.items()}
            print(f"Definizioni task caricate: {len(self.tasks_def)}")
        except Exception as e:
            print(f"Errore caricamento tasks.json: {e}")

    # ==================================================================
    # COMPATIBILITA' API: i mixin si aspettano task_list, prossimo_id, ...
    # ==================================================================

    @property
    def task_list(self):
        """
        Lista di task "complete" (dettagli + esecuzione fusi), come
        nel vecchio formato. Ricostruita al volo per stare in sync.
        """
        return [self._merge(d) for d in self.dettagli.task_list]

    @property
    def prossimo_id(self):
        """Ritorna il prossimo id univoco da assegnare a una nuova task."""
        return self.dettagli.prossimo_id

    def _merge(self, d):
        """Ricostruisce un dict task "completo" (dettagli + esecuzione)."""
        e = self.esecuzione.get(d['id']) or {}
        return {
            **d,
            'azioni':        e.get('azioni', []),
            'codice_personalizzato': e.get('codice_personalizzato', False),
            'esecuzione':    dict(e.get('esecuzione', {
                'file': None, 'stato': 'idle', 'params': {},
            })),
        }

    def carica(self):
        """Compat: in passato ricaricava task_registrate.json."""
        self.dettagli.carica()
        self.esecuzione._carica_tutto()

    def salva(self):
        """Compat: salva entrambi i sub-manager."""
        self.dettagli.salva()
        # esecuzione_manager salva automaticamente per ogni operazione

    # ==================================================================
    # CRUD: API che il resto del codice gia' usa
    # ==================================================================

    def aggiungi(self, nome, x, y,
                 fasi=None, alternativi=None,
                 id_stanza=None, tipo=None,
                 id_zona=None, id_zona_locale=None, nome_zona=None,
                 vitale=False, due_giocatori=False,
                 cooldown=0.0, lunghezza="N/A"):
        """Aggiunge."""
        d = self.dettagli.aggiungi(
            nome=nome, x=x, y=y,
            fasi=fasi, alternativi=alternativi,
            id_stanza=id_stanza, tipo=tipo,
            id_zona=id_zona, id_zona_locale=id_zona_locale, nome_zona=nome_zona,
            vitale=vitale, due_giocatori=due_giocatori,
            cooldown=cooldown, lunghezza=lunghezza,
        )
        # Crea anche il record di esecuzione vuoto
        self.esecuzione.crea_per(d['id'], azioni=[], codice_personalizzato=False)
        return self._merge(d)

    def aggiorna(self, id_task, nome, x, y,
                 vitale=None, due_giocatori=None,
                 codice_personalizzato=None, cooldown=None, lunghezza=None,
                 delay_avvio=None,
                 loop_guard_retry=None):
        """Aggiorna."""
        self.dettagli.aggiorna(
            id_task, nome, x, y,
            vitale=vitale, due_giocatori=due_giocatori,
            cooldown=cooldown, lunghezza=lunghezza,
            delay_avvio=delay_avvio,
            loop_guard_retry=loop_guard_retry,
        )
        if codice_personalizzato is not None:
            self.esecuzione.set_codice_personalizzato(id_task, codice_personalizzato)

    def rimuovi(self, id_task):
        """Rimuove."""
        self.dettagli.rimuovi(id_task)
        self.esecuzione.rimuovi(id_task)

    def get_by_id(self, id_task):
        """Ritorna by id."""
        d = self.dettagli.get_by_id(id_task)
        if d is None:
            # Goal irraggiungibile o limite nodi superato
            return None
        return self._merge(d)

    def is_registered(self, task_nome):
        """Ritorna se registered."""
        return self.dettagli.is_registered(task_nome)

    def find_registered(self, tipo=None, id_stanza=None):
        """Cerca registered."""
        d = self.dettagli.find_registered(tipo=tipo, id_stanza=id_stanza)
        return self._merge(d) if d else None

    # ==================================================================
    # PARENT / FIGLI (delegato ai dettagli)
    # ==================================================================

    def imposta_padre(self, id_task, id_padre):
        """Imposta padre."""
        d = self.dettagli.get_by_id(id_task)
        old_parent = d.get('id_padre') if d else None
        ok = self.dettagli.imposta_padre(id_task, id_padre)
        if ok and old_parent != id_padre:
            # Cambiare parent invalida il file .py: le azioni ereditate
            # sono potenzialmente diverse.
            self.esecuzione.invalida_file(id_task)
        return ok

    def get_figli(self, id_task):
        """Ritorna figli."""
        return [self._merge(d) for d in self.dettagli.get_figli(id_task)]

    # ==================================================================
    # AZIONI (delegato all'esecuzione)
    # ==================================================================

    def imposta_azioni(self, id_task, azioni):
        """Sostituisce le azioni e invalida i file .py della task e delle figlie."""
        self.esecuzione.imposta_azioni(id_task, azioni)
        # Invalida anche il file delle figlie che ereditano (azioni proprie vuote)
        for figlia_d in self.dettagli.get_figli(id_task):
            azioni_figlia = self.esecuzione.get_azioni(figlia_d['id'])
            if not azioni_figlia:  # eredita
                self.esecuzione.invalida_file(figlia_d['id'])

    def get_azioni_effettive(self, id_task):
        """
        Risolve le azioni effettive della task con ereditarieta':
        - Azioni proprie (non vuote) -> override
        - Altrimenti: azioni del padre (se id_padre valido)
        - Altrimenti: lista vuota
        Ritorna (azioni, src_id) dove src_id e' la task che le fornisce.
        """
        d = self.dettagli.get_by_id(id_task)
        if d is None:
            return [], None
        proprie = self.esecuzione.get_azioni(id_task)
        if proprie:
            return proprie, id_task
        id_padre = d.get('id_padre')
        if id_padre is not None:
            padre_d = self.dettagli.get_by_id(id_padre)
            if padre_d is not None:
                return self.esecuzione.get_azioni(id_padre), id_padre
        return [], None

    # ==================================================================
    # FASI / FRATELLI / ZONE LINK (delegato ai dettagli)
    # ==================================================================

    def aggiungi_fase(self, id_task, nome_fase, x, y):
        """Aggiunge fase. Per marcare una fase come 'ripeti', spunta il
        checkbox 'Ripeti fase' sull'azione cooldown corrispondente
        nell'editor delle azioni."""
        self.dettagli.aggiungi_fase(id_task, nome_fase, x, y)

    def rimuovi_fase(self, id_task, idx_fase):
        """Rimuove fase."""
        self.dettagli.rimuovi_fase(id_task, idx_fase)

    def aggiungi_alternativo(self, id_task, x, y):
        """Aggiunge alternativo."""
        self.dettagli.aggiungi_alternativo(id_task, x, y)

    def rimuovi_alternativo(self, id_task, idx_alternativo):
        """Rimuove alternativo."""
        self.dettagli.rimuovi_alternativo(id_task, idx_alternativo)

    def imposta_collegamento_zona(self, id_task, game_zone_id):
        """Imposta collegamento zona."""
        self.dettagli.imposta_collegamento_zona(id_task, game_zone_id)

    # ==================================================================
    # GENERAZIONE FILE .PY + CICLO DI VITA ESECUZIONE
    # ==================================================================

    def crea_file_esecuzione(self, id_task):
        """
        Genera (o sovrascrive) il file ``.py`` autonomo per la task.
        Risolve l'ereditarieta' parent->figlia e delega la scrittura
        a ``execution.task_writer.genera_file_esecuzione``.
        """
        # Se la task eredita, delega al padre (cosi' figli puntano allo
        # stesso file del padre, no duplicazione su disco).
        t_azioni, src_id = self.get_azioni_effettive(id_task)
        if src_id is not None and src_id != id_task:
            return self.crea_file_esecuzione(src_id)

        d = self.dettagli.get_by_id(id_task)
        if d is None:
            # Goal irraggiungibile o limite nodi superato
            return None

        # Custom code: non sovrascrivere mai un file esistente
        e = self.esecuzione.get(id_task) or {}
        if e.get('codice_personalizzato', False):
            ex_file = e.get('esecuzione', {}).get('file')
            if ex_file and os.path.exists(ex_file):
                print(f"[TaskManager] Preservo file custom: "
                      f"{os.path.basename(ex_file)}")
                return ex_file

        # Per la generazione il writer si aspetta un dict "completo"
        task_completo = self._merge(d)
        return genera_file_esecuzione(
            task=task_completo,
            azioni_effettive=t_azioni,
            src_id=src_id,
            tasks_exec_dir=self.TASKS_EXEC_DIR,
        )

    def predisponi_esecuzione(self, id_task):
        """
        Predisposizione comune per ogni lancio:
          1. Rigenera SEMPRE il .py (idempotente, ~10ms, evita file stantii).
          2. Imposta stato='ready' nella task corrente.
          3. Aggiorna riferimento al file.
        Ritorna ``(filepath, log_messages)`` per il popup di lancio.
        """
        d = self.dettagli.get_by_id(id_task)
        if d is None:
            return None, ["!! Task non trovata"]

        log = []
        azioni_eff, src_id = self.get_azioni_effettive(id_task)

        if src_id is not None and src_id != id_task:
            log.append(f">> Azioni ereditate dalla task padre [{src_id}] "
                       f"({len(azioni_eff)} azioni)")
            log.append(f">> Eredito file esecuzione dal padre [{src_id}]...")
            target_d = self.dettagli.get_by_id(src_id)
            if not target_d:
                log.append("!! Padre non trovato")
                self.esecuzione.imposta_stato(id_task, 'error')
                return None, log
        else:
            if azioni_eff:
                log.append(f">> Azioni proprie: {len(azioni_eff)}")
            else:
                log.append(">> Attenzione: nessuna azione registrata")
            target_d = d
            src_id = id_task

        target_e = self.esecuzione.get(src_id) or {}
        target_exec = target_e.get('esecuzione', {})

        if (target_e.get('codice_personalizzato', False)
                and target_exec.get('file')
                and os.path.exists(target_exec['file'])):
            log.append(">> Codice custom: preservo il file esistente OK")
            filepath = target_exec['file']
        else:
            log.append(">> Generazione file esecuzione...")
            filepath = self.crea_file_esecuzione(src_id)
            if filepath:
                log.append(f">> File pronto: {os.path.basename(filepath)} OK")
                self.esecuzione.imposta_file(src_id, filepath)
            else:
                log.append("!! Errore creazione file esecuzione")
                self.esecuzione.imposta_stato(id_task, 'error')
                return None, log

        # Aggiorna stato della task corrente (non del padre)
        self.esecuzione.imposta_file(id_task, filepath)
        self.esecuzione.imposta_stato(id_task, 'ready')
        log.append(f">> Stato impostato: ready OK")
        params = (self.esecuzione.get(id_task) or {}) \
                 .get('esecuzione', {}).get('params', {})
        log.append(f">> Params: {params}")
        return filepath, log

    def imposta_stato_esecuzione(self, id_task, stato, params=None):
        """Imposta stato esecuzione."""
        self.esecuzione.imposta_stato(id_task, stato, params=params)

    # ==================================================================
    # CONFRONTO CON RAM
    # ==================================================================

    def get_memory_tasks_info(self, memory_tasks):
        """
        Per ogni task in RAM, indica se e' registrata e ne fornisce i
        dettagli (struttura + esecuzione).
        """
        out = []
        for mt in memory_tasks:
            reg = self.find_registered(
                tipo=mt.get('tipo'), id_stanza=mt.get('id_stanza'),
            )
            out.append({**mt, 'registrata': reg is not None, 'reg_task': reg})
        return out
