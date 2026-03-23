# Site Crawler SEO — Design Document

**Progetto:** Mnemosyne Maria Luigia
**Data:** 2026-03-20
**Stato:** Proposta

---

## 1. Obiettivo

Costruire un modulo crawler integrato in Mnemosyne che, partendo dalla sitemap XML generata da Yoast SEO, esegua un audit completo del sito `ospedalemarialuigia.it` — simile a Screaming Frog ma cucito sull'architettura esistente (CLI → SQLite → Streamlit).

Il crawler **non modifica nulla** sul sito. Legge e basta.

---

## 2. Cosa analizza

### 2.1 Raggiungibilità e status HTTP

| Check | Descrizione | Severità |
|-------|-------------|----------|
| Status code | 200, 301, 302, 404, 410, 5xx per ogni URL in sitemap | 🔴 critico (4xx/5xx) |
| Redirect chain | Catene >2 hop o redirect loop | 🟠 warning |
| Tempo di risposta | TTFB per ogni pagina (ms) | 🟡 info se >1s, 🟠 se >3s |
| URL in sitemap ma 404 | Pagine fantasma nella sitemap | 🔴 critico |
| Mismatch canonical | L'URL canonical dichiarato non corrisponde all'URL effettivo | 🔴 critico |

### 2.2 SEO on-page (per ogni pagina crawlata)

| Check | Descrizione | Severità |
|-------|-------------|----------|
| Title tag | Mancante, vuoto, duplicato tra pagine, troppo lungo (>60ch) o corto (<30ch) | 🔴/🟠 |
| Meta description | Mancante, vuota, duplicata, troppo lunga (>160ch) o corta (<70ch) | 🟠 |
| H1 | Mancante, multiplo, vuoto | 🔴 |
| Struttura heading | Salti di livello (H2→H4), H1 multipli | 🟠 |
| Immagini senza alt | `<img>` senza attributo alt o alt vuoto | 🟠 |
| Immagini rotte | `<img src="...">` che ritorna 404 | 🔴 |
| Canonical tag | Assente, self-referencing corretto, punta altrove | 🟠/🔴 |
| Open Graph | og:title, og:description, og:image mancanti | 🟡 info |
| Hreflang | Se presente, verifica coerenza (non previsto multilingua, ma check) | 🟡 info |
| Schema.org/JSON-LD | Presenza e tipo di structured data | 🟡 info |
| Robots meta | noindex, nofollow involontari | 🔴 critico |

### 2.3 Contenuto

| Check | Descrizione | Severità |
|-------|-------------|----------|
| Word count | Conteggio parole dal body (confronto con dato in DB locale) | 🟡 info |
| Thin content | Pagine con <300 parole | 🟠 warning |
| Contenuto duplicato | Similarità alta tra pagine (via embeddings già in DB) | 🟠 warning |
| Ratio testo/HTML | Percentuale di testo visibile rispetto al codice HTML totale | 🟡 info |

### 2.4 Link interni ed esterni

| Check | Descrizione | Severità |
|-------|-------------|----------|
| Link interni rotti | Link a pagine interne che danno 404 | 🔴 critico |
| Link esterni rotti | Link a siti esterni che danno 4xx/5xx (sample, non tutti) | 🟠 warning |
| Anchor text vuoto | `<a href="..."></a>` o con solo immagine senza alt | 🟠 |
| Link nofollow interni | Link interni con rel="nofollow" (spreco di link juice) | 🟡 info |
| Redirect interni | Link interni che puntano a URL che fanno redirect | 🟠 |

### 2.5 Risorse e performance

| Check | Descrizione | Severità |
|-------|-------------|----------|
| Immagini pesanti | Immagini >200KB | 🟠 warning |
| Immagini non ottimizzate | Formato non WebP/AVIF quando potrebbe esserlo | 🟡 info |
| CSS/JS bloccanti | Risorse render-blocking nel `<head>` | 🟡 info |
| Mixed content | Risorse HTTP su pagina HTTPS | 🔴 critico |

### 2.6 Sitemap e robots.txt

