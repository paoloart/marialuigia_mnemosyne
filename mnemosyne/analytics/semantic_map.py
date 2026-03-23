"""Generate semantic analysis charts and push to dashboard_charts.

Usage:
    PYTHONPATH=. python -m mnemosyne.analytics.semantic_map

Requires: embeddings in DB, GSC/GA4 credentials.
"""

import html
import json
import os
import sqlite3

import numpy as np
import plotly.graph_objects as go
import umap
from collections import Counter
from datetime import datetime, timezone
from sklearn.cluster import KMeans
from urllib.parse import urlparse

from mnemosyne.config import get_db_path
from mnemosyne.dashboard import ga4_client, gsc_client
from mnemosyne.dashboard.chart_store import ensure_table

CLUSTER_NAMES = {
    0: "Psicoterapia — ACT, Schema Therapy, CBT",
    1: "Disturbi Alimentari e Immagine Corporea",
    2: "News, Congressi e Vita Ospedaliera",
    3: "Corsi Leaves e Centro Mindfulness",
    4: "Psicopatologia — Ansia, Umore, Personalità, Trauma",
}

CLUSTER_COLORS = {
    0: "#4ecdc4",
    1: "#ff6b6b",
    2: "#85c1e9",
    3: "#f7dc6f",
    4: "#bb8fce",
}

CREDS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "ospedalemarialuigia-1231-2501577589f1.json",
)


def _norm(v):
    a = np.array(v, dtype=np.float64)
    mx = a.max()
    return a / mx if mx > 0 else a


