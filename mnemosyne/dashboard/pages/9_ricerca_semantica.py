"""Pagina dashboard: Ricerca Semantica — trova articoli simili via cosine similarity."""

import sqlite3
import html

import numpy as np
import pandas as pd
import streamlit as st

from mnemosyne.config import get_db_path, get_openai_api_key


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _load_embeddings(conn):
    """Load all embeddings into memory. Cached per session."""
    rows = conn.execute("""
        SELECT e.post_id, e.vector, p.title, p.url, p.word_count
        FROM embeddings e JOIN posts p ON e.post_id = p.id
    """).fetchall()
    data = []
    for r in rows:
        vec = np.frombuffer(r['vector'], dtype=np.float32)
        data.append({
            "post_id": r['post_id'],
            "title": html.unescape(r['title']),
            "url": r['url'],
            "word_count": r['word_count'],
            "vector": vec,
        })
    return data


def _cosine_search(query_vec: np.ndarray, embeddings: list[dict], exclude_id: int | None = None, top_k: int = 10) -> list[dict]:
    """Find top_k most similar articles by cosine similarity."""
    results = []
    for item in embeddings:
        if item['post_id'] == exclude_id:
            continue
        cosine = float(np.dot(query_vec, item['vector']))
        results.append({**item, "similarity": cosine})
    results.sort(key=lambda x: x['similarity'], reverse=True)
    return results[:top_k]


def _embed_text(text: str) -> np.ndarray | None:
    """Get embedding for a text query via OpenAI API."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=get_openai_api_key())
        resp = client.embeddings.create(
            input=text,
            model="text-embedding-3-large",
        )
        return np.array(resp.data[0].embedding, dtype=np.float32)
    except Exception as e:
        st.error(f"Errore OpenAI: {e}")
        return None


def page():
    st.markdown("### Ricerca Semantica")
    st.caption("Trova articoli simili usando gli embeddings. Cosine similarity su vettori text-embedding-3-large.")

    conn = _get_conn()

    # Load embeddings once per session
    if "embeddings_cache" not in st.session_state:
        st.session_state.embeddings_cache = _load_embeddings(conn)

    embeddings = st.session_state.embeddings_cache
    st.caption(f"{len(embeddings)} articoli con embedding disponibili")

    tab_post, tab_text = st.tabs(["Cerca per articolo", "Cerca per testo libero"])

    # ── Tab 1: Cerca per articolo (locale, zero API) ──────
    with tab_post:
        st.markdown("##### Seleziona un articolo e trova i più simili")
        st.caption("Nessuna chiamata API — tutto calcolato localmente.")

        post_options = {e['post_id']: f"{e['post_id']} — {e['title'][:60]}" for e in sorted(embeddings, key=lambda x: x['title'])}
        selected_id = st.selectbox("Articolo", options=list(post_options.keys()),
                                   format_func=lambda x: post_options[x],
                                   key="search_post_select")

        top_k = st.slider("Numero risultati", 5, 30, 10, key="search_post_topk")

        # Find selected vector
        selected_vec = None
        for e in embeddings:
            if e['post_id'] == selected_id:
                selected_vec = e['vector']
                break

        if selected_vec is not None:
            results = _cosine_search(selected_vec, embeddings, exclude_id=selected_id, top_k=top_k)
            _show_results(results)

    # ── Tab 2: Cerca per testo libero (1 chiamata API) ────
    with tab_text:
        st.markdown("##### Scrivi una query e trova gli articoli più pertinenti")
        st.caption("Richiede una chiamata API OpenAI per generare l'embedding della query.")

        query = st.text_input("Query", placeholder="es. trattamento anoressia adolescenti", key="search_text_input")
        top_k_text = st.slider("Numero risultati", 5, 30, 10, key="search_text_topk")

        if query:
            # Cache query embeddings to avoid re-calling API
            cache_key = f"query_emb_{query}"
            if cache_key not in st.session_state:
                with st.spinner("Generando embedding della query..."):
                    vec = _embed_text(query)
                    if vec is not None:
                        st.session_state[cache_key] = vec
                    else:
                        st.session_state[cache_key] = None

            query_vec = st.session_state.get(cache_key)
            if query_vec is not None:
                results = _cosine_search(query_vec, embeddings, top_k=top_k_text)
                _show_results(results)

    conn.close()


def _show_results(results: list[dict]):
    """Display search results as a table with similarity scores."""
    if not results:
        st.info("Nessun risultato.")
        return

    # Visual similarity bar
    max_sim = results[0]['similarity'] if results else 1
    min_sim = results[-1]['similarity'] if results else 0

    for i, r in enumerate(results):
        sim = r['similarity']
        sim_pct = (sim - min_sim) / (max_sim - min_sim) if max_sim != min_sim else 1.0

        if sim >= 0.8:
            color = "#00d4aa"
        elif sim >= 0.7:
            color = "#ffd93d"
        else:
            color = "#8b949e"

        cols = st.columns([0.06, 0.08, 0.56, 0.12, 0.18])
        with cols[0]:
            st.markdown(f"**{i+1}.**")
        with cols[1]:
            st.markdown(f'<span style="color:{color}; font-weight:700;">{sim:.3f}</span>', unsafe_allow_html=True)
        with cols[2]:
            st.markdown(f"**{r['title'][:55]}** ({r['word_count']} parole)")
        with cols[3]:
            st.markdown(f"`{r['post_id']}`")
        with cols[4]:
            st.link_button("Apri", r['url'], use_container_width=True)


# ── Run ───────────────────────────────────────────────────
page()