| Check | Descrizione | Severità |
|-------|-------------|----------|
| robots.txt | Controlla esistenza, regole di blocco impreviste | 🟠 |
| Sitemap vs realtà | URL in sitemap ma non raggiungibili, e viceversa | 🔴/🟠 |
| Lastmod coerenza | `<lastmod>` in sitemap vs header Last-Modified della pagina | 🟡 info |

---

## 3. Architettura

### 3.1 Principio: stessa architettura di Mnemosyne

```
Utente (terminale)
   │
   └─> python -m mnemosyne crawl <sitemap_url_o_file>
          │
          ├─ 1. Parsa sitemap XML (+ sitemap index se presente)
          ├─ 2. Per ogni URL: HTTP GET + parsing HTML
          ├─ 3. INSERT risultati in tabelle SQLite (crawl_runs, crawl_pages, crawl_issues)
          ├─ 4. Genera summary e push grafici in dashboard_charts
          │
          └─> Dashboard Streamlit (nuova pagina 6_site_crawler.py) legge i risultati
```

### 3.2 Nuovo modulo: `mnemosyne/crawler/`

```
mnemosyne/crawler/
├── __init__.py
├── sitemap.py          # Parsing sitemap XML (index + urlset)
├── fetcher.py          # HTTP fetcher con concorrenza controllata
├── analyzers/
│   ├── __init__.py
│   ├── http_check.py   # Status code, redirect chain, TTFB
│   ├── onpage.py       # Title, meta, H1, headings, canonical, OG, schema
│   ├── images.py       # Alt mancanti, immagini rotte, peso, formato
│   ├── links.py        # Link interni/esterni rotti, anchor vuoti, nofollow
│   ├── content.py      # Word count, thin, text/HTML ratio
│   └── resources.py    # CSS/JS bloccanti, mixed content
├── engine.py           # Orchestratore: sitemap → fetch → analyze → store
└── report.py           # Genera summary per dashboard_charts
```

### 3.3 Nuove tabelle SQLite

```sql
-- Una "run" per ogni esecuzione del crawler
CREATE TABLE IF NOT EXISTS crawl_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,           -- ISO timestamp
    finished_at TEXT,
    sitemap_url TEXT NOT NULL,          -- URL o path della sitemap usata
    total_urls INTEGER DEFAULT 0,
    crawled_urls INTEGER DEFAULT 0,
    status TEXT DEFAULT 'running'       -- running | completed | failed
);

-- Una riga per ogni pagina crawlata
CREATE TABLE IF NOT EXISTS crawl_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    url TEXT NOT NULL,
    status_code INTEGER,
    redirect_url TEXT,                  -- URL finale dopo redirect (NULL se nessun redirect)
    redirect_chain TEXT,                -- JSON array dei redirect hop
    ttfb_ms INTEGER,                    -- Time to first byte in ms
    content_type TEXT,
    content_length INTEGER,             -- bytes
    title TEXT,
    meta_description TEXT,
    meta_robots TEXT,                   -- contenuto del meta robots
    canonical_url TEXT,
    h1_count INTEGER DEFAULT 0,
    h1_text TEXT,                       -- primo H1 trovato
    word_count INTEGER DEFAULT 0,
    html_size INTEGER DEFAULT 0,        -- dimensione HTML in bytes
    text_ratio REAL,                    -- testo/html ratio
    has_og_title INTEGER DEFAULT 0,
    has_og_description INTEGER DEFAULT 0,
    has_og_image INTEGER DEFAULT 0,
    has_schema_json_ld INTEGER DEFAULT 0,
    schema_types TEXT,                  -- JSON array dei @type trovati
    img_total INTEGER DEFAULT 0,
    img_no_alt INTEGER DEFAULT 0,
    internal_links_count INTEGER DEFAULT 0,
    external_links_count INTEGER DEFAULT 0,
    crawled_at TEXT NOT NULL,
    FOREIGN KEY (run_id) REFERENCES crawl_runs(id)
);

-- Ogni problema trovato, categorizzato
CREATE TABLE IF NOT EXISTS crawl_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    page_id INTEGER,                    -- NULL per issue globali (es. robots.txt)
    url TEXT NOT NULL,
    category TEXT NOT NULL,             -- 'http', 'onpage', 'content', 'images', 'links', 'resources', 'sitemap'
    severity TEXT NOT NULL,             -- 'critical', 'warning', 'info'
    check_name TEXT NOT NULL,           -- es. 'missing_title', 'broken_link', '404_in_sitemap'
    message TEXT NOT NULL,              -- Descrizione leggibile
    details TEXT,                       -- JSON con dati aggiuntivi (es. redirect chain)
    FOREIGN KEY (run_id) REFERENCES crawl_runs(id),
    FOREIGN KEY (page_id) REFERENCES crawl_pages(id)
);

-- Duplicati trovati (title e meta description)
CREATE TABLE IF NOT EXISTS crawl_duplicates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    field TEXT NOT NULL,                -- 'title' | 'meta_description'
    value TEXT NOT NULL,                -- Il valore duplicato
    urls TEXT NOT NULL,                 -- JSON array di URL con quel valore
    count INTEGER NOT NULL,
    FOREIGN KEY (run_id) REFERENCES crawl_runs(id)
);

-- Immagini analizzate
CREATE TABLE IF NOT EXISTS crawl_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    page_id INTEGER NOT NULL,
    src TEXT NOT NULL,
    alt TEXT,
    status_code INTEGER,               -- NULL se non verificato
    content_length INTEGER,             -- bytes
    content_type TEXT,                  -- image/jpeg, image/webp, etc.
    is_broken INTEGER DEFAULT 0,
    is_missing_alt INTEGER DEFAULT 0,
    is_oversized INTEGER DEFAULT 0,     -- >200KB
    FOREIGN KEY (run_id) REFERENCES crawl_runs(id),
    FOREIGN KEY (page_id) REFERENCES crawl_pages(id)
);

-- Link verificati (interni + esterni)
CREATE TABLE IF NOT EXISTS crawl_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    source_page_id INTEGER NOT NULL,
    target_url TEXT NOT NULL,
    anchor_text TEXT,
    is_internal INTEGER NOT NULL,       -- 1 = interno, 0 = esterno
    rel TEXT,                           -- "nofollow", "sponsored", etc.
    status_code INTEGER,               -- NULL se non verificato
    is_broken INTEGER DEFAULT 0,
    is_redirect INTEGER DEFAULT 0,
    FOREIGN KEY (run_id) REFERENCES crawl_runs(id),
    FOREIGN KEY (source_page_id) REFERENCES crawl_pages(id)
);
```

