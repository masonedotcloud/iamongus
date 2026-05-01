"""
Lettura della memoria di gioco di Among Us tramite ``pymem``.

Tre classi separate, una per ogni "tipologia" di dato letto:

- :class:`AmongUsMemoryReader`    -> posizione ``(x, y)`` del giocatore locale.
- :class:`AmongUsTaskReader`      -> lista task assegnate al giocatore locale
                                     (tipo, id_stanza, step corrente, done).
- :class:`AmongUsGameStateReader` -> stato di alto livello (in_game, voting,
                                     is_dead, is_impostor, game_status).

Tutti gli offset sono SPECIFICI della versione di Among Us su cui e' stato
sviluppato questo bot. Provengono dagli script ``task_lista.py`` e
``find_task_memoria.py`` (Il2Cpp dump). Se Among Us aggiorna la build, gli
offset vanno ridumpati e aggiornati qui.
"""

import json
import os

# Pymem e' opzionale: senza, il bot non puo' leggere RAM ma resta avviabile
# (la dashboard funziona per visualizzazione/registrazione task, e l'utente
# vede subito che la connessione al gioco fallisce).
try:
    import pymem
    import pymem.process
    _PYMEM_OK = True
except ImportError:
    _PYMEM_OK = False


# ============================================================================
# Lettore posizione del player locale
# ============================================================================

class AmongUsMemoryReader:
    """Legge la posizione ``(x, y)`` del giocatore locale dalla RAM."""

    def __init__(self):
        self.process_name = "Among Us.exe"
        self.module_name  = "GameAssembly.dll"
        self.pm = None                  # istanza pymem.Pymem (None se non connesso)
        self.game_assembly_base = None  # base address della DLL Il2Cpp

        # --- Offset per la build corrente di Among Us ---
        # PLAYER_CONTROL_CLASS: offset dell'oggetto PlayerControl
        #                       (typeinfo singleton) relativo alla base DLL.
        # Catena di dereferenze per arrivare a posizione:
        #   base + PLAYER_CONTROL_CLASS -> ptr alla classe statica
        #   classe + STATIC_FIELDS      -> ptr ai campi statici
        #   campi + OFFSET_LOCAL_PLAYER -> ptr al PlayerControl locale
        #   player + OFFSET_NET_TRANSFORM -> ptr al CustomNetTransform
        #   transform + OFFSET_X/Y      -> due float32 con posizione
        self.PLAYER_CONTROL_CLASS = 43780124
        self.STATIC_FIELDS        = 0x5C
        self.OFFSET_LOCAL_PLAYER  = 0x0
        self.OFFSET_NET_TRANSFORM = 0x98
        self.OFFSET_X             = 0x4C
        self.OFFSET_Y             = 0x50

    def connect(self):
        """Apre la connessione al processo di Among Us. ``True`` se OK."""
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
        """
        Ritorna ``(x, y)`` del player locale in coordinate di gioco, oppure
        ``None`` se non riesce a leggere (processo chiuso, scena non pronta,
        ecc.). Riconnessione automatica al primo accesso.
        """
        if not self.pm or not self.game_assembly_base:
            if not self.connect():
                return None
        try:
            # Catena di dereferenze: vedere commento offset in __init__.
            # Ogni step legge un puntatore (read_int = 32-bit); se 0
            # significa che lo stato non e' ancora pronto in RAM
            # (es. siamo nella lobby, transizione di scena, ecc.).
            player_control_class_addr = self.pm.read_int(
                self.game_assembly_base + self.PLAYER_CONTROL_CLASS)
            if player_control_class_addr == 0:
                return None
            static_fields_ptr = self.pm.read_int(
                player_control_class_addr + self.STATIC_FIELDS)
            if static_fields_ptr == 0:
                return None
            local_player_addr = self.pm.read_int(
                static_fields_ptr + self.OFFSET_LOCAL_PLAYER)
            if local_player_addr == 0:
                return None
            net_transform_addr = self.pm.read_int(
                local_player_addr + self.OFFSET_NET_TRANSFORM)
            if net_transform_addr == 0:
                return None
            pos_x = self.pm.read_float(net_transform_addr + self.OFFSET_X)
            pos_y = self.pm.read_float(net_transform_addr + self.OFFSET_Y)
            return (pos_x, pos_y)
        except pymem.exception.MemoryReadError:
            # Accesso a regione di memoria non piu' valida (processo morto?).
            return None
        except Exception:
            # Catch-all: qualunque altro errore non deve interrompere il loop
            # di lettura, ritorniamo None e il chiamante ritenta al prossimo tick.
            return None


