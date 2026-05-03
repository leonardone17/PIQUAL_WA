# PI-QUAL 2 Viewer Web - versione semplice senza Google

Questa versione usa:
- **Streamlit** per la web app
- **cartella `CASI_RM` nel repository** per le immagini
- **PostgreSQL remoto** per salvare le risposte

## Perché PostgreSQL e non SQLite
Su Streamlit Community Cloud la persistenza dei file locali non è garantita, quindi non è affidabile salvare le risposte in SQLite locale. Streamlit raccomanda connessioni a database remoti per casi di questo tipo. citeturn368913search5turn368913search7

## Struttura immagini
Metti una cartella `CASI_RM` nella root del repository:

```text
CASI_RM/
  Caso_001/
    T2_SAG/
    T2_AX/
    T2_COR/
    DWI/
    ADC/
    DCE/
  Caso_002/
    ...
```

Sono supportati anche alias come `T1_CE` al posto di `DCE`.

## File principali
- `app.py`: interfaccia web Streamlit
- `local_repository.py`: lettura dei casi dal repository
- `scoring.py`: logica PI-QUAL
- `db.py`: salvataggio su PostgreSQL
- `.streamlit/secrets.toml.example`: esempio secrets

## Database consigliato
La strada più semplice è usare un PostgreSQL remoto compatibile con Streamlit. Streamlit ha una guida ufficiale sia per PostgreSQL generico sia per Neon. citeturn368913search7turn368913search1

## Deploy rapido
1. Crea il repository GitHub.
2. Carica questi file.
3. Aggiungi la cartella `CASI_RM` con i tuoi casi.
4. Crea un database PostgreSQL remoto.
5. In Streamlit Community Cloud crea l'app scegliendo `app.py`.
6. Inserisci le secrets:

```toml
case_root = "CASI_RM"
database_url = "postgresql+psycopg2://USER:PASSWORD@HOST/DBNAME?sslmode=require"
```

7. Deploy.
8. Invia il link.

## Note operative
- Una risposta viene salvata per **valutatore + caso**.
- Se il valutatore rientra con lo stesso ID, l'app ricarica profilo e risposte già salvate.
- Il caso successivo si sblocca solo se il precedente è stato salvato ed è completo.
- Il punteggio finale PI-QUAL viene calcolato automaticamente dall'app.
