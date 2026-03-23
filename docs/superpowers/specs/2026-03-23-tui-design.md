# TUI Mnemosyne — Design Spec
**Data:** 2026-03-23
**Stato:** Approvato dall'utente

---

## Contesto

Mnemosyne è un sistema ETL WordPress → SQLite → Analytics → Streamlit per la gestione SEO del sito ospedalemarialuigia.it. Attualmente i comandi si lanciano da CLI (`python -m mnemosyne sync`, `embeddings`, ecc.) e i risultati si visualizzano nella dashboard Streamlit nel browser.

La TUI affianca (non sostituisce) Streamlit come pannello di controllo operativo da terminale: stato del sistema, trigger comandi pipeline, chat leggera con Claude Code.

---

## Obiettivo

Un'app Textual multi-schermata che permette di:
1. Vedere lo stato del sistema in tempo reale (DB, embeddings, SEO audit, GA4/GSC)
2. Triggerare i comandi pipeline senza uscire dal terminale
3. Fare query rapide a Claude Code in-TUI e aprire sessioni interattive full

---

## Architettura

### Struttura file

```
mnemosyne/tui/
├── __init__.py
├── app.py              # MnemosyneApp(App) — entry point Textual
├── screens/
│   ├── dashboard.py    # Screen 1: stato sistema
│   ├── commands.py     # Screen 2: trigger comandi pipeline
│   └── claude.py       # Screen 3: chat Claude Code
└── widgets/
    ├── status_panel.py # Widget: DB stats + embedding status
    └── log_panel.py    # Widget: log comandi con colori
```

### Entry point CLI

Aggiunto comando `tui` a `mnemosyne/__main__.py`:

```bash
PYTHONPATH=. python -m mnemosyne tui
```

### Principio chiave

La TUI importa direttamente i moduli Python esistenti (`sync`, `embeddings`, `audit`, ecc.) — nessun subprocess per i comandi pipeline. Solo per Claude Code usa subprocess (`claude -p "..."`).

Le funzioni pipeline sono **bloccanti** (I/O di rete, `time.sleep`, calcoli UMAP). Per non congelare l'event loop Textual, l'esecuzione avviene tramite:

```python
await asyncio.to_thread(sync_all, conn, client)
```

Non `asyncio.create_task()` su coroutine che internamente bloccano — questo congelerebbe la UI.

---

## Le tre schermate

### Screen 1 — Dashboard (home)

Layout a 3 colonne + log panel in basso:

```
┌─────────────────────────────────────────────────────┐
│  MNEMOSYNE  [1:Dashboard] [2:Commands] [3:Claude]   │
├──────────────┬──────────────┬───────────────────────┤
│  DB STATUS   │  SEO AUDIT   │   GA4 / GSC           │
│              │              │                       │
│ Posts: 342   │ Orphan: 12   │ Sessions 7d: 4.2k     │
│ Embeddings:  │ Thin: 8      │ Top query: "rTMS"     │
│  current 340 │ No meta: 5   │ Avg position: 14.2    │
│  pending 2   │ H-issues: 3  │                       │
│ Last sync:   │              │ Clusters: 5           │
│  2026-03-22  │              │ Cornerstone: 3 posts  │
├──────────────┴──────────────┴───────────────────────┤
│  LOG ULTIMI COMANDI                                 │
│  [12:34] sync completato — 3 post aggiornati        │
│  [12:35] embeddings — 2 nuovi generati              │
└─────────────────────────────────────────────────────┘
```

- Aggiornamento automatico ogni 30s via `set_interval`
- GA4/GSC con cache 300s (riusa i client esistenti)

### Screen 2 — Commands

Lista comandi con keybinding, output live nel pannello destro:

```
┌─────────────────────────────────────────────────────┐
│  COMANDI PIPELINE                                   │
├────────────────────────┬────────────────────────────┤
│  [S] Sync WP           │                            │
│  [E] Extract           │  OUTPUT                    │
│  [B] Embeddings        │                            │
│  [A] Refresh analytics │  > Running: embeddings...  │
│  [U] SEO Audit         │  > 2 nuovi embedding       │
│  [K] Backup DB         │  > Completato in 4.2s      │

│                        │                            │
└────────────────────────┴────────────────────────────┘
```

