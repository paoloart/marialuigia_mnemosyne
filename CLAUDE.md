# Mnemosyne Maria Luigia — Regole di progetto

## Regole non bypassabili

1. **Mai usare API Anthropic** — Nessuna chiamata a claude.ai o anthropic SDK. La dashboard non ha chat AI. Claude Code nel terminale è il cervello; la dashboard è lo schermo.

2. **Mai pushare su WordPress** senza conferma esplicita dell'utente. Il progetto legge da WP, non scrive.

3. **Sempre usare dati dal DB locale** (`data/maria_luigia.db`), non fetch dal web, salvo esplicita richiesta.

## Architettura Dashboard

```
Utente <-> Claude Code (terminale)
              |
         Esegue Python -> INSERT in dashboard_charts (SQLite)
              |
         Streamlit (browser) -> polling ogni 2s -> mostra grafico
```

Il DB SQLite in WAL mode è il bus di comunicazione. Claude scrive, Streamlit legge.

## Come generare grafici per il Live Canvas

```python
import sqlite3, plotly.express as px
from datetime import datetime, timezone

conn = sqlite3.connect("data/maria_luigia.db")
# ... genera fig con plotly ...
conn.execute(
    "INSERT INTO dashboard_charts (title, chart_type, data_json, created_at) VALUES (?, ?, ?, ?)",
    ("Titolo", "plotly_json", fig.to_json(), datetime.now(timezone.utc).isoformat()),
)
conn.commit()
conn.close()
```

chart_type accettati: `plotly_json`, `table`, `metric`, `markdown`

## Avvio dashboard

```bash
streamlit run mnemosyne/dashboard/app.py
```

## Struttura DB

Il DB principale è `data/maria_luigia.db`. Tabelle: posts, categories, tags, post_categories, post_tags, internal_links, external_links, headings, embeddings, dashboard_charts.

## Procedura: Aggiornamento embeddings e analisi semantica

Quando l'utente chiede di "aggiornare gli embeddings pending" o "rifare l'analisi semantica", segui questi step **nell'ordine**:

### 1. Backup DB
```bash
cp data/maria_luigia.db data/maria_luigia_backup_$(date +%Y%m%d).db
```

### 2. Genera embedding mancanti/pending
```bash
PYTHONPATH=. python -m mnemosyne embeddings
```
Questo genera solo gli embedding nuovi o con hash cambiato. NON rigenera quelli già correnti.

### 3. Verifica integrità embedding
```python
import sqlite3, numpy as np
conn = sqlite3.connect('data/maria_luigia.db')
rows = conn.execute('SELECT post_id, vector FROM embeddings').fetchall()
bad = sum(1 for r in rows if not np.isfinite(np.linalg.norm(np.frombuffer(r[1], dtype=np.float32))))
print(f'Validi: {len(rows)-bad}/{len(rows)}, Corrotti: {bad}')
```
Se ci sono corrotti, eliminare e rigenerare: `DELETE FROM embeddings WHERE post_id IN (...)` poi step 2.

### 4. Ricalcola analisi semantica e cornerstone
```bash
PYTHONPATH=. python -m mnemosyne refresh-analytics
```
Questo fa UMAP + KMeans(5) + cornerstone scoring e pusha i grafici nel Live Canvas.

### 5. Verifica nomi cluster
**IMPORTANTE**: I 5 cluster KMeans possono cambiare composizione con nuovi post. Dopo il refresh, mostra all'utente i titoli di ogni cluster e chiedi conferma dei nomi. I nomi sono hardcoded in `mnemosyne/analytics/semantic_map.py` nel dict `CLUSTER_NAMES`.

### 6. Embedding dtype
Gli embedding DEVONO essere `float32`. Sia in scrittura (`generator.py`) che in lettura. Mai `float64`.

## Avvio dashboard

```bash
PYTHONPATH=. streamlit run mnemosyne/dashboard/app.py
```

## Struttura DB

Il DB principale è `data/maria_luigia.db`. Tabelle: posts, categories, tags, post_categories, post_tags, internal_links, external_links, headings, embeddings, dashboard_charts.

## Test

```bash
python -m pytest tests/ -v
```
