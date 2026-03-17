# Mnemosyne Maria Luigia — Design Document

## Obiettivo

Creare un database locale SQLite contenente tutti i ~190 blog post del sito WordPress Maria Luigia, con possibilità di:

1. Analisi SEO (keyword density, titoli, meta description, lunghezza articoli)
2. Analisi struttura (headings H1-H6, gerarchia contenuti)
3. Analisi link interni (grafo, orphan pages, cluster)
4. Ricerca semantica tramite embeddings
5. Round-trip: modificare nel DB e ri-pushare su WordPress preservando la struttura HTML

## Stack tecnologico

- **Python** come linguaggio principale
- **SQLite** per il database (singolo file, zero dipendenze)
- **Embeddings:** OpenAI `text-embedding-3-large` (3072 dimensioni)
- **Librerie:** requests, beautifulsoup4, python-dotenv, openai, numpy, jupyter

## Schema database

### posts

| Colonna              | Tipo     | Note                                      |
|----------------------|----------|-------------------------------------------|
| id                   | INTEGER  | PK, dall'ID WordPress                     |
| title                | TEXT     |                                           |
| slug                 | TEXT     |                                           |
| url                  | TEXT     |                                           |
| content_html         | TEXT     | HTML originale, source of truth           |
| content_text         | TEXT     | Testo pulito, derivato da content_html    |
| excerpt              | TEXT     |                                           |
| status               | TEXT     | publish/draft                             |
| date_published       | TEXT     | ISO 8601                                  |
| date_modified        | TEXT     | ISO 8601, usato per sync intelligente     |
| author               | TEXT     |                                           |
| featured_image_url   | TEXT     |                                           |
| featured_image_alt   | TEXT     |                                           |
| meta_description     | TEXT     | Da Yoast SEO (yoast_head_json) se disponibile |
| content_text_hash    | TEXT     | SHA256 di content_text, per invalidare embeddings |
| word_count           | INTEGER  | Calcolato su content_text                 |

### categories

| Colonna   | Tipo    | Note                        |
|-----------|---------|-----------------------------|
| id        | INTEGER | PK                          |
| name      | TEXT    |                             |
| slug      | TEXT    |                             |
| parent_id | INTEGER | FK nullable, per gerarchie  |

### tags

| Colonna | Tipo    | Note |
|---------|---------|------|
| id      | INTEGER | PK   |
| name    | TEXT    |      |
| slug    | TEXT    |      |

### post_categories (N:N)

| Colonna     | Tipo    | Note |
|-------------|---------|------|
| post_id     | INTEGER | FK   |
| category_id | INTEGER | FK   |

### post_tags (N:N)

| Colonna | Tipo    | Note |
|---------|---------|------|
| post_id | INTEGER | FK   |
| tag_id  | INTEGER | FK   |

### internal_links

| Colonna        | Tipo    | Note                                    |
|----------------|---------|---------------------------------------- |
| id             | INTEGER | PK autoincrement                        |
| source_post_id | INTEGER | FK                                      |
| target_post_id | INTEGER | FK nullable (se link a pagina non-post) |
| target_url     | TEXT    |                                         |
| anchor_text    | TEXT    |                                         |

### external_links

| Colonna        | Tipo    | Note                         |
|----------------|---------|------------------------------|
| id             | INTEGER | PK autoincrement             |
| source_post_id | INTEGER | FK                           |
| target_url     | TEXT    |                              |
| anchor_text    | TEXT    |                              |

### headings

| Colonna  | Tipo    | Note                    |
|----------|---------|-------------------------|
| id       | INTEGER | PK autoincrement        |
| post_id  | INTEGER | FK                      |
| level    | INTEGER | 1-6                     |
| text     | TEXT    |                         |
| position | INTEGER | Ordine nel documento    |

### embeddings

| Colonna    | Tipo    | Note                             |
|------------|---------|----------------------------------|
| post_id    | INTEGER | PK composita (post_id, model_name), FK |
| model_name | TEXT    | PK composita, es. "text-embedding-3-large" |
| vector     | BLOB    | numpy array serializzato         |
| source_hash | TEXT   | SHA256 del content_text al momento della generazione |
| created_at | TEXT    | ISO 8601                         |

## Architettura del progetto

```
Mnemosyne_Maria_Luigia/
├── config.py              # Configurazione (URL sito, credenziali via env vars)
├── .env                   # App password WP, API key OpenAI (gitignored)
├── .gitignore
├── requirements.txt
├── db/
│   ├── schema.py          # Creazione tabelle SQLite
│   └── connection.py      # Helper connessione DB
├── scraper/
│   ├── wp_client.py       # Client REST API WordPress (fetch singolo post, categorie, tag)
│   ├── parser.py          # Parsing HTML → testo, estrazione link interni, headings
│   └── sync.py            # Orchestrazione: scarica tutto e popola il DB
├── embeddings/
│   └── generator.py       # Genera embeddings via OpenAI e li salva nel DB
├── analysis/              # Moduli di analisi (cresceranno nel tempo)
│   ├── seo.py             # Keyword density, word count, meta analysis
│   ├── structure.py       # Analisi headings, gerarchia contenuti
│   └── links.py           # Grafo link interni, orphan pages, cluster
├── data/
│   └── maria_luigia.db    # Il database SQLite (gitignored)
├── notebooks/             # Jupyter notebooks per analisi esplorative
│   └── exploration.ipynb
└── docs/
```

## Flusso operativo — 3 fasi separate

```
WordPress REST API
        │
        ▼
   [1. SYNC]  ──► posts.content_html (fedele all'originale)
        │          categories, tags, post_categories, post_tags
        │          metadati (excerpt, author, featured_image, ecc.)
        │
        │          • Una chiamata API per articolo con delay (1s) per evitare ban
        │          • Retry con backoff esponenziale su errori HTTP 429/5xx
        │          • Sync intelligente: confronta date_modified, scarica solo modifiche
        │          • ~190 articoli = ~3 minuti prima esecuzione
        │
        ▼
   [2. EXTRACT] ──► posts.content_text (testo pulito, derivato da content_html)
        │            posts.word_count
        │            internal_links (link <a> interni con anchor text)
        │            external_links (link <a> verso domini esterni)
        │            headings (struttura H1-H6 con posizione)
        │
        │            • Ricalcolabile in qualsiasi momento da content_html
        │
        ▼
   [3. EMBEDDINGS] ──► embeddings (SOLO su comando esplicito dell'utente)
                        • Modello: text-embedding-3-large (3072 dim)
                        • Genera solo per post senza embedding o con content_text_hash cambiato
                        • Vettore serializzato con numpy.tobytes()
```

## Autenticazione WordPress

- Basic Auth con Application Password (generata dal pannello WP)
- Credenziali in `.env`:
  ```
  WP_BASE_URL=https://...
  WP_USERNAME=...
  WP_APP_PASSWORD=...
  OPENAI_API_KEY=...
  ```

## CLI

Entry point unico:

- `python -m mnemosyne sync` — scarica/aggiorna da WordPress
- `python -m mnemosyne extract` — estrae testo, link, headings dal HTML
- `python -m mnemosyne embeddings` — genera embeddings (solo su comando)

## Principi di design

- **content_html è il source of truth** — preservato fedelmente per consentire round-trip verso WordPress
- **content_text è derivato** — sempre ricalcolabile da content_html
- **Embeddings solo on-demand** — non generati automaticamente durante sync/extract
- **Sync incrementale** — confronto date_modified per non riscaricare tutto ogni volta
- **Credenziali mai nel codice** — tutto in .env, gitignored
