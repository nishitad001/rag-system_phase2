import os
import weaviate
from dotenv import load_dotenv
from weaviate.classes.config import Property, DataType, Configure

# .env 読み込み（WEAVIATE_CLASS など任意）
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# 環境変数（なくてもデフォルト値でOK）
CLASS_NAME = os.getenv("WEAVIATE_CLASS", "ConfluenceChunk")
HOST = os.getenv("WEAVIATE_HOST", "localhost")
PORT = int(os.getenv("WEAVIATE_PORT", "8080"))
GRPC_PORT = int(os.getenv("WEAVIATE_GRPC_PORT", "50051"))

# --- Weaviate 接続（ローカル。API Key/ヘッダー不要） ---
client = weaviate.connect_to_local(host=HOST, port=PORT, grpc_port=GRPC_PORT)
print("✅ Connected to Weaviate")

# 既存クラスがあれば削除（必要に応じてコメントアウト）
existing = client.collections.list_all()
if CLASS_NAME in existing:
    client.collections.delete(CLASS_NAME)
    print(f"🧹 既存の {CLASS_NAME} コレクションを削除しました")

# --- クラス作成 ---
# ※ Phase1 と違い：
#   - vectorizer は外部（bge-m3）で生成するため none
#   - Generative も使わないので未設定
#   - updatedAt は DATE 型にしておくと後で範囲検索が楽
client.collections.create(
    name=CLASS_NAME,
    properties=[
        Property(name="pageId",     data_type=DataType.TEXT),
        Property(name="title",      data_type=DataType.TEXT),
        Property(name="url",        data_type=DataType.TEXT),
        Property(name="updatedAt",  data_type=DataType.DATE),
        Property(name="content",    data_type=DataType.TEXT),
        Property(name="chunkIndex", data_type=DataType.INT),
    ],
    vectorizer_config=Configure.Vectorizer.none(),
)

print(f"✅ {CLASS_NAME} コレクションを作成しました")
client.close()
