# Git LFS — note di setup

Questo repository usa **Git LFS** fin dal primo commit per i file
binari/pesanti: i modelli YOLO (`*.pt`) e i file di dati (`*.json`) sono
versionati come puntatori LFS (vedi `.gitattributes`). I contenuti reali
sono inclusi nello store locale `.git/lfs/objects/`.

## Verifica in locale (consigliata prima del push)

    git lfs install
    git lfs ls-files
    git lfs fsck
    git lfs checkout

## Push su GitHub

    git remote add origin <URL_DEL_REPO>
    git push -u origin --all

## Note

- `*.pt` e `*.json` sono tracciati via LFS.
- La cartella `tasks_exec/` NON e' versionata (vedi .gitignore): i file
  degli esecutori vengono rigenerati automaticamente dal task writer a
  partire da `task_registrate.json` se assenti.
