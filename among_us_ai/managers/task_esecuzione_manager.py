"""
Gestione dell'ESECUZIONE delle task: azioni registrate + stato + file .py.

Si occupa solo dei dati che servono per *eseguire* una task:

    azioni[]            sequenza di click/drag/zone registrati dall'editor
    esecuzione.file     path del file .py generato in tasks_exec/
    esecuzione.stato    idle | ready | running | done | error
    esecuzione.params   parametri custom passati al runtime
    codice_personalizzato       True = file .py editato a mano, non sovrascrivere

NON si occupa di:
- nome / posizione / tipo / id_stanza / id_padre / fasi / alternativi (vedi
  ``TaskDettagliManager``).
- Il join con la task "padre" (id_padre) per ereditare le azioni viene
  fatto dal facade ``TaskManager``, perche' richiede di leggere il
  id_padre che vive nel manager dei dettagli.

Persistenza: UN FILE JSON PER TASK in ``tasks_esecuzione/task_<id>.json``.
Schema di ogni file:

    {
      "id": 1,
      "azioni": [...],
      "codice_personalizzato": false,
      "esecuzione": {
        "file":   "tasks_exec/task_001_Swipe_Card.py",
        "stato":  "idle",
        "params": {}
      }
    }

Vantaggi del file-per-task:
- Modifiche concorrenti / merge git puliti (una task non rovina le altre).
- Eliminare una task = cancellare il suo file (atomico).
- Le azioni sono spesso lunghe (decine di poly[]): JSON piu' piccolo
  da leggere e scrivere quando si modifica una sola task.
"""

import json
import os


_DEFAULT_ESECUZIONE = {
    'file':   None,
    'stato':  'idle',
    'params': {},
}


class TaskEsecuzioneManager:
    """CRUD + persistenza dei dati di esecuzione, un file JSON per task."""

    def __init__(self, dir_path):
        """Inizializza l'istanza con i valori di default."""
        self.dir_path = dir_path
        # Cache in-memory: {id_task: dict_esecuzione}. Caricata lazy.
        self._cache = {}
        # Crea la directory (e i parent) se non esiste
        os.makedirs(self.dir_path, exist_ok=True)
        self._carica_tutto()

    # ------------------------------------------------------------------
    # Persistenza
    # ------------------------------------------------------------------

    def _path_for(self, id_task):
        """Ritorna il path del file .json di esecuzione per la task data."""
        return os.path.join(self.dir_path, f"task_{int(id_task):03d}.json")

    def _carica_tutto(self):
        """All'avvio carica tutti i file in cache (sono pochi/piccoli)."""
        if not os.path.isdir(self.dir_path):
            return
        n = 0
        for fn in os.listdir(self.dir_path):
            if not fn.startswith('task_') or not fn.endswith('.json'):
                continue
            try:
                with open(os.path.join(self.dir_path, fn),
                          'r', encoding='utf-8') as f:
                    # Carica e deserializza JSON da file
                    data = json.load(f)
                tid = int(data.get('id', 0))
                if tid > 0:
                    self._cache[tid] = data
                    n += 1
            except Exception as e:
                print(f"Errore caricamento {fn}: {e}")
        print(f"Esecuzione task caricata: {n} file")

    def _salva(self, id_task):
        """Salva su file."""
        data = self._cache.get(id_task)
        if data is None:
            return
        try:
            with open(self._path_for(id_task), 'w', encoding='utf-8') as f:
                # Serializza su file in formato JSON
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Errore salvataggio esecuzione task {id_task}: {e}")

    def _ensure(self, id_task):
        """Crea la entry vuota in cache se non esiste."""
        if id_task not in self._cache:
            self._cache[id_task] = {
                'id':            int(id_task),
                'azioni':        [],
                'codice_personalizzato': False,
                'esecuzione':    dict(_DEFAULT_ESECUZIONE),
            }
        return self._cache[id_task]

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def crea_per(self, id_task, azioni=None, codice_personalizzato=False):
        """Crea il file di esecuzione per una task appena registrata."""
        e = self._ensure(id_task)
        e['azioni'] = list(azioni) if azioni else []
        e['codice_personalizzato'] = bool(codice_personalizzato)
        self._salva(id_task)

    def rimuovi(self, id_task):
        """Cancella i dati di esecuzione e il file su disco."""
        self._cache.pop(id_task, None)
        try:
            p = self._path_for(id_task)
            if os.path.exists(p):
                # Cancella il file dal disco
                os.remove(p)
        except Exception as e:
            print(f"Errore rimozione esecuzione task {id_task}: {e}")

    def get(self, id_task):
        """Ritorna il dict completo di esecuzione, o None se assente."""
        return self._cache.get(id_task)

    # ------------------------------------------------------------------
    # Azioni
    # ------------------------------------------------------------------

    def get_azioni(self, id_task):
        """Lista di azioni proprie della task (senza considerare il parent)."""
        e = self._cache.get(id_task)
        return list(e['azioni']) if e else []

    def imposta_azioni(self, id_task, azioni):
        """
        Sostituisce la lista delle azioni e invalida il file .py associato
        (perche' il vecchio file di certo non riflette piu' le azioni nuove).
        """
        e = self._ensure(id_task)
        e['azioni'] = list(azioni)
        if not e.get('codice_personalizzato', False):
            e['esecuzione']['file']  = None
            e['esecuzione']['stato'] = 'idle'
        self._salva(id_task)

    # ------------------------------------------------------------------
    # File .py associato
    # ------------------------------------------------------------------

    def imposta_file(self, id_task, filepath):
        """Aggiorna il path del file .py generato."""
        e = self._ensure(id_task)
        e['esecuzione']['file'] = filepath
        self._salva(id_task)

    def invalida_file(self, id_task):
        """Marca il file come stantio (senza cancellarlo dal disco)."""
        e = self._cache.get(id_task)
        if e is None:
            return
        if e.get('codice_personalizzato', False):
            return  # i file custom non vanno mai invalidati
        e['esecuzione']['file']  = None
        e['esecuzione']['stato'] = 'idle'
        self._salva(id_task)

    # ------------------------------------------------------------------
    # Stato
    # ------------------------------------------------------------------

    def imposta_stato(self, id_task, stato, params=None):
        """Aggiorna stato di esecuzione e opzionalmente i params."""
        e = self._ensure(id_task)
        e['esecuzione']['stato'] = stato
        if params is not None:
            e['esecuzione']['params'] = params
        self._salva(id_task)

    def get_stato(self, id_task):
        """Ritorna stato."""
        e = self._cache.get(id_task)
        if e is None:
            return 'idle'
        return e.get('esecuzione', {}).get('stato', 'idle')

    # ------------------------------------------------------------------
    # Codice custom
    # ------------------------------------------------------------------

    def set_codice_personalizzato(self, id_task, valore):
        """Imposta il flag di codice personalizzato per una task."""
        e = self._ensure(id_task)
        e['codice_personalizzato'] = bool(valore)
        self._salva(id_task)

    def is_codice_personalizzato(self, id_task):
        """Ritorna se codice personalizzato."""
        e = self._cache.get(id_task)
        return bool(e and e.get('codice_personalizzato', False))
