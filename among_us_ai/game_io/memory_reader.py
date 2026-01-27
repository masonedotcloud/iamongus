"""
Lettura della memoria di gioco di Among Us tramite `pymem`.

Due classi separate per posizione del giocatore e task in corso:
- `AmongUsMemoryReader`  -> coordinate (x, y) del player locale
- `AmongUsTaskReader`    -> lista delle task assegnate al player locale

Tutti gli offset sono per la versione di Among Us su cui e' stato sviluppato
questo bot e provengono dagli script `task_lista.py` / `find_task_memoria.py`.
Se Among Us aggiorna la build, gli offset vanno rivisti qui.
"""

import json

try:
    import pymem
    import pymem.process
    _PYMEM_OK = True
except ImportError:
    _PYMEM_OK = False


# =============================================================================
# Lettore posizione player
# =============================================================================

class AmongUsMemoryReader:
    """Legge la posizione (x, y) del giocatore locale dalla RAM."""

    def __init__(self):
        """Inizializza l'istanza con i valori di default."""
        self.process_name = "Among Us.exe"
        self.module_name  = "GameAssembly.dll"
        self.pm = None
        self.game_assembly_base = None

        self.PLAYER_CONTROL_CLASS = 43780124
        self.STATIC_FIELDS        = 0x5C
        self.OFFSET_LOCAL_PLAYER  = 0x0
        self.OFFSET_NET_TRANSFORM = 0x98
        self.OFFSET_X             = 0x4C
        self.OFFSET_Y             = 0x50

    def connect(self):
        """Stabilisce la connessione al processo del gioco."""
        if not _PYMEM_OK:
            return False
        try:
            self.pm = pymem.Pymem(self.process_name)
            self.game_assembly_base = pymem.process.module_from_name(
                self.pm.process_handle, self.module_name
            ).lpBaseOfDll
            return True
        except pymem.exception.ProcessNotFound:
            return False

    def get_position(self):
        """Ritorna position."""
        if not self.pm or not self.game_assembly_base:
            if not self.connect():
                # Goal irraggiungibile o limite nodi superato
                return None
        try:
            player_control_class_addr = self.pm.read_int(
                self.game_assembly_base + self.PLAYER_CONTROL_CLASS)
            if player_control_class_addr == 0:
                # Goal irraggiungibile o limite nodi superato
                return None
            static_fields_ptr = self.pm.read_int(
                player_control_class_addr + self.STATIC_FIELDS)
            if static_fields_ptr == 0:
                # Goal irraggiungibile o limite nodi superato
                return None
            local_player_addr = self.pm.read_int(
                static_fields_ptr + self.OFFSET_LOCAL_PLAYER)
            if local_player_addr == 0:
                # Goal irraggiungibile o limite nodi superato
                return None
            net_transform_addr = self.pm.read_int(
                local_player_addr + self.OFFSET_NET_TRANSFORM)
            if net_transform_addr == 0:
                # Goal irraggiungibile o limite nodi superato
                return None
            pos_x = self.pm.read_float(net_transform_addr + self.OFFSET_X)
            pos_y = self.pm.read_float(net_transform_addr + self.OFFSET_Y)
            return (pos_x, pos_y)
        except pymem.exception.MemoryReadError:
            # Goal irraggiungibile o limite nodi superato
            return None
        except Exception:
            # Goal irraggiungibile o limite nodi superato
            return None


# =============================================================================
# Lettore task assegnate al player locale
# =============================================================================

