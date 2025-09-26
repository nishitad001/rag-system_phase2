import os
import sys
import argparse
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

BATCH = 100  # 1リクエストで取る件数（必要に応じて調整）


def dump_all(page_id: str | None):
    client = weaviate.connect_to_local(host=HOST, port=PORT, grpc_port=GRPC_PORT)
    try:
        coll = client.collections.get(CLASS_NAME)

        cursor = None
        total = 0

        while True:
            kwargs = dict(
                limit=BATCH,
                after=cursor,
                return_properties=["pageId", "title", "chunkIndex", "content"],
                include_vector=False,
            )
            if page_id:
                kwargs["filters"] = Filter.by_property("pageId").equal(page_id)

            res = coll.query.fetch_objects(**kwargs)
            objs = res.objects or []
            if not objs:
                break

            for o in objs:
                p = o.properties
                content = (p.get("content") or "").rstrip()
                print(f"--- pageId={p.get('pageId')}  title={p.get('title')}  chunkIndex={p.get('chunkIndex')} ---")
                print(content)
                print()  # 区切りの空行
                total += 1

            page_info = getattr(res, "page_info", None)
            cursor = page_info.end_cursor if page_info else None
            if not (page_info and page_info.has_next_page):
                break

        print(f"== total chunks printed: {total}", file=sys.stderr)

    finally:
        client.close()


def main():
    ap = argparse.ArgumentParser(description="Dump all 'content' from Weaviate ConfluenceChunk")
    ap.add_argument("--page-id", help="特定の pageId のみ出力したい場合に指定", default=None)
    args = ap.parse_args()
    dump_all(args.page_id)


if __name__ == "__main__":
    main()