---

## 4. Dettaglio componenti

### 4.1 `sitemap.py` — Parser Sitemap

```python
"""
Parsing sitemap XML (supporta sitemap index Yoast).

Input: URL o path locale di sitemap.xml
Output: lista di SitemapEntry(url, lastmod, changefreq, priority)
"""

@dataclass
class SitemapEntry:
    url: str
    lastmod: str | None = None
    changefreq: str | None = None
    priority: float | None = None

def parse_sitemap(source: str) -> list[SitemapEntry]:
    """
    Se source è un URL → fetch XML.
    Se source è un file locale → leggi file.
    Se è un sitemap index → segui ricorsivamente i <sitemap><loc>.
    Gestisce namespace XML di Yoast.
    """
    pass

def _parse_urlset(xml_content: bytes) -> list[SitemapEntry]:
    """Parsa un singolo <urlset>."""
    pass

def _parse_sitemap_index(xml_content: bytes) -> list[str]:
    """Parsa <sitemapindex>, ritorna lista di URL di sub-sitemap."""
    pass
```

**Dipendenze:** `xml.etree.ElementTree` (stdlib), `requests` (già in requirements).

### 4.2 `fetcher.py` — HTTP Fetcher concorrente

```python
"""
Fetcher HTTP con:
- Concorrenza limitata (default 5 thread, configurabile)
- Delay tra richieste allo stesso host (politeness, default 0.5s)
- Timeout per request (default 10s)
- Retry su errori di rete (max 2 retry con backoff)
- User-Agent personalizzato: "MnemosyneBot/1.0 (+ospedalemarialuigia.it)"
- Raccolta TTFB (time to first byte)
- Follow redirect con tracciamento catena
"""

@dataclass
class FetchResult:
    url: str
    final_url: str                   # dopo redirect
    status_code: int
    redirect_chain: list[tuple[str, int]]  # [(url, status_code), ...]
    ttfb_ms: int
    headers: dict[str, str]
    body: bytes | None               # None se non HTML
    content_type: str
    content_length: int
    error: str | None                # errore di rete

class SiteFetcher:
    def __init__(self, max_workers=5, delay=0.5, timeout=10):
        self.session = requests.Session()
        # ...

    def fetch_all(self, urls: list[str],
                  callback: Callable | None = None) -> list[FetchResult]:
        """
        Fetch tutte le URL con ThreadPoolExecutor.
        callback(done, total) per progress reporting.
        """
        pass

    def fetch_one(self, url: str) -> FetchResult:
        """
        Fetch singolo URL.
        - allow_redirects=False per tracciare catena manualmente
        - Misura TTFB con requests hooks
        """
        pass
```

