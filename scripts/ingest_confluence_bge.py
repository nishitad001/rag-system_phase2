# phase2/scripts/ingest_confluence_bge.py
import os
import re
import time
import uuid
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# ==== ENV ====
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=ENV_PATH)

CONF_BASE_URL = os.environ["CONF_BASE_URL"].rstrip("/")
CONF_EMAIL = os.environ["CONF_EMAIL"]
CONF_API_TOKEN = os.environ["CONF_API_TOKEN"]
CONF_PAGE_IDS = [x.strip() for x in os.environ.get("CONF_PAGE_IDS", "").split(",") if x.strip()]

WEAVIATE_URL = os.environ["WEAVIATE_URL"].rstrip("/")
WEAVIATE_API_KEY = os.environ.get("WEAVIATE_API_KEY") or None
CLASS_NAME = os.environ.get("WEAVIATE_CLASS", "ConfluenceChunk")

MODEL_PATH = os.environ.get("MODEL_PATH")  # 例: ./phase2/models/bge-m3
MODEL_NAME = os.environ.get("EMBED_MODEL_NAME", "BAAI/bge-m3")

# ==== PARAMS ====
CHARS_PER_CHUNK = 1200
CHUNK_OVERLAP = 200
BATCH_SIZE = 16

# device 判定（CUDA が無ければ自動で CPU）
try:
    import torch  # noqa: F401
    DEVICE = "cuda" if getattr(torch, "cuda", None) and torch.cuda.is_available() else "cpu"
except Exception:
    DEVICE = "cpu"


# ==== HTTP with retry ====
def req_retry(method, url, **kwargs):
    backoff = 1.0
    for _ in range(6):
        r = requests.request(method, url, timeout=60, **kwargs)
        if r.status_code in (429, 502, 503, 504):
            time.sleep(backoff)
            backoff = min(backoff * 2, 16)
            continue
        if r.status_code >= 400:
            try:
                body = r.text[:800]
                print(f"[ERR] {r.status_code} {method} {url} -> {body}")
            except Exception:
                pass
            r.raise_for_status()
        return r
    r.raise_for_status()


# ==== Confluence ====
def get_page(page_id: str):
    url = f"{CONF_BASE_URL}/rest/api/content/{page_id}"
    params = {"expand": "body.storage,version,ancestors,metadata.labels"}
    r = req_retry(
        "GET",
        url,
        auth=(CONF_EMAIL, CONF_API_TOKEN),
        headers={"Accept": "application/json"},
        params=params,
    )
    return r.json()


def storage_html_to_text(storage_html: str) -> str:
    """
    Confluence storage(XHTML) -> プレーンテキスト。
    コードブロックの <ac:plain-text-body><![CDATA[...]]></ac:plain-text-body> を
    事前に <pre>...</pre> に置換してからパース。
    """
    html = storage_html or ""

    # CDATA のコード部分を <pre> に展開
    html = re.sub(
        r"<ac:plain-text-body><!\[CDATA\[(.*?)\]\]></ac:plain-text-body>",
        lambda m: f"<pre>{m.group(1)}</pre>",
        html,
        flags=re.S,
    )

    soup = BeautifulSoup(html, "html5lib")
    text = soup.get_text("\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


# ==== Chunking ====
def chunk_text(txt: str, size=CHARS_PER_CHUNK, overlap=CHUNK_OVERLAP):
    txt = (txt or "").strip()
    if not txt:
        return []
    out, i, n = [], 0, len(txt)
    while i < n:
        j = min(n, i + size)
        out.append(txt[i:j])
        if j == n:
            break
        i = max(j - overlap, 0)
    return out


# ==== Embedding (bge-m3 dense only) ====
_model = None


def get_model():
    global _model
    if _model is None:
        path = MODEL_PATH if MODEL_PATH else MODEL_NAME
        print(f"[INFO] load model {path} (device={DEVICE})")
        _model = SentenceTransformer(path, device=DEVICE)
    return _model


def embed_dense_passages(passages):
    m = get_model()
    out, buf = [], []
    for t in passages:
        buf.append(f"passage: {t}")
        if len(buf) == BATCH_SIZE:
            vec = m.encode(buf, normalize_embeddings=True).tolist()
            out.extend(vec)
            buf = []
    if buf:
        vec = m.encode(buf, normalize_embeddings=True).tolist()
        out.extend(vec)
    return out


# ==== Weaviate upsert (v1系用) ====
def upsert_chunk(obj_id: str, props: dict, vec):
    headers = {"Content-Type": "application/json"}
    if WEAVIATE_API_KEY:
        headers["Authorization"] = f"Bearer {WEAVIATE_API_KEY}"

    # まず古いのを削除（存在しなくても無視）
    try:
        requests.delete(
            f"{WEAVIATE_URL}/v1/objects/{obj_id}",
            headers=headers,
            params={"class": CLASS_NAME},
            timeout=20,
        )
    except Exception:
        pass

    # 新規作成 (v1系は vector フィールドのみ)
    create = {
        "id": obj_id,
        "class": CLASS_NAME,
        "properties": props,
        "vector": vec,
    }
    r = requests.post(f"{WEAVIATE_URL}/v1/objects", headers=headers, json=create, timeout=60)

    if r.status_code >= 400:
        print(f"[ERR] upsert failed {r.status_code}: {r.text[:800]}")
        r.raise_for_status()


def deterministic_uuid(page_id: str, idx: int) -> str:
    ns = uuid.uuid5(uuid.NAMESPACE_URL, f"confluence:{page_id}")
    return str(uuid.uuid5(ns, f"chunk:{idx}"))


# ==== Main ingest ====
def ingest_page(page_id: str):
    print(f"[INFO] fetch {page_id}")
    data = get_page(page_id)
    title = data.get("title", "")
    storage_html = data.get("body", {}).get("storage", {}).get("value", "") or ""
    updated_at = data.get("version", {}).get("when")
    webui = data.get("_links", {}).get("webui")
    url = f"{CONF_BASE_URL}{webui}" if webui and webui.startswith("/") else webui

    text = storage_html_to_text(storage_html)
    chunks = chunk_text(text)
    if not chunks:
        print(f"[WARN] no text for {page_id}")
        return

    print(f"[INFO] embed {len(chunks)} chunks (bge-m3)")
    vecs = embed_dense_passages(chunks)

    for v in vecs:
        if len(v) != 1024:
            raise RuntimeError(f"unexpected embedding dim: {len(v)} (expected 1024)")

    for i, (chunk, vec) in enumerate(zip(chunks, vecs)):
        obj_id = deterministic_uuid(page_id, i)
        props = {
            "pageId": page_id,
            "title": title,
            "url": url,
            "updatedAt": updated_at,
            "content": chunk,
            "chunkIndex": i,
        }
        upsert_chunk(obj_id, props, vec)
    print(f"[OK] upserted {len(chunks)} chunks for {page_id} ({title})")


if __name__ == "__main__":
    if not CONF_PAGE_IDS:
        raise SystemExit("CONF_PAGE_IDS 未設定（例: 98439,360449）")
    for pid in CONF_PAGE_IDS:
        ingest_page(pid)
