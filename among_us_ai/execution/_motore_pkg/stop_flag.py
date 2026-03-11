"""
Stop flag condivisa per interrompere l'esecuzione di una task.

Il bot principale monitora la RAM del gioco mentre il subprocess
esegue le azioni della task. Quando rileva che lo step in RAM e'
avanzato (= la fase e' stata completata), manda "STOP\\n" su stdin
del subprocess.

Un thread reader nel subprocess (avviato in `lifecycle.run_task`)
legge stdin: se trova "STOP", chiama `request_stop()` che setta una
flag. Gli handler controllano questa flag periodicamente nei loop
interni (drag, drag_zone, ecc.) e si interrompono in modo pulito
se la flag e' settata.

Vantaggi:
  - Reattivita' rapida (~100ms) anche durante azioni lente
  - Niente azioni inutili dopo che la fase e' stata completata
  - Niente click "fuori dal pannello" (il pannello potrebbe essersi
    chiuso dopo che la fase e' stata risolta)
"""

# Flag interna: True = il bot principale ha richiesto lo stop
_stop_requested = False


def request_stop():
    """
    Marca lo stop come richiesto.

    Chiamato dal thread reader di stdin quando arriva "STOP\\n".
    Idempotente: chiamarlo piu' volte non e' un problema.
    """
    global _stop_requested
    _stop_requested = True


def is_stop_requested():
    """
    True se il bot principale ha richiesto lo stop dell'esecuzione.

    Da usare negli handler in punti dove vogliamo "uscire pulitamente"
    (es. dentro un loop di drag, fra una iterazione e l'altra).

    Esempio d'uso:
        if is_stop_requested():
            # rilascia eventuali tasti/mouse pressati
            _pag.mouseUp()
            return  # esce dall'handler
    """
    return _stop_requested


def reset_stop():
    """
    Resetta la flag a False.

    Chiamato all'inizio di ogni run_task per pulire eventuale stato
    residuo da una task precedente (anche se in produzione il
    subprocess vive solo per una task, e' una sicurezza in piu').
    """
    global _stop_requested
    _stop_requested = False