**Nota sulla concorrenza:** si usa `ThreadPoolExecutor` (non asyncio) per coerenza con il resto del progetto che usa `requests`. 5 worker simultanei sono un buon bilanciamento tra velocità e gentilezza verso il server — il sito è il proprio, ma non vogliamo sovraccaricare l'hosting.

**Nota importante:** il fetcher NON verifica ogni singolo link esterno. Per i link esterni fa un check HEAD (non GET) e solo un campione o su richiesta esplicita, per non martellare siti terzi.

### 4.3 `analyzers/` — I singoli check

Ogni analyzer è una funzione pura:

```python
# Signature comune per tutti gli analyzer
def analyze_*(page: CrawlPage, html: BeautifulSoup, fetch_result: FetchResult) -> list[CrawlIssue]
```

**`http_check.py`:**
- `check_status_code()` → issue se non 200
- `check_redirect_chain()` → issue se >2 hop o loop
- `check_ttfb()` → issue se >1000ms (warning) o >3000ms (critical)

**`onpage.py`:**
- `check_title()` → mancante, vuoto, >60ch, <30ch
- `check_meta_description()` → mancante, vuota, >160ch, <70ch
- `check_h1()` → mancante, multiplo, vuoto
- `check_headings_structure()` → salti di livello
- `check_canonical()` → mancante, mismatch con URL effettivo
- `check_meta_robots()` → noindex/nofollow non intenzionale
- `check_og_tags()` → og:title/description/image mancanti
- `check_schema_jsonld()` → presenza e tipo

**`images.py`:**
- `check_missing_alt()` → img senza alt
- `check_image_size()` → immagini >200KB (via Content-Length, HEAD request)
- `check_image_format()` → JPEG/PNG che potrebbero essere WebP

**`links.py`:**
- `extract_and_check_links()` → tutti i link nella pagina
- `check_broken_internal()` → link interni che non risolvono a 200
- `check_nofollow_internal()` → link interni con nofollow
- `check_empty_anchor()` → anchor text vuoto

**`content.py`:**
- `check_word_count()` → conteggio e flag thin
- `check_text_html_ratio()` → rapporto testo/codice

**`resources.py`:**
- `check_mixed_content()` → risorse HTTP su pagina HTTPS
- `check_render_blocking()` → CSS/JS nel head senza async/defer

### 4.4 `engine.py` — Orchestratore

```python
"""
Orchestratore del crawl. Flusso:

1. Parsa sitemap
2. Crea crawl_run nel DB
3. Fetch robots.txt → analizza
4. Per ogni URL dalla sitemap:
   a. Fetch HTML
   b. Parse con BeautifulSoup
   c. Esegui tutti gli analyzer
   d. Salva risultati in crawl_pages + crawl_issues
   e. Aggiorna progresso (crawled_urls)
5. Post-processing:
   a. Rileva duplicati (title, meta_description)
   b. Cross-reference link interni rotti (usa i status_code già raccolti)
   c. Verifica link esterni (HEAD request, campione o tutti)
6. Genera report summary → dashboard_charts
7. Marca crawl_run come completed
"""

class CrawlEngine:
    def __init__(self, conn: sqlite3.Connection, sitemap_source: str,
                 max_workers=5, delay=0.5, check_external_links=False):
        # ...

    def run(self) -> int:
        """Esegue il crawl completo. Ritorna run_id."""
        pass

    def _process_page(self, entry: SitemapEntry, result: FetchResult) -> None:
        """Processa una singola pagina: parse + analyze + store."""
        pass

    def _post_process(self, run_id: int) -> None:
        """Duplicati, cross-ref link, report."""
        pass
```

