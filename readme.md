# 💻 RAGシステム実行手順（Phase2・FastAPI + Streamlit + Weaviate + Confluence）

## ✅ 事前準備

| 項目     | 内容 |
|----------|------|
| 環境     | Windows + WSL2（Ubuntu） |
| Docker   | WSL2上に直接インストールしたDocker + docker-composeを使用 |
| `.env`   | プロジェクト直下にUTF-8で作成 |

### `.env`ファイルの内容例

CONF_BASE_URL=https://confluence-test.atlassian.net/wiki
CONF_USER=confluence_user@gmail.com
CONF_API_TOKEN=ABCDExxxxxx
WEAVIATE_ENDPOINT=http://localhost:8080

---

🔧 Qwen モデル環境構築

Ollama インストール
Ollama 公式サイト
 からインストール。
Ubuntu の場合:

curl -fsSL https://ollama.com/install.sh | sh


Qwen モデルの取得

ollama pull qwen2:1.5b-instruct


動作確認

ollama run qwen2:1.5b-instruct "こんにちは、自己紹介してください"

## 🚀 実行コマンド一覧

| 手順 | コマンド / 操作 | 説明 |
|------|------------------|------|
| 1 | `cd /mnt/c/Users/nishitad/Downloads/phase2` | プロジェクトルートに移動 |
| 2 | `python3 -m venv .venv` | 仮想環境を作成 |
| 3 | `source .venv/bin/activate` | 仮想環境を有効化 |
| 4 | `pip install -r requirements.txt` | 必要ライブラリをインストール |
| 5 | `docker-compose up -d` | Weaviate をバックグラウンドで起動 |
| 6 | `python scripts/create_confluence_chunk_class.py` | Weaviate に Confluence 用クラス定義を登録 |
| 7 | `python scripts/ingest_confluence_bge.py` | Confluence ページ取得 → 埋め込み → Weaviate に登録 |
| 8 | `python scripts/api_server_phase2.py` | FastAPI サーバーを起動（http://localhost:8000） |
| 9 | `streamlit run ui/langchain_confluence_qa.py` | Streamlit UI を起動（http://localhost:8501） |
| 10 | ブラウザでアクセス | `http://localhost:8501` にアクセスして質問！ |

---

## 🔁 Confluenceデータ自動アップサート設定手順（cron）

以下は、Confluence ページデータを Weaviate に定期アップサートするための設定手順です。

| 手順 | 内容 | コマンド / スクリプト例 |
|------|------|--------------------------|
| 1 | スクリプトファイルを作成 | `/home/a/phase2/scripts/run_batch.sh` を新規作成 |
| 2 | スクリプトに以下を記述 | ```#!/bin/bash<br>source /home/a/phase2/.venv/bin/activate<br>python /home/a/phase2/scripts/ingest_confluence_bge.py``` |
| 3 | 実行権限を付与 | `chmod +x /home/a/phase2/scripts/run_batch.sh` |
| 4 | cronエディタを開く | `crontab -e` |
| 5 | 以下の行を追加（毎日6時実行） | `0 6 * * * /home/a/phase2/scripts/run_batch.sh >> /home/a/phase2/logs/cron.log 2>&1` |
| 6 | 保存して終了 | `Ctrl + O` → `Enter` → `Ctrl + X` |
| 7 | 登録内容を確認 | `crontab -l` |
| 8 | ログを確認（任意） | `cat /home/a/phase2/logs/cron.log` |

---

## 💡 cron記法の例

| 実行タイミング   | cron記法           | 説明                    |
|------------------|---------------------|-------------------------|
| 毎日6時           | `0 6 * * *`          | 毎日朝6時に実行         |
| 毎週月曜10時      | `0 10 * * 1`         | 毎週月曜10時に実行      |
| 毎時ちょうど      | `0 * * * *`          | 毎時0分に実行           |
| 10分おき          | `*/10 * * * *`       | 10分ごとに実行          |

---

## 🔧 cronサービスの操作コマンド

```bash
sudo service cron stop     # cronを停止
sudo service cron start    # cronを起動
sudo service cron restart  # cronを再起動

## 📁 プロジェクト構成と各ファイルの役割（Phase2）

.
├── data
│ └── users.csv
├── docker-compose.yaml
├── readme.md
├── requirements.txt
├── requirements_phase2.txt
├── scripts
│ ├── api_server_phase2.py
│ ├── create_confluence_chunk_class.py
│ ├── devtools
│ │ └── download_bge_m3.py
│ ├── dump_confluence_content.py
│ ├── ingest_confluence_bge.py
│ ├── search_weaviate.py
│ └── verify_confluence_chunks.py
└── ui
├── lang_config.py
└── langchain_confluence_qa.py

### ルートディレクトリ

| パス                    | 役割 |
| --------------------- | ------------------------------------ |
| `docker-compose.yaml` | Weaviate コンテナなどの構成定義 |
| `requirements.txt`    | Python パッケージ依存関係（共通用） |
| `requirements_phase2.txt` | Phase2 専用の依存関係定義 |
| `readme.md`           | プロジェクト説明・手順 |

---

### 📁 data/

| パス               | 役割 |
| ---------------- | ------------------------------- |
| `data/users.csv` | ユーザー情報の管理用（オプション） |

---

### 📁 scripts/

| パス                                  | 役割 |
| ----------------------------------- | -------------------------------- |
| `scripts/api_server_phase2.py`      | Phase2 用 FastAPI サーバー起動スクリプト |
| `scripts/create_confluence_chunk_class.py` | Weaviate に Confluence 用クラスを作成 |
| `scripts/dump_confluence_content.py` | Confluence ページをダンプ（テキスト確認用） |
| `scripts/ingest_confluence_bge.py`  | Confluence ページを取得 → 埋め込み → Weaviate 登録 |
| `scripts/search_weaviate.py`        | Weaviate に登録されたデータを検索（テスト用） |
| `scripts/verify_confluence_chunks.py` | 登録済みの Confluence チャンクを検証 |
| `scripts/devtools/download_bge_m3.py` | BGE-M3 埋め込みモデルのダウンロード（開発用） |

---

### 📁 ui/

| パス                            | 役割 |
| ----------------------------- | ---------------------------------- |
| `ui/lang_config.py`           | 言語設定モジュール（UIで利用） |
| `ui/langchain_confluence_qa.py` | Streamlit ベースの Q&A フロントエンド |