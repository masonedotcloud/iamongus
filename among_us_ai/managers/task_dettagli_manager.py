"""
Gestione della STRUTTURA delle task registrate.

Si occupa solo dei "dettagli" della task (chi e' la task, dove sta sulla
mappa, di che tipo e', a chi e' figlia, quali fasi/alternativi ha):

    id, nome, x, y, tipo, id_stanza, lunghezza, vitale, due_giocatori,
    id_padre, cooldown, fasi[], alternativi[], id_zona, id_zona_locale,
    nome_zona

NON si occupa di:
- azioni registrate dall'editor
- file .py generato per l'esecuzione
- stato di esecuzione (idle/ready/running/done)
- codice custom

Questi sono di competenza di ``TaskEsecuzioneManager``.

Persistenza: file JSON unico ``tasks_dettagli.json`` con schema:

    {
      "task_list": [
        {"id": 1, "nome": "Swipe Card", "x": 5.91, "y": -8.53, ...},
        ...
      ]
    }

Il join con i dati di esecuzione avviene sull'``id``.
"""

import json
import os


# Campi che fanno parte della "struttura" e finiscono in tasks_dettagli.json
_STRUCT_FIELDS = (
    'id', 'nome', 'x', 'y',
    'tipo', 'id_stanza',
    'lunghezza', 'vitale', 'due_giocatori',
    'cooldown',
    'id_padre',
    'fasi', 'alternativi',
    'id_zona', 'id_zona_locale', 'nome_zona',
)