# ============================================================================
# Lettore task assegnate al player locale
# ============================================================================

class AmongUsTaskReader:
    """
    Legge la lista delle task del giocatore locale dalla RAM di Among Us.

    Per ogni task ritorna un dict con: ``id`` (univoco di istanza),
    ``id_stanza`` (= room id del gioco), ``tipo`` (Task Type ID),
    ``step`` corrente, ``max_step``, ``prog`` (stringa "N/M"), ``done``.

    Gli offset sono derivati da ``task_lista.py`` + ``find_task_memoria.py``.
    """

    PROCESS_NAME  = "Among Us.exe"
    MODULE_NAME   = "GameAssembly.dll"

    # Catena per arrivare alla lista task del player locale (analoga a
    # AmongUsMemoryReader ma con OFFSET_MY_TASKS al posto di NET_TRANSFORM).
    PLAYER_CONTROL_CLASS = 43780124
    STATIC_FIELDS        = 0x5C
    OFFSET_LOCAL_PLAYER  = 0x0
    OFFSET_MY_TASKS      = 0xAC       # ptr al List<PlayerTask> nel PlayerControl
    OFFSET_NET_TRANSFORM = 0x98
    OFFSET_X             = 0x4C
    OFFSET_Y             = 0x50
    # Offset interni a ciascun oggetto PlayerTask
    OFFSET_ID            = 0x14
    OFFSET_ROOM_ID       = 0x1C       # ID stanza/zona del gioco (room)
    OFFSET_TYPE          = 0x20       # Task Type ID (identificatore "categoria")
    OFFSET_STEP          = 0x30       # step corrente (0..MAX_STEP)
    OFFSET_MAX_STEP      = 0x34       # numero di step richiesti

    def __init__(self, tasks_json_path="tasks.json"):
        self.pm                 = None
        self.game_assembly_base = None
        # Definizioni delle task (Task Type ID -> {nome, lunghezza, ...}),
        # caricate da tasks.json. Usate per arricchire i dati grezzi.
        self.skeld_tasks        = self._load_tasks_def(tasks_json_path)
        self._connected         = False

    def _load_tasks_def(self, path):
        """Carica e deserializza ``tasks.json`` (mappa Task Type ID -> metadati)."""
        try:
            with open(path, 'r') as f:
                raw = json.load(f)
            # JSON ha chiavi stringa: converto a int per matching diretto.
            return {int(k): v for k, v in raw.items()}
        except Exception:
            # File mancante o malformato: nessuna definizione disponibile.
            # I dati grezzi sono ancora leggibili dalla RAM (solo senza nome).
            return {}

    def _connect(self):
        """Apre la connessione al processo di Among Us. ``True`` se OK."""
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
        Restituisce la lista delle task assegnate al player locale.

        :return: ``list[dict]`` con campi (id_stanza, tipo, step, max_step,
                 prog, done, nome, lung, vis) oppure ``None`` se non riesce
                 a leggere (processo morto, scena non pronta).
        """
        if not _PYMEM_OK:
            return None
        if not self.pm:
            if not self._connect():
                return None
        try:
            # Catena di dereferenze per arrivare al PlayerControl locale.
            # Equivalente a AmongUsMemoryReader.get_position() ma con
            # OFFSET_MY_TASKS al posto di NET_TRANSFORM.
            base_ptr      = self.pm.read_uint(self.game_assembly_base + self.PLAYER_CONTROL_CLASS)
            static_fields = self.pm.read_uint(base_ptr + self.STATIC_FIELDS)
            player        = self.pm.read_uint(static_fields + self.OFFSET_LOCAL_PLAYER)
            if player == 0:
                return None  # scena non pronta (lobby, transizione)

            # m_ptr punta al `List<PlayerTask>` C#. Layout interno:
            #   m_ptr + 0x00: header
            #   m_ptr + 0x08: items[]  (array degli oggetti task)
            #   m_ptr + 0x0C: count    (lunghezza valida)
            m_ptr = self.pm.read_uint(player + self.OFFSET_MY_TASKS)
            if m_ptr == 0:
                return []  # nessuna task assegnata ancora

            items = self.pm.read_uint(m_ptr + 0x08)
            count = self.pm.read_int(m_ptr + 0x0C)
            tasks = []

            # Loop sulla lista (cap a 25 per safety: una partita normale
            # ha 8-15 task, 25 e' ampiamente sopra il massimo realistico).
            for i in range(min(count, 25)):
                # items[i] = puntatore al task object (32-bit per ogni slot).
                # Header dell'array a +0x10, poi 4 byte per puntatore.
                t_ptr = self.pm.read_uint(items + 0x10 + (i * 4))
                if t_ptr == 0:
                    continue  # slot vuoto (raro ma puo' capitare)

                tipo      = self.pm.read_int(t_ptr + self.OFFSET_TYPE)
                id_stanza = self.pm.read_int(t_ptr + self.OFFSET_ROOM_ID)
                step      = self.pm.read_int(t_ptr + self.OFFSET_STEP)
                mstep     = self.pm.read_int(t_ptr + self.OFFSET_MAX_STEP)

                # Arricchimento dal tasks.json: se il tipo e' noto, prendo
                # nome/lunghezza/vitale; altrimenti placeholder generico.
                info = self.skeld_tasks.get(
                    tipo,
                    {"n": f"Task Type {tipo}", "l": "-", "v": False},
                )

                tasks.append({
                    "nome":      info["n"],
                    "lung":      info["l"],
                    "vis":       "SI" if info["v"] else "NO",
                    "prog":      f"{step}/{mstep}",
                    "done":      (step >= mstep) if mstep > 0 else False,
                    "tipo":      tipo,        # Task Type ID (univoco per tipologia)
                    "id_stanza": id_stanza,
                })
            return tasks
        except Exception:
            # Lettura fallita: invalido la connessione cosi' al prossimo
            # tick si ri-tenta il connect (es. dopo restart di Among Us).
            self.pm         = None
            self._connected = False
            return None


# =============================================================================
# Lettore stato del gioco (in_game, voting, dead, impostor)
# =============================================================================

# ----------------------------------------------------------------------------
# INDIRIZZI DELLE CLASSI (offset rispetto a GameAssembly.dll)
# ----------------------------------------------------------------------------
# Specifici della versione di Among Us in uso. Se Among Us aggiorna la build,
# questi 3 valori vanno ridumpati (es. con IDA o un dumper Il2Cpp) e
# aggiornati qui.
#
# Valori estratti da script.json dell'utente (build corrente).
# Per trovarli con un dumper Il2Cpp i nomi sono:
#   - AmongUsClient_TypeInfo  (o AmongUsClient__TypeInfo)
#   - MeetingHud_TypeInfo     (o MeetingHud__TypeInfo)
#   - PlayerControl_TypeInfo  (o PlayerControl__TypeInfo)
#
# Lasciali a 0 per disabilitare il reader (il bot ignorera' la lettura
# dello stato del gioco e si comportera' come prima).
GAME_STATE_AMONG_US_CLIENT_CLASS = 0x29AB228
GAME_STATE_MEETING_HUD_CLASS     = 0x29ACA80
GAME_STATE_PLAYER_CONTROL_CLASS  = 0x29C081C

# ----------------------------------------------------------------------------
# OFFSETS INTERNI DELLE CLASSI (rispetto agli indirizzi sopra)
# ----------------------------------------------------------------------------
# Questi sono generalmente piu' stabili tra le versioni di Among Us.
GAME_STATE_OFFSET_GAME_STATE   = 0x64
GAME_STATE_OFFSET_LOCAL_PLAYER = 0x0
GAME_STATE_OFFSET_PLAYER_DATA  = 0x58
GAME_STATE_OFFSET_IS_DEAD      = 0x54
GAME_STATE_OFFSET_ROLE         = 0x4C
GAME_STATE_OFFSET_TEAM_TYPE    = 0x4C


class AmongUsGameStateReader:
    """
    Legge lo stato di alto livello del gioco di Among Us.

    Campi nel dict ritornato da :meth:`get_game_state`:

    - ``in_game``     : ``True`` se siamo dentro una partita (no menu/lobby)
    - ``game_status`` : 0=menu, 1=lobby, 2=partita online
    - ``is_voting``   : ``True`` se siamo in fase di votazione/meeting
    - ``is_dead``     : ``True`` se il giocatore e' morto/fantasma
    - ``is_impostor`` : ``True`` se il giocatore e' impostore

    Indirizzi delle classi: hardcoded nelle costanti ``GAME_STATE_*_CLASS``
    in cima al file (build-specific). Per override a runtime, passarli al
    costruttore.

    Architettura (32/64 bit) auto-rilevata dalla base address della DLL al
    primo :meth:`connect`. Il layout dei campi statici e la dimensione dei
    puntatori cambiano: vedere :attr:`STATIC_FIELDS` e :meth:`_read_ptr`.
    """

    def __init__(self,
                 among_us_client_class=None,
                 meeting_hud_class=None,
                 player_control_class=None):
        """
        :param among_us_client_class:  override per ``GAME_STATE_AMONG_US_CLIENT_CLASS``
        :param meeting_hud_class:      override per ``GAME_STATE_MEETING_HUD_CLASS``
        :param player_control_class:   override per ``GAME_STATE_PLAYER_CONTROL_CLASS``

        Se almeno uno dei tre indirizzi richiesti (AmongUsClient e PlayerControl)
        e' 0, il reader resta "non configurato": :meth:`get_game_state` ritorna
        sempre ``None`` e :attr:`_is_configured` e' ``False``.
        """
        self.process_name = "Among Us.exe"
        self.module_name  = "GameAssembly.dll"
        self.pm = None
        self.game_assembly_base = None

        # Auto-rilevati dopo connect() (32/64 bit cambiano i layout):
        # - is_64_bit:    True se base DLL > 4 GB
        # - STATIC_FIELDS: offset dei campi statici dentro un TypeInfo
        self.is_64_bit    = False
        self.STATIC_FIELDS = 0x5C

        # Indirizzi delle classi: priorita' (1) override costruttore,
        # (2) JSON dump (dati_memoria/script.json), (3) costanti hardcoded.
        # Il JSON e' piu' robusto: se il gioco si aggiorna e gli indirizzi
        # cambiano, basta rigenerare il dump senza toccare il codice.
        self.AMONG_US_CLIENT_CLASS = GAME_STATE_AMONG_US_CLIENT_CLASS
        self.MEETING_HUD_CLASS     = GAME_STATE_MEETING_HUD_CLASS
        self.PLAYER_CONTROL_CLASS  = GAME_STATE_PLAYER_CONTROL_CLASS

        # (2) Prova a caricare dal JSON: sovrascrive le costanti se trova
        # le voci. Non fatale se il file manca.
        self._carica_classi_da_json()

        # (1) Override espliciti del costruttore: massima priorita'.
        if among_us_client_class is not None:
            self.AMONG_US_CLIENT_CLASS = among_us_client_class
        if meeting_hud_class is not None:
            self.MEETING_HUD_CLASS = meeting_hud_class
        if player_control_class is not None:
            self.PLAYER_CONTROL_CLASS = player_control_class

        # Offsets interni delle classi (alias agli equivalenti globali).
        self.OFFSET_GAME_STATE   = GAME_STATE_OFFSET_GAME_STATE
        self.OFFSET_LOCAL_PLAYER = GAME_STATE_OFFSET_LOCAL_PLAYER
        self.OFFSET_PLAYER_DATA  = GAME_STATE_OFFSET_PLAYER_DATA
        self.OFFSET_IS_DEAD      = GAME_STATE_OFFSET_IS_DEAD
        self.OFFSET_ROLE         = GAME_STATE_OFFSET_ROLE
        self.OFFSET_TEAM_TYPE    = GAME_STATE_OFFSET_TEAM_TYPE

        # Reader e' "valido" solo se almeno AmongUsClient e PlayerControl
        # sono configurati (MeetingHud puo' anche essere 0: serve solo per
        # rilevare la votazione, gli altri valori restano corretti).
        self._is_configured = (
            self.AMONG_US_CLIENT_CLASS != 0
            and self.PLAYER_CONTROL_CLASS != 0
        )
        if self._is_configured:
            print("[GameStateReader] Indirizzi classi configurati OK",
                  flush=True)
        else:
            print("[GameStateReader] Indirizzi classi non configurati. "
                  "Modifica le costanti GAME_STATE_*_CLASS in "
                  "memory_reader.py oppure passa gli indirizzi al "
                  "costruttore. Stato gioco disabilitato.",
                  flush=True)

    def _carica_classi_da_json(self):
        """
        Prova a caricare gli indirizzi delle classi dal dump IL2CPP
        ``script.json`` (campo ``ScriptMetadata``). Se trova le voci,
        sovrascrive le costanti hardcoded; e' robusto agli aggiornamenti
        del gioco (basta rigenerare il dump).

        Cerca il file in piu' posizioni note, in ordine:
          1. ``dati_memoria/script.json`` (relativo alla cwd del bot)
          2. ``../dati_memoria/script.json`` (compat. col layout originale)
          3. ``<package>/../dati_memoria/script.json`` (relativo al codice)

        Se nessun file e' presente, non fa nulla (restano le costanti).
        """
        candidati = [
            os.path.join("dati_memoria", "script.json"),
            os.path.join("..", "dati_memoria", "script.json"),
            os.path.join(os.path.dirname(__file__), "..", "..",
                         "dati_memoria", "script.json"),
        ]
        path = next((p for p in candidati if os.path.exists(p)), None)
        if path is None:
            # Nessun JSON: si usano le costanti hardcoded (silenzioso).
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Il dump puo' essere {"ScriptMetadata": [...]} o direttamente
            # una lista di voci.
            metadata = data.get("ScriptMetadata", []) if isinstance(data, dict) else data
            trovati = 0
            for entry in metadata:
                name = entry.get("Name", "")
                address = entry.get("Address", 0)
                if name in ("AmongUsClient__TypeInfo", "AmongUsClient_TypeInfo"):
                    self.AMONG_US_CLIENT_CLASS = address
                    trovati += 1
                elif name in ("MeetingHud__TypeInfo", "MeetingHud_TypeInfo"):
                    self.MEETING_HUD_CLASS = address
                    trovati += 1
                elif name in ("PlayerControl__TypeInfo", "PlayerControl_TypeInfo"):
                    self.PLAYER_CONTROL_CLASS = address
                    trovati += 1
            print(f"[GameStateReader] Indirizzi caricati da {path} "
                  f"({trovati} classi).", flush=True)
        except Exception as e:
            print(f"[GameStateReader] Errore lettura {path}: {e}. "
                  "Uso le costanti hardcoded.", flush=True)

    def connect(self):
        """
        Apre la connessione al processo di Among Us e auto-rileva 32/64 bit.

        Su build 64-bit la base address e' tipicamente molto sopra 4 GB,
        mentre su 32-bit sta sotto: questo e' il check piu' affidabile
        senza interrogare il PE header. ``STATIC_FIELDS`` cambia di layout
        di conseguenza (0xB8 su 64-bit, 0x5C su 32-bit).
        """
        if not _PYMEM_OK:
            return False
        try:
            self.pm = pymem.Pymem(self.process_name)
            module = pymem.process.module_from_name(
                self.pm.process_handle, self.module_name)
            self.game_assembly_base = module.lpBaseOfDll
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
        """Legge un puntatore della dimensione corretta per l'architettura."""
        try:
            if self.is_64_bit:
                return self.pm.read_ulonglong(address)
            return self.pm.read_uint(address)
        except Exception:
            # Indirizzo invalido / processo terminato: il chiamante
            # interpreta 0 come "stato non pronto" e ritorna None.
            return 0

    def get_game_state(self):
        """
        Restituisce lo stato corrente del gioco come dict (vedere docstring
        di classe per i campi), oppure ``None`` se il reader non e'
        configurato o se la lettura fallisce.
        """
        if not self._is_configured:
            return None
        if not self.pm or not self.game_assembly_base:
            if not self.connect():
                return None

        # Default: tutto a False / 0. Aggiorno via via che riesco a leggere.
        state = {
            "in_game":     False,
            "game_status": 0,     # 0=menu, 1=lobby, 2=partita
            "is_voting":   False,
            "is_dead":     False,
            "is_impostor": False,
        }

        try:
            # ---- 1) STATO DEL GIOCO (menu / lobby / partita) ----
            # AmongUsClient.Instance.GameState  (int enum)
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

            # Offset Unity per "oggetto vivo nel motore?" (Native handle).
            # Su MonoBehaviour distrutto questo handle e' 0 anche se il managed
            # object esiste ancora -> permette di distinguere "distrutto" da
            # "non ancora creato".
            native_offset = 0x10 if self.is_64_bit else 0x8

            # ---- 2) PLAYER LOCALE (in_game / is_dead / is_impostor) ----
            pc_addr = self._read_ptr(
                self.game_assembly_base + self.PLAYER_CONTROL_CLASS)
            if pc_addr:
                pc_static = self._read_ptr(pc_addr + self.STATIC_FIELDS)
                if pc_static:
                    local_player = self._read_ptr(
                        pc_static + self.OFFSET_LOCAL_PLAYER)
                    if local_player:
                        # PlayerControl.LocalPlayer e' un MonoBehaviour:
                        # se il native handle e' valido, il player esiste
                        # davvero nella scena (siamo in_game).
                        player_native = self._read_ptr(
                            local_player + native_offset)
                        if player_native:
                            state["in_game"] = True
                            player_data = self._read_ptr(
                                local_player + self.OFFSET_PLAYER_DATA)
                            if player_data:
                                # is_dead: byte boolean a OFFSET_IS_DEAD.
                                state["is_dead"] = bool(
                                    self.pm.read_bool(
                                        player_data + self.OFFSET_IS_DEAD))
                                # is_impostor: leggo il TeamType del role
                                # (1 = Impostor, 0/2 = Crewmate/Other).
                                role_addr = self._read_ptr(
                                    player_data + self.OFFSET_ROLE)
                                if role_addr:
                                    team = self.pm.read_int(
                                        role_addr + self.OFFSET_TEAM_TYPE)
                                    state["is_impostor"] = (team == 1)

            # ---- 3) VOTAZIONE / MEETING in corso ----
            # MeetingHud.Instance esiste solo durante una votazione.
            # Lo verifico con il native handle (come per il player).
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
            # Errore di lettura: forza reconnect al prossimo tentativo.
            self.pm = None
            self.game_assembly_base = None
            return None