### 4.5 `report.py` — Genera grafici per la Dashboard

Dopo ogni crawl, genera e pusha in `dashboard_charts`:

1. **Metric card: Health Score** — percentuale di pagine senza issue critici
2. **Pie chart: Distribuzione severità** — quanti critical/warning/info
3. **Bar chart: Issue per categoria** — HTTP, On-page, Content, Images, Links, Resources
4. **Tabella: Top 20 issue critici** — i problemi più gravi con URL
5. **Scatter: TTFB per pagina** — tempo di risposta, colorato per range
6. **Bar chart: Distribuzione status code** — 200, 301, 302, 404, etc.

```python
def generate_crawl_report(conn: sqlite3.Connection, run_id: int) -> None:
    """Genera tutti i grafici e li inserisce in dashboard_charts (pinned=1)."""
    pass

def _health_score(conn, run_id) -> float:
    """% di pagine in sitemap senza issue critical."""
    pass

def _severity_distribution(conn, run_id) -> go.Figure:
    """Pie chart critical/warning/info."""
    pass

def _issues_by_category(conn, run_id) -> go.Figure:
    """Bar chart orizzontale per categoria."""
    pass
```

---

## 5. Pagina Dashboard: `6_site_crawler.py`

Nuova pagina Streamlit con questa struttura:

```
🕷️ Site Crawler
├── Header con info ultimo crawl (data, URL crawlate, durata)
├── 4 metric cards: Health Score | Critical | Warning | Info
├── Tab: Panoramica
│   ├── Distribuzione severità (pie)
│   ├── Issue per categoria (bar)
│   └── TTFB distribution (scatter)
├── Tab: Errori HTTP
│   ├── Filtro per status code
│   └── Tabella URL con status, redirect chain, TTFB
├── Tab: SEO On-Page
│   ├── Filtro per tipo di check
│   └── Tabella issue con URL, check_name, message
├── Tab: Immagini
│   ├── Summary: totale, senza alt, rotte, pesanti
│   └── Tabella dettaglio
├── Tab: Link
│   ├── Sub-tab: Interni rotti
│   ├── Sub-tab: Esterni rotti
│   ├── Sub-tab: Redirect interni
│   └── Sub-tab: Anchor vuoti
├── Tab: Contenuto
│   ├── Word count distribution (histogram)
│   ├── Thin content list
│   └── Duplicati title/meta
└── Sidebar:
    ├── Selettore crawl_run (storico)
    ├── Pulsante "Nuovo crawl" (TBD, o solo da CLI)
    └── Export CSV delle issue
```

Refresh rate: `run_every=5` (non serve 2s come il live canvas, il crawl non cambia in tempo reale).

---

## 6. CLI: nuovo comando `crawl`

```bash
# Crawl da URL sitemap
python -m mnemosyne crawl https://ospedalemarialuigia.it/sitemap_index.xml

# Crawl da file locale (sitemap scaricata)
python -m mnemosyne crawl ./sitemap.xml

# Con opzioni
python -m mnemosyne crawl <sitemap> --workers 3 --delay 1.0 --check-external

# Vedere risultati dell'ultimo crawl in CLI
python -m mnemosyne crawl --report

# Vedere storico crawl
python -m mnemosyne crawl --history
```

**Integrazione in `__main__.py`:**

```python
elif command == "crawl":
    from mnemosyne.crawler.engine import CrawlEngine

    if "--report" in sys.argv:
        from mnemosyne.crawler.report import print_cli_report
        print_cli_report(conn)
    elif "--history" in sys.argv:
        from mnemosyne.crawler.report import print_history
        print_history(conn)
    else:
        sitemap_source = sys.argv[2]
        workers = int(get_flag("--workers", 5))
        delay = float(get_flag("--delay", 0.5))
        check_ext = "--check-external" in sys.argv

        engine = CrawlEngine(conn, sitemap_source,
                             max_workers=workers, delay=delay,
                             check_external_links=check_ext)
        run_id = engine.run()
        print(f"\nCrawl completato! Run ID: {run_id}")
        print("Apri la dashboard per i risultati dettagliati.")
```

