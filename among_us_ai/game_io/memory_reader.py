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


# =============================================================================
# Lettore stato del gioco (in_game, voting, dead, impostor)
# =============================================================================

import os


class AmongUsGameStateReader:
    """
    Legge lo stato corrente del gioco di Among Us:
    - in_game        : True se siamo in partita (no menu, no lobby)
    - game_status    : 0=menu, 1=lobby, 2=partita online
    - is_voting      : True se siamo in fase di votazione/meeting
    - is_dead        : True se il giocatore e' morto/fantasma
    - is_impostor    : True se il giocatore e' impostore

    Offsets caricati dinamicamente da `script.json` (file con la mappa
    delle classi/indirizzi prodotto dal dumper). Se il file manca, il
    reader rimane inattivo e ritorna None.

    Architettura auto-rilevata (32/64 bit) dalla base address della DLL.
    """

    def __init__(self, script_json_path="script.json"):
        self.process_name = "Among Us.exe"
        self.module_name  = "GameAssembly.dll"
        self.pm = None
        self.game_assembly_base = None

        # Auto-rilevati dopo connect()
        self.is_64_bit    = False
        self.STATIC_FIELDS = 0x5C

        # Indirizzi delle classi (popolati da script.json)
        self.PLAYER_CONTROL_CLASS  = 0
        self.AMONG_US_CLIENT_CLASS = 0
        self.MEETING_HUD_CLASS     = 0

        # Offsets (verificati per la versione corrente; rivedere se Among
        # Us aggiorna la build)
        self.OFFSET_GAME_STATE   = 0x64
        self.OFFSET_LOCAL_PLAYER = 0x0
        self.OFFSET_PLAYER_DATA  = 0x58
        self.OFFSET_IS_DEAD      = 0x54
        self.OFFSET_ROLE         = 0x4C
        self.OFFSET_TEAM_TYPE    = 0x4C

        # Carico script.json
        self._json_path = script_json_path
        self._json_loaded = False
        self._load_classes_from_json()

    def _load_classes_from_json(self):
        """Legge gli indirizzi di classe da script.json (formato dumper)."""
        if not os.path.exists(self._json_path):
            print(f"[MemoryReader] script.json non trovato in "
                  f"'{self._json_path}'. Stato gioco disabilitato.",
                  flush=True)
            return
        try:
            with open(self._json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            metadata = data.get("ScriptMetadata", [])
            if not metadata and isinstance(data, list):
                metadata = data
            for entry in metadata:
                name = entry.get("Name", "")
                address = entry.get("Address", 0)
                if name in ("AmongUsClient__TypeInfo",
                              "AmongUsClient_TypeInfo"):
                    self.AMONG_US_CLIENT_CLASS = address
                elif name in ("MeetingHud__TypeInfo",
                                "MeetingHud_TypeInfo"):
                    self.MEETING_HUD_CLASS = address
                elif name in ("PlayerControl__TypeInfo",
                                "PlayerControl_TypeInfo"):
                    self.PLAYER_CONTROL_CLASS = address
            self._json_loaded = (
                self.AMONG_US_CLIENT_CLASS != 0
                and self.PLAYER_CONTROL_CLASS != 0
            )
            if self._json_loaded:
                print("[MemoryReader] script.json caricato OK", flush=True)
        except Exception as e:
            print(f"[MemoryReader] Errore lettura script.json: {e}",
                  flush=True)

    def connect(self):
        """Connette al processo del gioco. Auto-rileva 32/64 bit."""
        if not _PYMEM_OK:
            return False
        try:
            self.pm = pymem.Pymem(self.process_name)
            module = pymem.process.module_from_name(
                self.pm.process_handle, self.module_name)
            self.game_assembly_base = module.lpBaseOfDll
            # Auto-rilevamento architettura
            if self.game_assembly_base > 0xFFFFFFFF:
                self.is_64_bit = True
                self.STATIC_FIELDS = 0xB8
            else:
                self.is_64_bit = False
                self.STATIC_FIELDS = 0x5C
            return True
        except pymem.exception.ProcessNotFound:
            return False
        except Exception:
            return False

    def _read_ptr(self, address):
        """Legge un puntatore della dimensione corretta per l'arch."""
        try:
            if self.is_64_bit:
                return self.pm.read_ulonglong(address)
            return self.pm.read_uint(address)
        except Exception:
            return 0

    def get_game_state(self):
        """
        Ritorna lo stato corrente del gioco come dict.
        Ritorna None se non riesce a leggere (processo chiuso, json
        mancante, ecc).
        """
        if not self._json_loaded:
            return None
        if not self.pm or not self.game_assembly_base:
            if not self.connect():
                return None

        state = {
            "in_game":     False,
            "game_status": 0,     # 0=menu, 1=lobby, 2=partita
            "is_voting":   False,
            "is_dead":     False,
            "is_impostor": False,
        }

        try:
            # 1. STATO DEL GIOCO (menu / lobby / partita)
            client_addr = self._read_ptr(
                self.game_assembly_base + self.AMONG_US_CLIENT_CLASS)
            if client_addr:
                client_static = self._read_ptr(
                    client_addr + self.STATIC_FIELDS)
                if client_static:
                    client_inst = self._read_ptr(client_static + 0x0)
                    if client_inst:
                        state["game_status"] = self.pm.read_int(
                            client_inst + self.OFFSET_GAME_STATE)

            # Offset Unity per "oggetto distrutto?"
            native_offset = 0x10 if self.is_64_bit else 0x8

            # 2. PLAYER LOCALE (in_game / is_dead / is_impostor)
            pc_addr = self._read_ptr(
                self.game_assembly_base + self.PLAYER_CONTROL_CLASS)
            if pc_addr:
                pc_static = self._read_ptr(pc_addr + self.STATIC_FIELDS)
                if pc_static:
                    local_player = self._read_ptr(
                        pc_static + self.OFFSET_LOCAL_PLAYER)
                    if local_player:
                        # Trucco Unity: oggetto ancora "vivo" nel motore?
                        player_native = self._read_ptr(
                            local_player + native_offset)
                        if player_native:
                            state["in_game"] = True
                            player_data = self._read_ptr(
                                local_player + self.OFFSET_PLAYER_DATA)
                            if player_data:
                                state["is_dead"] = bool(
                                    self.pm.read_bool(
                                        player_data + self.OFFSET_IS_DEAD))
                                role_addr = self._read_ptr(
                                    player_data + self.OFFSET_ROLE)
                                if role_addr:
                                    team = self.pm.read_int(
                                        role_addr + self.OFFSET_TEAM_TYPE)
                                    state["is_impostor"] = (team == 1)

            # 3. VOTAZIONE in corso
            if state["in_game"]:
                meeting_addr = self._read_ptr(
                    self.game_assembly_base + self.MEETING_HUD_CLASS)
                if meeting_addr:
                    meeting_static = self._read_ptr(
                        meeting_addr + self.STATIC_FIELDS)
                    if meeting_static:
                        meeting_inst = self._read_ptr(meeting_static + 0x0)
                        if meeting_inst:
                            meeting_native = self._read_ptr(
                                meeting_inst + native_offset)
                            if meeting_native:
                                state["is_voting"] = True

            return state
        except Exception:
            # Connessione persa: forza reconnect al prossimo tentativo
            self.pm = None
            self.game_assembly_base = None
            return None
