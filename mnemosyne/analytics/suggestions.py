"""Generate actionable suggestions and store them in the suggestions table.

Suggestion types:
- add_link: post A should link to post B
- refresh_content: post needs updating (low traffic, old, thin)
- boost_cornerstone: cornerstone not linked from its cluster
"""

import html
import json
import os
import sqlite3
from datetime import datetime, timezone

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics.pairwise import cosine_similarity
from urllib.parse import urlparse
import umap

from mnemosyne.config import get_db_path

CREDS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "ospedalemarialuigia-1231-2501577589f1.json",
)


def _norm(v):
    a = np.array(v, dtype=np.float64)
    mx = a.max()
    return a / mx if mx > 0 else a


def _ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            priority TEXT NOT NULL DEFAULT 'media',
            post_id INTEGER,
            post_title TEXT,
            post_url TEXT,
            target_post_id INTEGER,
            target_title TEXT,
            target_url TEXT,
            reason TEXT NOT NULL,
            data_json TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            dismissed_at TEXT
        )
    """)
    conn.commit()


def _insert(conn, stype, priority, post_id, post_title, post_url,
            target_post_id, target_title, target_url, reason, data=None):
    conn.execute(
        "INSERT INTO suggestions (type, priority, post_id, post_title, post_url, "
        "target_post_id, target_title, target_url, reason, data_json, status, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (stype, priority, post_id, post_title, post_url,
         target_post_id, target_title, target_url, reason,
         json.dumps(data, ensure_ascii=False) if data else None,
         "pending", datetime.now(timezone.utc).isoformat()),
    )


def generate_suggestions(conn: sqlite3.Connection, creds_path: str = CREDS_PATH) -> int:
    """Generate all suggestions. Returns count of new suggestions."""
    _ensure_table(conn)

    # Clear old pending suggestions (keep dismissed ones)
    conn.execute("DELETE FROM suggestions WHERE status = 'pending'")
    conn.commit()

    # ── Load data ─────────────────────────────────────────────────
    rows = conn.execute("""
        SELECT e.post_id, e.vector, p.title, p.url, p.word_count,
               p.date_published, p.date_modified,
               (SELECT c.name FROM post_categories pc
                JOIN categories c ON c.id = pc.category_id
                WHERE pc.post_id = p.id LIMIT 1) as category,
               (SELECT COUNT(*) FROM internal_links il WHERE il.target_post_id = p.id) as links_in,
               (SELECT COUNT(*) FROM internal_links il WHERE il.source_post_id = p.id) as links_out
        FROM embeddings e JOIN posts p ON p.id = e.post_id
    """).fetchall()

    if not rows:
        return 0

    post_ids = [r['post_id'] for r in rows]
    titles = [html.unescape(r['title'][:60]) for r in rows]
    urls = [r['url'] for r in rows]
    word_counts = [r['word_count'] or 0 for r in rows]
    dates_pub = [r['date_published'] for r in rows]
    dates_mod = [r['date_modified'] for r in rows]
    links_in = [r['links_in'] for r in rows]
    links_out = [r['links_out'] for r in rows]
    vectors = np.array([np.frombuffer(r['vector'], dtype=np.float32) for r in rows])
    id_to_idx = {pid: i for i, pid in enumerate(post_ids)}

    # Existing links
    raw_links = conn.execute(
        "SELECT source_post_id, target_post_id FROM internal_links WHERE target_post_id IS NOT NULL"
    ).fetchall()
    existing_links = set()
    for l in raw_links:
        si = id_to_idx.get(l['source_post_id'])
        ti = id_to_idx.get(l['target_post_id'])
        if si is not None and ti is not None:
            existing_links.add((si, ti))

    # Analytics
    try:
        from mnemosyne.dashboard import gsc_client, ga4_client
        gsc_map = {p['page']: p for p in gsc_client.get_top_pages(creds_path=creds_path, days=90, limit=200)}
        ga4_map = {p['page_path']: p for p in ga4_client.get_top_pages(creds_path=creds_path, days=90, limit=200)}
    except Exception:
        gsc_map, ga4_map = {}, {}

    gsc_clicks = [gsc_map.get(r['url'], {}).get('clicks', 0) for r in rows]
    gsc_impressions = [gsc_map.get(r['url'], {}).get('impressions', 0) for r in rows]
    ga4_pageviews = [ga4_map.get(urlparse(r['url']).path, {}).get('pageviews', 0) for r in rows]

    # Cornerstone
    composite = (0.15 * _norm(word_counts) + 0.25 * _norm(links_in) + 0.10 * _norm(links_out) +
                 0.20 * _norm(gsc_clicks) + 0.15 * _norm(gsc_impressions) + 0.15 * _norm(ga4_pageviews))
    threshold = max(np.percentile(composite, 85), 0.3)
    is_cornerstone = composite >= threshold

    # Clustering
    reducer = umap.UMAP(n_neighbors=12, min_dist=0.05, metric='cosine', random_state=42)
    umap_coords = reducer.fit_transform(vectors)
    km = KMeans(n_clusters=5, random_state=42, n_init=10)
    cluster_labels = km.fit_predict(umap_coords)

    sim_matrix = cosine_similarity(vectors)

    count = 0
    now_year = datetime.now().year

    # ═════════════════════════════════════════════════════════════════
    # TYPE 1: add_link — orphan posts need incoming links
    # ═════════════════════════════════════════════════════════════════
    for i in range(len(rows)):
        if links_in[i] > 0:
            continue
        sims = sim_matrix[i].copy()
        sims[i] = 0
        best_j = int(np.argmax(sims))
        if sims[best_j] < 0.3:
            continue
        _insert(conn, 'add_link', 'alta', post_ids[best_j], titles[best_j], urls[best_j],
                post_ids[i], titles[i], urls[i],
                f"Post orfano (0 link in entrata). Il post più simile (sim={sims[best_j]:.2f}) potrebbe linkarlo.",
                {'similarity': float(sims[best_j])})
        count += 1

    # ═════════════════════════════════════════════════════════════════
    # TYPE 2: add_link — cornerstone missing links from cluster
    # ═════════════════════════════════════════════════════════════════
    for i in range(len(rows)):
        if not is_cornerstone[i]:
            continue
        c = cluster_labels[i]
        for j in range(len(rows)):
            if j == i or cluster_labels[j] != c:
                continue
            if (j, i) in existing_links:
                continue
            if sim_matrix[i][j] < 0.4:
                continue
            _insert(conn, 'add_link', 'alta', post_ids[j], titles[j], urls[j],
                    post_ids[i], f"⭐ {titles[i]}", urls[i],
                    f"Cornerstone del cluster senza link da questo post (sim={sim_matrix[i][j]:.2f}).",
                    {'similarity': float(sim_matrix[i][j]), 'cornerstone': True})
            count += 1

    # ═════════════════════════════════════════════════════════════════
    # TYPE 3: add_link — same cluster, high similarity, no link
    # ═════════════════════════════════════════════════════════════════
    for c in range(5):
        members = [i for i, l in enumerate(cluster_labels) if l == c]
        for a_idx, a in enumerate(members):
            for b in members[a_idx + 1:]:
                if (a, b) in existing_links or (b, a) in existing_links:
                    continue
                s = sim_matrix[a][b]
                if s < 0.55:
                    continue
                priority = 'alta' if s > 0.7 else 'media'
                _insert(conn, 'add_link', priority, post_ids[a], titles[a], urls[a],
                        post_ids[b], titles[b], urls[b],
                        f"Post molto simili nello stesso cluster senza link reciproco (sim={s:.2f}).",
                        {'similarity': float(s)})
                count += 1

    # ═════════════════════════════════════════════════════════════════
    # TYPE 4: refresh_content — low traffic + old + enough content
    # ═════════════════════════════════════════════════════════════════
    for i in range(len(rows)):
        reasons = []
        data = {}

        # Low traffic despite having content
        if word_counts[i] > 500 and gsc_clicks[i] == 0 and gsc_impressions[i] == 0:
            reasons.append("Zero traffico organico (90gg) nonostante contenuto sostanzioso")
            data['zero_traffic'] = True

        # High impressions but low CTR (title/meta needs work)
        imp = gsc_map.get(urls[i], {}).get('impressions', 0)
        clicks = gsc_map.get(urls[i], {}).get('clicks', 0)
        if imp > 500 and clicks > 0 and (clicks / imp) < 0.01:
            reasons.append(f"CTR bassissimo ({clicks}/{imp} = {clicks/imp:.1%}) — title/meta da migliorare")
            data['low_ctr'] = True
            data['impressions'] = imp
            data['clicks'] = clicks

        # Old content (published > 3 years ago, not modified recently)
        try:
            pub_year = int(dates_pub[i][:4])
            mod_year = int(dates_mod[i][:4])
            if pub_year < now_year - 3 and mod_year < now_year - 1 and word_counts[i] > 300:
                reasons.append(f"Pubblicato nel {pub_year}, ultima modifica {mod_year}")
                data['old_content'] = True
                data['pub_year'] = pub_year
        except (ValueError, TypeError):
            pass

        # Thin content with some traffic potential
        if word_counts[i] < 500 and gsc_impressions[i] > 100:
            reasons.append(f"Contenuto sottile ({word_counts[i]} parole) ma con {gsc_impressions[i]} impressioni — espandere")
            data['thin_with_potential'] = True

        if not reasons:
            continue

        priority = 'alta' if len(reasons) >= 2 else 'media'
        _insert(conn, 'refresh_content', priority, post_ids[i], titles[i], urls[i],
                None, None, None,
                ' | '.join(reasons), data)
        count += 1

    conn.commit()
    print(f"Generated {count} suggestions.")
    return count
