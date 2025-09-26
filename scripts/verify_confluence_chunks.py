import os
import sys
import weaviate
from dotenv import load_dotenv
from weaviate.classes.query import Filter

# ---- env 読み込み（phase2/.env を明示）----
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
load_dotenv(dotenv_path=ENV_PATH)

CLASS_NAME = os.getenv("WEAVIATE_CLASS", "ConfluenceChunk")
HOST = os.getenv("WEAVIATE_HOST", "localhost")
PORT = int(os.getenv("WEAVIATE_PORT", "8080"))
GRPC_PORT = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))

# 使い方:
#   python phase2/scripts/verify_confluence_chunks.py
#   python phase2/scripts/verify_confluence_chunks.py 98439
TARGET_PAGE_ID = sys.argv[1] if len(sys.argv) > 1 else None


def main():
    client = weaviate.connect_to_local(host=HOST, port=PORT, grpc_port=GRPC_PORT)
    try:
        coll = client.collections.get(CLASS_NAME)

        # 1) 総件数
        agg = coll.aggregate.over_all(total_count=True)
        total = agg.total_count or 0
        print(f"== {CLASS_NAME} total objects: {total}")

        # 2) サンプル表示（最新10件）
        print("\n== sample objects (limit=10)")
        res = coll.query.fetch_objects(
            limit=10,
            return_properties=["pageId", "title", "chunkIndex", "updatedAt", "url"],
            include_vector=False,
        )
        for o in res.objects:
            p = o.properties
            print(f"- pageId={p.get('pageId')}  chunk={p.get('chunkIndex')}  title={p.get('title')}")
            print(f"  updatedAt={p.get('updatedAt')}  url={p.get('url')}\n")

        # 3) 特定 pageId の全チャンク（指定があれば）
        if TARGET_PAGE_ID:
            print(f"== objects for pageId={TARGET_PAGE_ID} (limit=100)")
            filt = Filter.by_property("pageId").equal(TARGET_PAGE_ID)
            res2 = coll.query.fetch_objects(
                filters=filt,
                limit=100,
                return_properties=["pageId", "title", "chunkIndex", "updatedAt", "content"],
                include_vector=False,
            )
            for o in res2.objects:
                p = o.properties
                head = (p.get("content") or "").replace("\n", " ")[:120]
                print(f"- chunk={p.get('chunkIndex'):>3}  title={p.get('title')}")
                print(f"  {head} ...")
            print(f"(found {len(res2.objects)} chunks)")

        # 4) ベクトルの次元確認（1件だけ）
        print("\n== vector dimension check (1 object)")
        res3 = coll.query.fetch_objects(limit=1, include_vector=True)
        if res3.objects:
            vec = res3.objects[0].vector
            if isinstance(vec, dict):  # named vectors 形式（例: {"default": [...] }）
                name, arr = next(iter(vec.items()))
                dim = len(arr) if arr is not None else 0
                print(f"vector name={name}, dim={dim}  (expected 1024 for bge-m3)")
            elif isinstance(vec, list):  # 単一ベクトル（旧形式）
                print(f"vector dim={len(vec)}  (expected 1024 for bge-m3)")
            else:
                print("no vector on object")
        else:
            print("no objects to check.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