- Ogni comando gira in `asyncio.to_thread()` — la TUI non si blocca
- Output catturato a fine esecuzione (batch, non streaming) via `redirect_stdout` + `post_message()`
- Stato del comando (idle / running / done / error) mostrato accanto al nome
- `[K] Backup DB`: implementato con `shutil.copy2()` — non richiede nuovo comando CLI

### Screen 3 — Claude

```
┌─────────────────────────────────────────────────────┐
│  CLAUDE CODE                                        │
├─────────────────────────────────────────────────────┤
│                                                     │
│  [conversazione scrollabile]                        │
│                                                     │
│  > Analizza i cluster attuali e suggerisci          │
│    nomi migliori per il cluster 2                   │
│                                                     │
│  Claude: Il cluster 2 contiene principalmente...   │
│                                                     │
├─────────────────────────────────────────────────────┤
│  Prompt: ________________________________  [Invio]  │
│  [O] Apri sessione interattiva completa             │
└─────────────────────────────────────────────────────┘
```

- Input → `claude -p "<prompt>"` via subprocess async, output streamato
- `[O]` → `app.suspend()` + lancia `claude` interattivo, `app.resume()` all'uscita
- **Nota compatibilità:** `app.suspend()` richiede un terminale Unix con controllo job (SIGTSTP/SIGCONT). Supportato su macOS Terminal, iTerm2, tmux. Comportamento non garantito in ambienti CI o terminali non standard.

---

## Data flow

### Aggiornamento stato (Dashboard)

```
set_interval(30s)
  └─> asyncio.to_thread(fetch_all_stats)
        ├─ query SQLite: COUNT posts, embeddings per status
        ├─ seo/audit.py → orphan, thin, missing meta
        └─> GA4/GSC clients sincroni (cache 300s esistente)
              └─> update reactive attributes → re-render
```

Sia le query SQLite che le chiamate GA4/GSC girano in `asyncio.to_thread()` per non bloccare la UI durante il refresh.

### Esecuzione comandi (Commands screen)

Le funzioni pipeline usano `print()` internamente. Per catturare l'output senza subprocess si usa `contextlib.redirect_stdout` con un `io.StringIO` buffer, poi si scrive nel LogPanel al termine (cattura batch, non streaming riga per riga):

```
Tasto premuto
  └─> asyncio.to_thread(run_with_capture, fn, *args)
        ├─ with redirect_stdout(StringIO()) as buf:
        │      fn(*args)   # es. sync_all(conn, client)
        ├─ output = buf.getvalue()
        └─> post_message(LogLine(output)) → LogPanel aggiornato
```

**Nota:** non è streaming real-time ma cattura al completamento. Per comandi lunghi (sync, embeddings) il pannello si aggiorna a fine esecuzione — accettabile dato che lo stato "running" è mostrato nel frattempo.

### Chat Claude (Claude screen)

```
Input submitted
  └─> asyncio subprocess: claude -p "<prompt>"
        ├─ legge stdout riga per riga
        └─> appende nel log panel

[O] premuto
  └─> app.suspend()
        └─> subprocess interattivo: claude
              └─> app.resume() al termine
```

---

## Error handling

| Scenario | Comportamento |
|----------|--------------|
| Comando fallisce | Riga rossa nel log con stderr, stato torna idle |
| SQLite inaccessibile | Widget mostra "DB non raggiungibile" |
| `claude` non in PATH | Messaggio esplicito "Claude Code non installato" |
| GA4/GSC timeout | Mostra ultima lettura cached con avviso "dati non aggiornati" |

---

## Testing

Nessun test Textual (richiederebbe mock UI). Le funzioni di fetch dati sono pure e testabili separatamente.

Nuovo `tests/test_tui_data.py` — testa le funzioni di fetch usate dai widget senza avviare la UI:

- `fetch_db_stats(conn)` → conta posts, ultimo sync
- `fetch_embedding_status(conn)` → current / pending / not_generated
- `fetch_seo_summary(conn)` → orphan, thin, missing meta, heading issues
- `fetch_cluster_info(conn)` → count cluster, cornerstone posts

---

## Dipendenze da aggiungere

```
textual>=0.60.0
```

---

## Out of scope

- Replicare i grafici Plotly in terminale (rimane Streamlit per quello)
- Autenticazione o multi-utente
- Configurazione da UI (rimane `.env`)