def generate_semantic_map(conn: sqlite3.Connection, creds_path: str = CREDS_PATH) -> dict:
    """Run full semantic analysis and insert charts into dashboard_charts.

    Returns a summary dict with cluster counts and cornerstone list.
    """
    ensure_table(conn)

    # ── Load data ─────────────────────────────────────────────────
    rows = conn.execute("""
        SELECT e.post_id, e.vector, p.title, p.url, p.word_count,
               (SELECT c.name FROM post_categories pc
                JOIN categories c ON c.id = pc.category_id
                WHERE pc.post_id = p.id LIMIT 1) as category,
               (SELECT COUNT(*) FROM internal_links il WHERE il.target_post_id = p.id) as links_in,
               (SELECT COUNT(*) FROM internal_links il WHERE il.source_post_id = p.id) as links_out
        FROM embeddings e JOIN posts p ON p.id = e.post_id
    """).fetchall()

    if not rows:
        print("No embeddings found.")
        return {"error": "no embeddings"}

    titles = [html.unescape(r["title"][:55]) for r in rows]
    urls = [r["url"] for r in rows]
    word_counts = [r["word_count"] or 0 for r in rows]
    categories = [r["category"] or "Senza categoria" for r in rows]
    links_in = [r["links_in"] for r in rows]
    links_out = [r["links_out"] for r in rows]
    vectors = np.array([np.frombuffer(r["vector"], dtype=np.float32) for r in rows])

    # Validate embeddings
    norms = np.linalg.norm(vectors, axis=1)
    bad = np.sum(~np.isfinite(norms))
    if bad > 0:
        print(f"WARNING: {bad} corrupted embeddings found. Regenerate first.")
        return {"error": f"{bad} corrupted embeddings"}

    print(f"Loaded {len(rows)} embeddings, all valid.")

    # ── Analytics data ────────────────────────────────────────────
    gsc_clicks, gsc_impressions, ga4_pageviews = [], [], []
    try:
        gsc_map = {p["page"]: p for p in gsc_client.get_top_pages(creds_path=creds_path, days=90, limit=200)}
        ga4_map = {p["page_path"]: p for p in ga4_client.get_top_pages(creds_path=creds_path, days=90, limit=200)}
        print(f"GSC: {len(gsc_map)} pages, GA4: {len(ga4_map)} pages")
    except Exception as e:
        print(f"Analytics unavailable ({e}), using zeros.")
        gsc_map, ga4_map = {}, {}

    for r in rows:
        gsc = gsc_map.get(r["url"], {})
        gsc_clicks.append(gsc.get("clicks", 0))
        gsc_impressions.append(gsc.get("impressions", 0))
        ga4 = ga4_map.get(urlparse(r["url"]).path, {})
        ga4_pageviews.append(ga4.get("pageviews", 0))

    # ── Cornerstone scoring ───────────────────────────────────────
    composite = (
        0.15 * _norm(word_counts)
        + 0.25 * _norm(links_in)
        + 0.10 * _norm(links_out)
        + 0.20 * _norm(gsc_clicks)
        + 0.15 * _norm(gsc_impressions)
        + 0.15 * _norm(ga4_pageviews)
    )
    threshold = max(np.percentile(composite, 85), 0.3)
    is_cornerstone = composite >= threshold
    n_cs = int(sum(is_cornerstone))
    print(f"Cornerstone: {n_cs} (threshold={threshold:.3f})")

    # ── UMAP + KMeans(5) ─────────────────────────────────────────
    reducer = umap.UMAP(n_neighbors=12, min_dist=0.05, metric="cosine", random_state=42)
    umap_coords = reducer.fit_transform(vectors)

    km = KMeans(n_clusters=5, random_state=42, n_init=10)
    cluster_labels = km.fit_predict(umap_coords)
    print("UMAP + KMeans done.")

    # ── Build plots ───────────────────────────────────────────────
    max_lin = max(links_in) if max(links_in) > 0 else 1
    node_sizes = [6 + (li / max_lin) * 29 for li in links_in]

    # Main scatter
    fig = go.Figure()
    for c in range(5):
        idx = [i for i, l in enumerate(cluster_labels) if l == c and not is_cornerstone[i]]
        if not idx:
            continue
        fig.add_trace(go.Scatter(
            x=[umap_coords[i, 0] for i in idx],
            y=[umap_coords[i, 1] for i in idx],
            mode="markers", name=CLUSTER_NAMES[c],
            hovertext=[
                f"<b>{titles[i]}</b><br>{categories[i]}<br>"
                f"{word_counts[i]}w | In:{links_in[i]} Out:{links_out[i]}<br>"
                f"Clicks:{gsc_clicks[i]} | PV:{ga4_pageviews[i]}<br>"
                f"Score: {composite[i]:.3f}"
                for i in idx
            ],
            hoverinfo="text",
            marker=dict(size=[node_sizes[i] for i in idx],
                        color=CLUSTER_COLORS[c], opacity=0.6, line=dict(width=0)),
            legendgroup=CLUSTER_NAMES[c],
        ))

    cs_idx = [i for i in range(len(rows)) if is_cornerstone[i]]
    fig.add_trace(go.Scatter(
        x=[umap_coords[i, 0] for i in cs_idx],
        y=[umap_coords[i, 1] for i in cs_idx],
        mode="markers", name=f"CORNERSTONE ({n_cs})",
        hovertext=[
            f"<b>⭐ {titles[i]}</b><br>{categories[i]}<br>"
            f"{word_counts[i]}w | In:{links_in[i]} Out:{links_out[i]}<br>"
            f"Clicks:{gsc_clicks[i]} | PV:{ga4_pageviews[i]}<br>"
            f"<b>Score: {composite[i]:.3f}</b>"
            for i in cs_idx
        ],
        hoverinfo="text",
        marker=dict(
            size=[node_sizes[i] * 1.2 for i in cs_idx],
            color=[CLUSTER_COLORS[cluster_labels[i]] for i in cs_idx],
            line=dict(width=3, color="#ffd700"), opacity=1.0,
        ),
    ))

    fig.update_layout(
        title=dict(text=f"Cornerstone Content Map — {n_cs} pillar, 5 macro-aree",
                   font=dict(size=16, color="#e6edf3")),
        showlegend=True,
        legend=dict(font=dict(size=10, color="#8b949e"), bgcolor="rgba(0,0,0,0)"),
        hovermode="closest",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=800,
        annotations=[dict(
            text="Dimensione = link in entrata | Bordo oro = cornerstone",
            xref="paper", yref="paper", x=0.01, y=-0.02,
            showarrow=False, font=dict(size=11, color="#8b949e"),
        )],
    )

    # Heatmap
    all_cats = sorted(set(categories))
    matrix = np.zeros((5, len(all_cats)))
    for i, l in enumerate(cluster_labels):
        matrix[l, all_cats.index(categories[i])] += 1

    fig_heat = go.Figure(data=go.Heatmap(
        z=matrix, x=all_cats, y=[CLUSTER_NAMES[c] for c in range(5)],
        colorscale=[[0, "#0e1117"], [0.5, "#1a4a3a"], [1, "#00d4aa"]],
        text=matrix.astype(int), texttemplate="%{text}",
        textfont=dict(size=10, color="#e6edf3"),
    ))
    fig_heat.update_layout(
        title=dict(text="5 Macro-aree vs Categorie WordPress",
                   font=dict(size=16, color="#e6edf3")),
        xaxis=dict(tickangle=45, color="#8b949e", tickfont=dict(size=8)),
        yaxis=dict(color="#8b949e", tickfont=dict(size=9)),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        height=400, margin=dict(l=300),
    )

    # Cluster table
    cluster_data = []
    for c in range(5):
        idx = [i for i, l in enumerate(cluster_labels) if l == c]
        cat_counts = Counter(categories[i] for i in idx)
        top_cats = ", ".join(f"{cat} ({cnt})" for cat, cnt in cat_counts.most_common(3))
        cluster_data.append({
            "Macro-area": CLUSTER_NAMES[c],
            "Post": len(idx),
            "Cornerstone": sum(1 for i in idx if is_cornerstone[i]),
            "Parole medie": int(np.mean([word_counts[i] for i in idx])),
            "Click totali (90g)": sum(gsc_clicks[i] for i in idx),
            "Categorie WP": top_cats,
        })

    # Cornerstone table
    cs_data = []
    for i in sorted(cs_idx, key=lambda i: -composite[i]):
        cs_data.append({
            "Titolo": titles[i],
            "Macro-area": CLUSTER_NAMES[cluster_labels[i]],
            "Parole": word_counts[i],
            "Link In": links_in[i],
            "Clicks 90g": gsc_clicks[i],
            "PV 90g": ga4_pageviews[i],
            "Score": f"{composite[i]:.3f}",
        })

    # ── Push to dashboard_charts ──────────────────────────────────
    # Clean old
    conn.execute(
        "DELETE FROM dashboard_charts WHERE title LIKE '%Cornerstone%' "
        "OR title LIKE '%cornerstone%' OR title LIKE '%Cluster%' "
        "OR title LIKE '%Macro%' OR title LIKE '%Mappa Semantica%' "
        "OR title LIKE '%Analisi Semantica%' OR title LIKE '%Silhouette%'"
    )

    now = datetime.now(timezone.utc).isoformat()
    for title, ctype, data in [
        (f"Cornerstone Map — {n_cs} pillar, 5 macro-aree", "plotly_json", fig.to_json()),
        ("5 Macro-aree vs Categorie WP", "plotly_json", fig_heat.to_json()),
        (f"Cornerstone Content ({n_cs} post)", "table", json.dumps(cs_data, ensure_ascii=False)),
        ("5 Macro-aree Semantiche", "table", json.dumps(cluster_data, ensure_ascii=False)),
    ]:
        conn.execute(
            "INSERT INTO dashboard_charts (title, chart_type, data_json, created_at, pinned) "
            "VALUES (?, ?, ?, ?, ?)",
            (title, ctype, data, now, 1),
        )
    conn.commit()

    print(f"4 charts pushed to Live Canvas.")
    return {
        "cornerstone_count": n_cs,
        "cluster_counts": {CLUSTER_NAMES[c]: int(sum(1 for l in cluster_labels if l == c)) for c in range(5)},
        "cornerstone_posts": cs_data,
    }


if __name__ == "__main__":
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    result = generate_semantic_map(conn)
    conn.close()
    print(f"\nDone. {result.get('cornerstone_count', 0)} cornerstone identified.")
