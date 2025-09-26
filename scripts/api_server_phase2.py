# 標準ライブラリ
from typing import Optional

# サードパーティライブラリ
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# langchain系
from langchain_community.chat_models import ChatOllama
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_weaviate.vectorstores import WeaviateVectorStore

# weaviate系
from weaviate import WeaviateClient
from weaviate.connect import ConnectionParams

# === モデル・Embedding読み込み ===
load_dotenv()

# Qwen (Ollama経由)
llm = ChatOllama(model="qwen2:7b-instruct", temperature=0.3)

# BGE embedding
embedding = HuggingFaceEmbeddings(model_name="BAAI/bge-m3")

client = WeaviateClient(
    connection_params=ConnectionParams.from_url(
        "http://localhost:8080", grpc_port=50051
    )
)
client.connect()

# === Phase2: Confluenceドキュメント用 ===
vectorstore = WeaviateVectorStore(
    client=client,
    index_name="ConfluenceChunk",
    text_key="content",
    embedding=embedding,
)

# === FastAPI 初期化 ===
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === モデル定義 ===
class RefineRequest(BaseModel):
    raw_question: str

class QueryRequest(BaseModel):
    question: str
    prompt_type: Optional[str] = None

# === API ①: /refine_question ===
@app.post("/refine_question")
def refine_question(req: RefineRequest):
    prompt = (
        "Here is a question input by a user in Japanese.\n"
        "Please refine it into a technically clear and precise format that is easy for an AI to understand.\n"
        "If the question is vague, add reasonable clarifications.\n"
        "The output should be in Japanese, concise, and structured (e.g., bullet points or a well-organized sentence).\n\n"
        f"【ユーザーの入力】\n{req.raw_question}\n\n"
        "【整形された質問（日本語）】"
    )
    response = llm.invoke(prompt)
    return {"refined_question": response.content}

# === API ②: /query ===
@app.post("/query")
def query(req: QueryRequest):
    query_text = req.question
    prompt_type = req.prompt_type or "詳細回答ver"

    if prompt_type in ["詳細回答ver", "Detailed Answer"]:
        prompt_mode = "detail"
    else:
        prompt_mode = "simple"

    # Weaviateから類似検索
    docs_with_score = vectorstore.similarity_search_with_score(query_text, k=3)
    combined_text = "\n\n".join([doc.page_content for doc, _ in docs_with_score])

    if prompt_mode == "detail":
        prompt = (
            f"The following is a set of past Confluence docs (topK=3).\n"
            f"Please answer the following question **in Japanese**, based only on the information explicitly written in the documents.\n\n"
            f"Question:\n{query_text}\n\n"
            f"Instructions:\n"
            f"- Output must be in **Markdown format**.\n"
            f"- Do **not** use headings like 'Conclusion' or 'Details'.\n"
            f"- Start with a natural sentence that clearly answers the question.\n"
            f"- Then add background or explanation **without repeating the same wording or phrases used in the initial sentence.**\n"
            f"- Bullet points are allowed if they improve clarity.\n"
            f"- Use `**bold**` to emphasize important elements such as logic changes, validations, or team actions.\n"
            f"- Do not bold common phrases.\n"
            f"- At the end, include this line as a footnote **only if the answer is clearly supported by the docs**:\n"
            f"\n  *この情報は、Confluenceドキュメントに基づいています。*\n"
            f"- Do not use general knowledge or assumptions.\n\n"
            f"Reference data:\n{combined_text}"
        )
    else:
        prompt = (
            f"The following is a set of past Confluence docs (topK=3).\n"
            f"Please answer the following question **in Japanese**, based only on the information explicitly written in the documents.\n\n"
            f"Question:\n{query_text}\n\n"
            f"Instructions:\n"
            f"- Output must be in **Markdown format**.\n"
            f"- Start with a natural sentence that clearly answers the question.\n"
            f"- If necessary, add one short supporting sentence without repeating the same wording.\n"
            f"- Do not include background or assumptions.\n"
            f"- Do not use bullet points.\n"
            f"- Use `**bold**` only for key values, specific terms, or decisions.\n"
            f"- At the end, include this line as a footnote **only if the answer is clearly supported by the docs**:\n"
            f"\n  *この情報は、Confluenceドキュメントに基づいています。*\n"
            f"- Do not use general knowledge or assumptions.\n\n"
            f"Reference data:\n{combined_text}"
        )

    response = llm.invoke(prompt)

    sources = [
        {
            "page_content": doc.page_content,
            "metadata": doc.metadata,
            "score": float(score),
        }
        for doc, score in docs_with_score
    ]

    return {"answer": response.content, "sources": sources}

# === 実行 ===
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