class TaskDettagliManager:
    """CRUD + persistenza dei dettagli strutturali delle task."""

    def __init__(self, file_path):
        """
        :param file_path: path del file JSON dettagli (es. ``tasks_dettagli.json``).
        """
        self.file_path  = file_path
        self.task_list  = []   # lista di dict "dettagli"
        self.prossimo_id = 1
        self.carica()

    # ------------------------------------------------------------------
    # Persistenza
    # ------------------------------------------------------------------

    def carica(self):
        """Carica la lista task dal JSON dettagli. Se assente, parte vuota."""
        if not os.path.exists(self.file_path):
            return
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.task_list = data.get('task_list', [])
            self.prossimo_id = max(
                (t['id'] for t in self.task_list), default=0
            ) + 1
            print(f"Dettagli task caricati: {len(self.task_list)}")
        except Exception as e:
            print(f"Errore caricamento dettagli task ({e}).")

    def salva(self):
        """Serializza l'intera ``task_list`` su disco (overwrite atomico)."""
        try:
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(
                    {'task_list': self.task_list},
                    f, indent=2, ensure_ascii=False,
                )
        except Exception as e:
            print(f"Errore salvataggio dettagli task ({e}).")

    # ------------------------------------------------------------------
    # CRUD principale
    # ------------------------------------------------------------------

    def aggiungi(self, nome, x, y,
                 fasi=None, alternativi=None,
                 id_stanza=None, tipo=None,
                 id_zona=None, id_zona_locale=None, nome_zona=None,
                 vitale=False, due_giocatori=False,
                 cooldown=0.0, lunghezza="N/A"):
        """
        Crea e salva i dettagli di una nuova task. Ritorna l'ID assegnato.
        Le azioni e i dati di esecuzione vanno gestiti separatamente
        tramite ``TaskEsecuzioneManager``.
        """
        task = {
            'id':            self.prossimo_id,
            'nome':          nome,
            'x':             float(x),
            'y':             float(y),
            'fasi':          fasi if fasi is not None else [],
            'alternativi':      alternativi if alternativi is not None else [],
            'tipo':          tipo,
            'id_stanza':       id_stanza,
            'id_zona':       id_zona,
            'id_zona_locale': id_zona_locale,
            'nome_zona':     nome_zona,
            'vitale':        bool(vitale),
            'due_giocatori': bool(due_giocatori),
            'cooldown':      float(cooldown),
            'lunghezza':     lunghezza,
            'id_padre':     None,
        }
        self.task_list.append(task)
        self.prossimo_id += 1
        self.salva()
        return task

    def aggiorna(self, id_task, nome, x, y,
                 vitale=None, due_giocatori=None,
                 cooldown=None, lunghezza=None,
                 delay_avvio=None,
                 loop_guard_retry=None):
        """
        Aggiorna i campi della task con id ``id_task``.
        Solo i parametri non-``None`` vengono modificati (update parziale).
        """
        for t in self.task_list:
            if t['id'] == id_task:
                t['nome'] = nome
                t['x'] = float(x)
                t['y'] = float(y)
                if vitale is not None:
                    t['vitale'] = bool(vitale)
                if due_giocatori is not None:
                    t['due_giocatori'] = bool(due_giocatori)
                if cooldown is not None:
                    t['cooldown'] = float(cooldown)
                if lunghezza is not None:
                    t['lunghezza'] = str(lunghezza)
                if delay_avvio is not None:
                    # Pausa iniziale (sec) prima di iniziare le azioni:
                    # 0 = parte subito, >0 = aspetta dopo apertura pannello.
                    # Utile per minigiochi con animazione di apertura lunga.
                    t['delay_avvio'] = max(0.0, float(delay_avvio))
                if loop_guard_retry is not None:
                    # Se True, quando il subprocess termina ma la task non
                    # risulta done in RAM, il bot tenta automaticamente
                    # fino a N retry (ESC + rilancia) prima di applicare
                    # il cooldown di sicurezza. Vedi LOOP_GUARD_* in config.
                    t['loop_guard_retry'] = bool(loop_guard_retry)
                break
        self.salva()

    def rimuovi(self, id_task):
        """Rimuove la task con l'id dato (no-op se non trovata)."""
        self.task_list = [t for t in self.task_list if t['id'] != id_task]
        self.salva()

    # ------------------------------------------------------------------
    # Parent / figli (gerarchia padre-figlia per task multi-fase)
    # ------------------------------------------------------------------

    def imposta_padre(self, id_task, id_padre):
        """
        Collega una task a un padre (oppure scollega con ``id_padre=None``).

        :return: ``True`` se ok, ``False`` se rifiutato per:
                 - self-loop (id_padre == id_task)
                 - padre inesistente
                 - catena di profondita' > 1 (nessun "nipote")
        """
        if id_padre is not None:
            if id_padre == id_task:
                return False
            padre = self.get_by_id(id_padre)
            if padre is None:
                return False
            # Niente catene padre -> figlia -> nipote: il padre non puo'
            # essere a sua volta figlia di un'altra task.
            if padre.get('id_padre') is not None:
                return False
        for t in self.task_list:
            if t['id'] == id_task:
                t['id_padre'] = id_padre
                break
        self.salva()
        return True

    def get_figli(self, id_task):
        """Ritorna la lista delle task figlie (id_padre == id_task)."""
        return [t for t in self.task_list if t.get('id_padre') == id_task]

    # ------------------------------------------------------------------
    # Fasi / alternativi
    # ------------------------------------------------------------------

    def aggiungi_fase(self, id_task, nome_fase, x, y):
        """
        Aggiunge una fase intermedia (waypoint) alla task.

        Una "fase" e' un punto della mappa dove il bot si ferma per
        eseguire un sotto-step prima della task vera (es. un button da
        premere lungo il percorso).

        NB: la flag ``ripeti`` NON e' un attributo della fase ma
        dell'azione ``cooldown`` che la chiude. Vedi `aggiorna_lista` in
        ``editor_mixins/list_panel.py`` per la UI di selezione.
        """
        for t in self.task_list:
            if t['id'] == id_task:
                t.setdefault('fasi', []).append({
                    'nome': nome_fase,
                    'x': float(x),
                    'y': float(y),
                })
                break
        self.salva()

    def rimuovi_fase(self, id_task, idx_fase):
        """Rimuove la fase all'indice ``idx_fase`` della task indicata."""
        for t in self.task_list:
            if t['id'] == id_task:
                fasi = t.get('fasi', [])
                if 0 <= idx_fase < len(fasi):
                    fasi.pop(idx_fase)
                break
        self.salva()

    def aggiungi_alternativo(self, id_task, x, y):
        """
        Aggiunge un punto alternativo alla task.

        Gli "alternativi" sono fallback: se l'arrivo alla pos principale
        fallisce (es. task non si apre), il bot prova questi punti.
        """
        for t in self.task_list:
            if t['id'] == id_task:
                t.setdefault('alternativi', []).append(
                    {'x': float(x), 'y': float(y)}
                )
                break
        self.salva()

    def rimuovi_alternativo(self, id_task, idx_alternativo):
        """Rimuove l'alternativo all'indice ``idx_alternativo``."""
        for t in self.task_list:
            if t['id'] == id_task:
                alternativi = t.get('alternativi', [])
                if 0 <= idx_alternativo < len(alternativi):
                    alternativi.pop(idx_alternativo)
                break
        self.salva()

    # ------------------------------------------------------------------
    # Zone link (mapping task -> id_stanza del gioco)
    # ------------------------------------------------------------------

    def imposta_collegamento_zona(self, id_task, game_zone_id):
        """
        Collega/scollega la task a una zona di gioco.

        :param game_zone_id: id_stanza letto dalla RAM, oppure ``None``
                             per scollegare.
        """
        for t in self.task_list:
            if t['id'] == id_task:
                if game_zone_id is None:
                    t.pop('id_zona', None)
                else:
                    t['id_zona'] = int(game_zone_id)
                break
        self.salva()

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_by_id(self, id_task):
        """Cerca una task per id. Ritorna il dict oppure ``None``."""
        for t in self.task_list:
            if t['id'] == id_task:
                return t
        return None

    def is_registered(self, task_nome):
        """``True`` se esiste una task con quel nome (case-insensitive)."""
        nome_lower = task_nome.lower()
        return any(t['nome'].lower() == nome_lower for t in self.task_list)

    def find_registered(self, tipo=None, id_stanza=None):
        """
        Cerca la task corrispondente incrociando ``tipo`` (Task Type ID)
        + ``id_stanza``: entrambi devono coincidere.

        :return: il dict task oppure ``None`` se non trovata o se uno
                 dei due parametri e' ``None``.
        """
        if tipo is None or id_stanza is None:
            return None
        for t in self.task_list:
            if t.get('tipo') == tipo and t.get('id_stanza') == id_stanza:
                return t
        return None
