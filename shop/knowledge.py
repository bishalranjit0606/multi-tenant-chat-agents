import hashlib
import math
import os
import re

from shop.db import connect

DIM = 1024
STOP_WORDS = {
    "the", "and", "for", "how", "you", "your", "what", "with",
    "this", "that", "are", "can", "does", "from", "about",
}


def _secret(name):
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return ""
    key = os.environ.get(name, "").strip()
    if not key or key == "replace-me":
        return ""
    return key


def groq_key():
    return _secret("GROQ_API_KEY")


def gemini_key():
    return _secret("GEMINI_API_KEY")


def word_stem(word):
    if len(word) > 5 and word.endswith("age"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 4 and word.endswith("ed"):
        return word[:-2]
    if len(word) > 4 and word.endswith("e"):
        return word[:-1]
    return word


def words_of(text):
    return [
        word_stem(word)
        for word in re.split(r"[^a-z0-9]+", str(text or "").lower())
        if len(word) > 2 and word not in STOP_WORDS
    ]


def hash_embed(text):
    vector = [0.0] * DIM
    for word in words_of(text):
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % DIM
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def chunk_text(row):
    title = f"{row['document']} {row['section']}"
    return f"{title} {title} {title} {title} {title} {row['text']}"


class LocalHashEmbedder:
    def __call__(self, texts):
        return [hash_embed(text) for text in texts]


def _unit(values):
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


def gemini_embed(texts):
    import httpx

    model = os.environ.get("GEMINI_EMBED_MODEL", "gemini-embedding-001")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
    vectors = []
    with httpx.Client(timeout=60) as client:
        for text in texts:
            response = client.post(
                url,
                headers={"x-goog-api-key": gemini_key()},
                json={
                    "content": {"parts": [{"text": text}]},
                    "output_dimensionality": DIM,
                },
            )
            response.raise_for_status()
            data = response.json()
            embedding = data.get("embedding") if isinstance(data, dict) else None
            values = embedding.get("values") if isinstance(embedding, dict) else None
            if not values:
                raise RuntimeError("Gemini did not return an embedding.")
            if len(values) != DIM:
                raise RuntimeError("Gemini embedding size does not match this shop.")
            vectors.append(_unit([float(value) for value in values]))
    return vectors


class GeminiEmbedder:
    def __call__(self, texts):
        return gemini_embed(texts)


def make_embedder():
    if gemini_key():
        return GeminiEmbedder()
    return LocalHashEmbedder()


def to_vector(values):
    return "[" + ",".join(f"{float(value):.8f}" for value in values) + "]"


def rebuild(path=None):
    from shop.db import seed_database

    seed_database(path)
    conn = connect(path)
    try:
        rows = conn.execute(
            "SELECT id, document, section, text FROM knowledge ORDER BY id"
        ).fetchall()
        embedder = make_embedder()
        for row in rows:
            text = chunk_text(row)
            vector = to_vector(embedder([text])[0])
            conn.execute(
                "UPDATE knowledge SET embedding = CAST(? AS vector) WHERE id = ?",
                (vector, row["id"]),
            )
        conn.commit()
    finally:
        conn.close()
    return path


def chunk_count(path=None):
    conn = connect(path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM knowledge WHERE embedding IS NOT NULL"
        ).fetchone()
    finally:
        conn.close()
    return row["n"]


def search_notes(org_id, query, path=None, limit=3):
    if not str(query or "").strip():
        return []
    vector = to_vector(make_embedder()([query])[0])
    conn = connect(path)
    try:
        rows = conn.execute(
            """
            SELECT document, section, text
            FROM (
                SELECT document, section, text, embedding <=> CAST(? AS vector) AS distance
                FROM knowledge
                WHERE org_id = ? AND embedding IS NOT NULL
            ) AS shop_rows
            WHERE distance < 1
            ORDER BY distance
            LIMIT ?
            """,
            (vector, org_id, limit),
        ).fetchall()
    finally:
        conn.close()
    return [
        {"document": row["document"], "section": row["section"], "text": row["text"]}
        for row in rows
    ]


def search_for_session(db_path, token, args=None):
    from shop.auth import session_for
    from shop.rules import fail

    session = session_for(db_path, token)
    if not session:
        return fail("logged_out", "Log in first.")
    query = str((args or {}).get("query") or (args or {}).get("text") or "")
    return {"ok": True, "matches": search_notes(session["orgId"], query, db_path)}


if __name__ == "__main__":
    print(rebuild())