class AmongUsTaskReader:
    """
    Legge le task del giocatore locale direttamente dalla RAM di Among Us.

    Offset da task_lista.py + find_task_memoria.py.
    """

    PROCESS_NAME  = "Among Us.exe"
    MODULE_NAME   = "GameAssembly.dll"

    PLAYER_CONTROL_CLASS = 43780124
    STATIC_FIELDS        = 0x5C
    OFFSET_LOCAL_PLAYER  = 0x0
    OFFSET_MY_TASKS      = 0xAC
    OFFSET_NET_TRANSFORM = 0x98
    OFFSET_X             = 0x4C
    OFFSET_Y             = 0x50
    # Offset task
    OFFSET_ID            = 0x14
    OFFSET_ROOM_ID       = 0x1C   # ID stanza/zona del gioco
    OFFSET_TYPE          = 0x20   # tipo task
    OFFSET_STEP          = 0x30
    OFFSET_MAX_STEP      = 0x34

    def __init__(self, tasks_json_path="tasks.json"):
        """Inizializza l'istanza con i valori di default."""
        self.pm                 = None
        self.game_assembly_base = None
        self.skeld_tasks        = self._load_tasks_def(tasks_json_path)
        self._connected         = False

    def _load_tasks_def(self, path):
        """Carica le definizioni delle task da tasks.json."""
        try:
            with open(path, 'r') as f:
                # Carica e deserializza JSON da file
                raw = json.load(f)
            return {int(k): v for k, v in raw.items()}
        except Exception:
            return {}

    def _connect(self):
        """Stabilisce la connessione al processo del gioco."""
        if not _PYMEM_OK:
            return False
        try:
            self.pm = pymem.Pymem(self.PROCESS_NAME)
            self.game_assembly_base = pymem.process.module_from_name(
                self.pm.process_handle, self.MODULE_NAME).lpBaseOfDll
            self._connected = True
            return True
        except Exception:
            self.pm         = None
            self._connected = False
            return False

    def get_tasks(self):
        """
        Ritorna lista di dict task con i campi grezzi dalla RAM.
        Usa 'tipo' (Task Type ID) come vero identificatore univoco.
        """
        if not _PYMEM_OK:
            # Goal irraggiungibile o limite nodi superato
            return None
        if not self.pm:
            if not self._connect():
                # Goal irraggiungibile o limite nodi superato
                return None
        try:
            base_ptr      = self.pm.read_uint(self.game_assembly_base + self.PLAYER_CONTROL_CLASS)
            static_fields = self.pm.read_uint(base_ptr + self.STATIC_FIELDS)
            player        = self.pm.read_uint(static_fields + self.OFFSET_LOCAL_PLAYER)
            if player == 0:
                # Goal irraggiungibile o limite nodi superato
                return None

            m_ptr = self.pm.read_uint(player + self.OFFSET_MY_TASKS)
            if m_ptr == 0:
                return []

            items = self.pm.read_uint(m_ptr + 0x08)
            count = self.pm.read_int(m_ptr + 0x0C)
            tasks = []
            for i in range(min(count, 25)):
                t_ptr = self.pm.read_uint(items + 0x10 + (i * 4))
                if t_ptr == 0:
                    continue

                tipo    = self.pm.read_int(t_ptr + self.OFFSET_TYPE)
                id_stanza = self.pm.read_int(t_ptr + self.OFFSET_ROOM_ID)
                step    = self.pm.read_int(t_ptr + self.OFFSET_STEP)
                mstep   = self.pm.read_int(t_ptr + self.OFFSET_MAX_STEP)

                # Info se presenti, altrimenti nome generico basato sul TIPO
                info = self.skeld_tasks.get(
                    tipo,
                    {"n": f"Task Type {tipo}", "l": "-", "v": False},
                )

                tasks.append({
                    "nome":    info["n"],
                    "lung":    info["l"],
                    "vis":     "SI" if info["v"] else "NO",
                    "prog":    f"{step}/{mstep}",
                    "done":    (step >= mstep) if mstep > 0 else False,
                    "tipo":    tipo,      # Task Type ID (univoco per tipologia)
                    "id_stanza": id_stanza,
                })
            return tasks
        except Exception:
            self.pm         = None
            self._connected = False
            # Goal irraggiungibile o limite nodi superato
            return None
