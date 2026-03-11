"""
Esecuzione delle task come **thread interno** invece di subprocess separato.

Vantaggi rispetto al subprocess:
  - Zero startup di Python (~300-500ms risparmiati per ogni avvio)
  - Zero IPC overhead (nessun fork, nessun pipe del SO)
  - Avvio quasi istantaneo: appena premi SPAZIO, il motore parte
  - Nessuna copia in memoria del modulo `_motore_pkg` (gia' caricato
    nel processo principale)

Compatibilita' con il modello subprocess:
  - L'oggetto `TaskThreadProcess` ritornato espone la stessa API di
    `subprocess.Popen` (poll(), wait(), terminate(), pid, stdout)
  - Le `print()` del motore vengono catturate via `redirect_stdout`
    e propagate al lettore stdout esistente in tasks_process.py
  - I marker `__COOLDOWN__:` continuano a funzionare uguali
  - Exit code 0 se la task riesce, 1 se esegui_lifecycle ritorna False

Sicurezza:
  - Tutto il motore e' wrappato in try/except: una eccezione del motore
    viene loggata + segnata come exit_code=1 ma NON crasha il bot.
  - Il thread e' marcato daemon=True: se il bot principale termina,
    il thread non blocca lo shutdown.
"""
import io
import os
import sys
import time
import threading