---

## 7. Dipendenze aggiuntive

Nessuna nuova dipendenza necessaria! Tutto si fa con quello che c'è già:

| Cosa serve | Libreria | Già in requirements? |
|-----------|----------|---------------------|
| HTTP requests | `requests` | ✅ |
| HTML parsing | `beautifulsoup4` | ✅ |
| XML parsing | `xml.etree.ElementTree` | ✅ (stdlib) |
| Concorrenza | `concurrent.futures` | ✅ (stdlib) |
| Grafici | `plotly` | ✅ |
| Tabelle | `pandas` | ✅ |
| Database | `sqlite3` | ✅ (stdlib) |
| Dashboard | `streamlit` | ✅ |

---

## 8. Politeness e limiti

Per non sovraccaricare il server (anche se è il nostro):

- **Max 5 worker** simultanei (default, configurabile)
- **0.5s delay** tra richieste dallo stesso thread
- **User-Agent** identificabile: `MnemosyneBot/1.0`
- **Rispetta robots.txt** (parse e verifica regole)
- **HEAD request** per link esterni (non GET completo)
- **Timeout 10s** per pagina
- **Nessun JavaScript rendering** — il crawler è HTML-only (come Screaming Frog in modalità default)

---

## 9. Integrazione con dati esistenti

Il crawler può arricchire l'analisi incrociando dati che Mnemosyne ha già:

| Dato esistente | Uso nel crawler |
|----------------|-----------------|
| `posts.url` | Cross-ref: URL in sitemap che corrispondono a post nel DB |
| `posts.meta_description` | Confronto: meta dal DB vs meta dal crawl live |
| `internal_links` | Confronto: link dal parsing WP vs link trovati nel crawl |
| `embeddings` | Rilevamento contenuti duplicati (cosine similarity) |
| GA4/GSC data | Prioritizzare le issue: un 404 su una pagina con molto traffico è più grave |

Questo cross-referencing è **opzionale** e avviene nel post-processing, non rallenta il crawl.

---

## 10. Ordine di implementazione suggerito

### Fase 1 — Core (MVP)
1. Tabelle DB (`schema.py` migration)
2. `sitemap.py` — parsing sitemap
3. `fetcher.py` — HTTP fetcher
4. `analyzers/http_check.py` — status code e redirect
5. `analyzers/onpage.py` — title, meta, H1, canonical
6. `engine.py` — orchestratore base
7. CLI `crawl` command
8. Test unitari per ogni componente

### Fase 2 — Analisi completa
9. `analyzers/images.py`
10. `analyzers/links.py`
11. `analyzers/content.py`
12. `analyzers/resources.py`
13. Rilevamento duplicati (post-processing)
14. Verifica link esterni (HEAD)

### Fase 3 — Dashboard
15. `report.py` — grafici per dashboard_charts
16. `6_site_crawler.py` — pagina Streamlit
17. Export CSV
18. Cross-reference con dati esistenti

### Fase 4 — Polish
19. Progress bar live (crawl scrive progresso in DB, dashboard lo mostra)
20. Confronto tra crawl successivi (diff)
21. Prioritizzazione issue con dati GA4/GSC

---

## 11. Struttura file finale

```
mnemosyne/
├── crawler/
│   ├── __init__.py
│   ├── sitemap.py
│   ├── fetcher.py
│   ├── engine.py
│   ├── report.py
│   └── analyzers/
│       ├── __init__.py
│       ├── http_check.py
│       ├── onpage.py
│       ├── images.py
│       ├── links.py
│       ├── content.py
│       └── resources.py
├── dashboard/
│   └── pages/
│       └── 6_site_crawler.py    ← NUOVO
├── db/
│   └── schema.py                ← MIGRATION per nuove tabelle
└── __main__.py                  ← NUOVO comando "crawl"
```

---

## 12. Note finali

- Il crawler **non usa API Anthropic** — rispetta la regola #1 del CLAUDE.md
- Il crawler **non scrive su WordPress** — rispetta la regola #2
- I dati del crawl vivono nel DB locale — rispetta la regola #3
- L'architettura CLI → SQLite → Streamlit è identica al resto del progetto
- Nessuna dipendenza nuova da installare
