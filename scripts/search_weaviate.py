import os
import argparse
import json
import weaviate
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

# ---- env ----
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=ENV_PATH)

WEAVIATE_HOST = os.getenv("WEAVIATE_HOST", "localhost")
WEAVIATE_PORT = int(os.getenv("WEAVIATE_PORT", "8080"))
WEAVIATE_GRPC = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))
CLASS_NAME    = os.getenv("WEAVIATE_CLASS", "ConfluenceChunk")

MODEL_PATH = os.getenv("MODEL_PATH")  # 例: ./phase2/models/bge-m3
MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "BAAI/bge-m3")

# device
try:
    import torch  # noqa
    DEVICE = "cuda" if getattr(torch, "cuda", None) and torch.cuda.is_available() else "cpu"
except Exception:
    DEVICE = "cpu"

def get_model():
    path = MODEL_PATH if MODEL_PATH else MODEL_NAME
    print(f"[INFO] load model {path} (device={DEVICE})")
    return SentenceTransformer(path, device=DEVICE)

def embed_query(text: str):
    model = get_model()
    vec = model.encode([f"query: {text}"], normalize_embeddings=True)[0]
    return vec.tolist()

def near_vector_compat(coll, vec, k):
    """weaviate-client v4.6.0 / v4.16 どちらでも動くように引数名を切替"""
    try:
        # 4.x 系で共通の型
        from weaviate.classes.query import MetadataQuery
    except Exception:
        MetadataQuery = None

    kwargs_base = dict(
        limit=k,
        return_properties=["pageId", "title", "chunkIndex", "url", "content"],
        include_vector=False,
    )

    # まずは v4.6.0 互換（near_vector= / return_metadata=）
    try:
        if MetadataQuery:
            return coll.query.near_vector(
                near_vector=vec,
                return_metadata=MetadataQuery(distance=True),
                **kwargs_base,
            )
        else:
            return coll.query.near_vector(near_vector=vec, **kwargs_base)
    except TypeError:
        # 新しめのAPI（vector= / metadata=）にフォールバック
        if MetadataQuery:
            return coll.query.near_vector(
                vector=vec,
                metadata=MetadataQuery(distance=True),
                **kwargs_base,
            )
        else:
            return coll.query.near_vector(vector=vec, **kwargs_base)

def search_with_client(query: str, k: int = 5):
    vec = embed_query(query)
    client = weaviate.connect_to_local(host=WEAVIATE_HOST, port=WEAVIATE_PORT, grpc_port=WEAVIATE_GRPC)
    try:
        coll = client.collections.get(CLASS_NAME)
        res = near_vector_compat(coll, vec, k)
        return res
    finally:
        client.close()

def main():
    ap = argparse.ArgumentParser(description="Vector search against Weaviate (ConfluenceChunk)")
    ap.add_argument("query", nargs="*", help="検索クエリ（例: SQL の実行方法）")
    ap.add_argument("-k", "--limit", type=int, default=5, help="返す件数")
    ap.add_argument("--raw", action="store_true", help="生JSONを出力")
    args = ap.parse_args()

    q = " ".join(args.query) if args.query else "SQL の実行方法"
    print(f"[INFO] query: {q}  (k={args.limit})")

    res = search_with_client(q, k=args.limit)
    objs = getattr(res, "objects", []) or []

    if args.raw:
        payload = {
            "objects": [
                {
                    "id": o.uuid,
                    "properties": o.properties,
                    # v4.6 は o.metadata.distance が入る想定（ない場合は None）
                    "distance": getattr(getattr(o, "metadata", None), "distance", None),
                }
                for o in objs
            ]
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    if not objs:
        print("(no results)")
        return

    for i, o in enumerate(objs, 1):
        p = o.properties or {}
        dist = getattr(getattr(o, "metadata", None), "distance", None)
        head = (p.get("content") or "").replace("\n", " ")[:120]
        print(f"{i}. {p.get('title')}  (pageId={p.get('pageId')}, chunk={p.get('chunkIndex')}, dist={dist})")
        print(f"   {head} ...")
        if p.get("url"):
            print(f"   {p['url']}")

if __name__ == "__main__":
    main()