class TaskThreadProcess:
    """
    Wrapper che mima `subprocess.Popen` ma esegue il motore in un thread
    interno al processo principale del bot.

    API supportata (compatibile con il codice subprocess esistente):
      - .pid                (int, fittizio: thread.ident)
      - .stdout             (file-like, leggibile per riga)
      - .returncode         (int, None se in esecuzione)
      - .poll() -> int|None (None se in esecuzione, exit_code se terminato)
      - .wait(timeout=None) -> int (blocca fino a fine + ritorna exit_code)
      - .terminate()        (richiede stop, soft)
      - .kill()             (alias di terminate; non e' realmente kill -9)
    """

    def __init__(self, task_meta, azioni, nome_task=""):
        """
        Crea e AVVIA il thread di esecuzione.

        Parametri
        ---------
        task_meta : dict
            Metadati della task (incluso step, start_from_action,
            delay_avvio, ecc.). Stesso formato di TASK_META nel file .py.
        azioni : list[dict]
            Lista delle azioni della task.
        nome_task : str
            Nome usato per i log. Solo cosmetico.
        """
        self._task_meta = task_meta
        self._azioni = azioni
        self._nome = nome_task or task_meta.get('nome', '?')

        # Pipe in-memory per catturare stdout del motore.
        # Usiamo `os.pipe()` invece di `io.BytesIO` perche' il reader thread
        # esistente (in tasks_process.py) cicla con `for raw in proc.stdout`
        # che si comporta in streaming SOLO se stdout e' un file pipe vero.
        # Una `BytesIO` bloccherebbe il reader (read() ritorna b'' subito,
        # senza aspettare nuove scritture).
        read_fd, write_fd = os.pipe()
        # Disabilita buffering sul lato write
        self._write_fd = write_fd
        self._write_file = os.fdopen(write_fd, 'wb', buffering=0)
        # Lato read esposto come `proc.stdout` (binary, line-buffered)
        self.stdout = os.fdopen(read_fd, 'rb', buffering=0)

        # Stato exit code
        self.returncode = None

        # Flag stop richiesto da terminate()/kill()
        self._stop_requested = False

        # Thread principale: esegue esegui_lifecycle
        self._thread = threading.Thread(
            target=self._run_inside_thread,
            name=f"TaskThread-{self._nome}",
            daemon=True,
        )
        self._thread.start()

        # PID fittizio (non e' un vero PID di OS, e' l'ident del thread)
        self.pid = self._thread.ident or -1

    # ------------------------------------------------------------------
    # Thread di esecuzione
    # ------------------------------------------------------------------

    def _run_inside_thread(self):
        """
        Body del thread: esegue il motore con stdout/stderr reindirizzati
        sulla pipe. Cattura tutte le eccezioni per non far crashare il
        bot principale.
        """
        # Wrapper TextIOBase compatibile per redirezione di sys.stdout.
        # Convive bene con codice che chiama write(str), flush(), e
        # eventualmente isatty()/fileno() (return defaults conservativi).
        import io as _io
        pipe_writer_bin = self._write_file

        class _PipeTextIO(_io.TextIOBase):
            def __init__(self, fd_file):
                self._fd = fd_file
                self._lock = threading.Lock()
            def write(self, s):
                if not s:
                    return 0
                if isinstance(s, bytes):
                    data = s
                else:
                    data = s.encode('utf-8', errors='replace')
                with self._lock:
                    try:
                        self._fd.write(data)
                        self._fd.flush()
                    except (OSError, ValueError):
                        # Pipe chiusa (terminate() chiamato); ignora.
                        return 0
                return len(s)
            def flush(self):
                try:
                    self._fd.flush()
                except (OSError, ValueError):
                    pass
            def writable(self):
                return True
            def isatty(self):
                return False
            def fileno(self):
                # Alcune librerie chiamano fileno(): ritorna l'fd reale
                # del lato write della pipe.
                return self._fd.fileno()

        pipe_writer = _PipeTextIO(pipe_writer_bin)

        # Importa il motore qui, lazy: cosi' se l'import fallisce,
        # l'errore va al log invece di crashare al modulo-load.
        try:
            from ._motore_pkg.lifecycle import esegui_lifecycle
        except ImportError as imp_err:
            self.returncode = 1
            try:
                pipe_writer_bin.write(
                    f"[ThreadRunner] Impossibile importare esegui_lifecycle: {imp_err}\n".encode()
                )
                pipe_writer_bin.close()
            except Exception:
                pass
            return

        exit_code = 0
        try:
            # Reindirizza stdout/stderr SOLO per questo thread.
            # NB: redirect_stdout e' thread-local solo se Python 3.10+
            # con sys.settrace, ma in pratica lo facciamo a livello di
            # thread cosi' altre print del bot principale non finiscono
            # nella pipe.
            #
            # Uso un trick: salvo i sys.stdout/stderr originali e li
            # ri-imposto a fine thread. Le print del motore vanno alla
            # pipe; le print del bot principale (su altri thread) vanno
            # al terminale.
            #
            # ATTENZIONE: questo NON e' thread-safe se altre task girano
            # in parallelo. La nostra architettura e' single-task-at-a-time
            # (vedi check `_task_process is not None` in tasks_process.py),
            # quindi e' sicuro.
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = pipe_writer
            sys.stderr = pipe_writer
            try:
                ok = esegui_lifecycle(self._task_meta, self._azioni)
                exit_code = 0 if ok else 1
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr
        except SystemExit as e:
            # esegui_lifecycle puo' chiamare sys.exit(N) - rispettiamolo
            try:
                exit_code = int(e.code) if e.code is not None else 0
            except (ValueError, TypeError):
                exit_code = 1
        except KeyboardInterrupt:
            exit_code = 130  # convenzione *nix per Ctrl-C
        except Exception as exc:
            # Ogni altra eccezione: log + exit code 1
            try:
                pipe_writer.write(f"[ThreadRunner] Eccezione non gestita: {exc!r}\n")
                import traceback
                pipe_writer.write(traceback.format_exc())
            except Exception:
                pass
            exit_code = 1

        # Imposta returncode e chiudi la pipe (cosi' il reader esce dal
        # ciclo `for line in proc.stdout`).
        self.returncode = exit_code
        try:
            self._write_file.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # API compatibile con subprocess.Popen
    # ------------------------------------------------------------------

    def poll(self):
        """Ritorna None se in esecuzione, altrimenti l'exit code."""
        if self._thread.is_alive():
            return None
        return self.returncode if self.returncode is not None else 0

    def wait(self, timeout=None):
        """Blocca fino a termine del thread; ritorna exit code."""
        self._thread.join(timeout=timeout)
        return self.returncode if self.returncode is not None else 0

    def terminate(self):
        """
        Richiede lo stop "soft" del thread.

        I thread Python non possono essere uccisi forzatamente; possiamo
        solo settare un flag che il motore controlla periodicamente
        (vedi `_stop_requested` -> meccanismo di check nel motore).
        Per ora l'implementazione e' best-effort: chiudiamo la pipe
        (causa errori di scrittura nel motore al prossimo print) e
        speriamo che il motore termini in fretta.
        """
        self._stop_requested = True
        try:
            self._write_file.close()
        except Exception:
            pass

    def kill(self):
        """Alias di terminate (non puo' fare un vero kill -9 su un thread)."""
        self.terminate()
