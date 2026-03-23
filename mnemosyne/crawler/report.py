"""Genera grafici di report del crawl e li pusha in dashboard_charts."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

import plotly.express as px
import plotly.graph_objects as go

# ── Colori coerenti con la dashboard ──────────────────────

_COLORS = {
    "critical": "#ff6b6b",
    "warning": "#ffd93d",
    "info": "#6bcbff",
    "ok": "#00d4aa",
}

_CATEGORY_COLORS = {
    "http": "#ff6b6b",
    "onpage": "#ffa94d",
    "content": "#ffd93d",
    "images": "#a9e34b",
    "links": "#38d9a9",
    "resources": "#6bcbff",
    "sitemap": "#cc5de8",
}

_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#e6edf3"),
    margin=dict(l=40, r=20, t=50, b=30),
)


def generate_crawl_report(conn: sqlite3.Connection, run_id: int) -> int:
    """Genera tutti i grafici del crawl e li inserisce in dashboard_charts.
    Returns number of charts created."""

    # Pulisci grafici vecchi del crawler
    conn.execute("DELETE FROM dashboard_charts WHERE title LIKE 'Crawl:%'")

    now = datetime.now(timezone.utc).isoformat()
    charts = []

    # 1. Health Score (metric)
    score = _health_score(conn, run_id)
    charts.append(("Crawl: Health Score", "metric", json.dumps({
        "value": f"{score:.0f}%",
        "label": "Pagine senza issue critici",
        "delta": None,
    })))

    # 2. Issue counts (metric)
    counts = _issue_counts(conn, run_id)
    charts.append(("Crawl: Issue Summary", "metric", json.dumps({
        "value": str(counts["critical"]),
        "label": f"Critici: {counts['critical']} | Warning: {counts['warning']} | Info: {counts['info']}",
        "delta": None,
    })))

    # 3. Pie chart: distribuzione severità
    fig = _severity_pie(conn, run_id)
    if fig:
        charts.append(("Crawl: Distribuzione Severità", "plotly_json", fig.to_json()))

    # 4. Bar chart: issue per categoria
    fig = _issues_by_category(conn, run_id)
    if fig:
        charts.append(("Crawl: Issue per Categoria", "plotly_json", fig.to_json()))

    # 5. Bar chart: distribuzione status code
    fig = _status_code_distribution(conn, run_id)
    if fig:
        charts.append(("Crawl: Status Code", "plotly_json", fig.to_json()))

    # 6. Scatter: TTFB per pagina
    fig = _ttfb_scatter(conn, run_id)
    if fig:
        charts.append(("Crawl: TTFB per Pagina", "plotly_json", fig.to_json()))

    # 7. Tabella: top 20 issue critici
    table = _top_critical_issues(conn, run_id)
    if table:
        charts.append(("Crawl: Top Issue Critici", "table", json.dumps(table)))

    # Insert all
    for title, chart_type, data_json in charts:
        conn.execute(
            "INSERT INTO dashboard_charts (title, chart_type, data_json, created_at, pinned) VALUES (?, ?, ?, ?, ?)",
            (title, chart_type, data_json, now, 1),
        )
    conn.commit()

    return len(charts)


def _health_score(conn: sqlite3.Connection, run_id: int) -> float:
    """% di pagine senza issue critical."""
    total = conn.execute(
        "SELECT COUNT(*) FROM crawl_pages WHERE run_id = ?", (run_id,)
    ).fetchone()[0]
    if total == 0:
        return 100.0
    pages_with_critical = conn.execute(
        "SELECT COUNT(DISTINCT page_id) FROM crawl_issues WHERE run_id = ? AND severity = 'critical'",
        (run_id,),
    ).fetchone()[0]
    return ((total - pages_with_critical) / total) * 100


def _issue_counts(conn: sqlite3.Connection, run_id: int) -> dict[str, int]:
    rows = conn.execute(
        "SELECT severity, COUNT(*) FROM crawl_issues WHERE run_id = ? GROUP BY severity",
        (run_id,),
    ).fetchall()
    counts = {"critical": 0, "warning": 0, "info": 0}
    for sev, cnt in rows:
        counts[sev] = cnt
    return counts


def _severity_pie(conn: sqlite3.Connection, run_id: int) -> go.Figure | None:
    counts = _issue_counts(conn, run_id)
    if sum(counts.values()) == 0:
        return None

    labels = list(counts.keys())
    values = list(counts.values())
    colors = [_COLORS[l] for l in labels]

    fig = go.Figure(go.Pie(
        labels=[l.capitalize() for l in labels],
        values=values,
        marker=dict(colors=colors),
        hole=0.4,
        textinfo="value+percent",
        textfont=dict(size=13),
    ))
    fig.update_layout(
        title=dict(text="Distribuzione Issue per Severità", font=dict(size=15)),
        height=380,
        showlegend=True,
        **_LAYOUT,
    )
    return fig


def _issues_by_category(conn: sqlite3.Connection, run_id: int) -> go.Figure | None:
    rows = conn.execute(
        "SELECT category, COUNT(*) as cnt FROM crawl_issues WHERE run_id = ? GROUP BY category ORDER BY cnt DESC",
        (run_id,),
    ).fetchall()
    if not rows:
        return None

    categories = [r[0] for r in rows]
    counts = [r[1] for r in rows]
    colors = [_CATEGORY_COLORS.get(c, "#8b949e") for c in categories]

    fig = go.Figure(go.Bar(
        x=counts,
        y=categories,
        orientation="h",
        marker=dict(color=colors),
        text=counts,
        textposition="auto",
    ))
    fig.update_layout(
        title=dict(text="Issue per Categoria", font=dict(size=15)),
        height=350,
        yaxis=dict(autorange="reversed"),
        xaxis=dict(title="Conteggio"),
        **_LAYOUT,
    )
    return fig


def _status_code_distribution(conn: sqlite3.Connection, run_id: int) -> go.Figure | None:
    rows = conn.execute(
        "SELECT status_code, COUNT(*) as cnt FROM crawl_pages WHERE run_id = ? GROUP BY status_code ORDER BY status_code",
        (run_id,),
    ).fetchall()
    if not rows:
        return None

    codes = [str(r[0]) for r in rows]
    counts = [r[1] for r in rows]
    colors = []
    for r in rows:
        code = r[0]
        if code == 200:
            colors.append(_COLORS["ok"])
        elif 300 <= code < 400:
            colors.append(_COLORS["warning"])
        elif code >= 400:
            colors.append(_COLORS["critical"])
        else:
            colors.append("#8b949e")

    fig = go.Figure(go.Bar(
        x=codes,
        y=counts,
        marker=dict(color=colors),
        text=counts,
        textposition="auto",
    ))
    fig.update_layout(
        title=dict(text="Distribuzione Status Code", font=dict(size=15)),
        height=350,
        xaxis=dict(title="Status Code", type="category"),
        yaxis=dict(title="Pagine"),
        **_LAYOUT,
    )
    return fig


def _ttfb_scatter(conn: sqlite3.Connection, run_id: int) -> go.Figure | None:
    rows = conn.execute(
        "SELECT url, ttfb_ms FROM crawl_pages WHERE run_id = ? AND ttfb_ms IS NOT NULL ORDER BY ttfb_ms DESC",
        (run_id,),
    ).fetchall()
    if not rows:
        return None

    urls = [r[0].split("/")[-2] if r[0].endswith("/") else r[0].split("/")[-1] for r in rows]
    ttfbs = [r[1] for r in rows]
    colors = []
    for t in ttfbs:
        if t > 3000:
            colors.append(_COLORS["critical"])
        elif t > 1000:
            colors.append(_COLORS["warning"])
        else:
            colors.append(_COLORS["ok"])

    fig = go.Figure(go.Scatter(
        x=list(range(len(urls))),
        y=ttfbs,
        mode="markers",
        marker=dict(color=colors, size=6, opacity=0.7),
        text=[f"{u}: {t}ms" for u, t in zip(urls, ttfbs)],
        hoverinfo="text",
    ))
    fig.update_layout(
        title=dict(text="TTFB per Pagina (ms)", font=dict(size=15)),
        height=400,
        xaxis=dict(title="Pagine (ordinate per TTFB)", showticklabels=False),
        yaxis=dict(title="TTFB (ms)"),
        **_LAYOUT,
    )
    # Reference lines
    fig.add_hline(y=1000, line_dash="dot", line_color=_COLORS["warning"], opacity=0.5,
                  annotation_text="1s", annotation_font_color=_COLORS["warning"])
    fig.add_hline(y=3000, line_dash="dot", line_color=_COLORS["critical"], opacity=0.5,
                  annotation_text="3s", annotation_font_color=_COLORS["critical"])
    return fig


def _top_critical_issues(conn: sqlite3.Connection, run_id: int) -> list[dict] | None:
    rows = conn.execute(
        """SELECT check_name, message, url
           FROM crawl_issues
           WHERE run_id = ? AND severity = 'critical'
           ORDER BY check_name
           LIMIT 20""",
        (run_id,),
    ).fetchall()
    if not rows:
        return None
    return [{"check": r[0], "messaggio": r[1], "url": r[2]} for r in rows]
