# /ui/langchain_confluence_qa.py

import streamlit as st
import requests
import json
import logging
import os
import pandas as pd
from datetime import datetime
from lang_config import LANG

# ===== ページ設定 =====
st.set_page_config(page_title="Confluence QA Bot", layout="centered")

# ===== ログ設定 =====
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="logs/app.log",
    filemode="a",
)

# ===== 言語設定 =====
if "lang" not in st.session_state:
    st.session_state.lang = "ja"  # ← 初期値は日本語

lang_toggle = st.sidebar.radio(
    "Language",
    ["English", "日本語"],
    index=0 if st.session_state.lang == "en" else 1
)

if lang_toggle == "English":
    st.session_state.lang = "en"
else:
    st.session_state.lang = "ja"

T = LANG[st.session_state.lang]

# ===== プロンプトタイプの設定 =====
prompt_type = st.sidebar.radio(
    T["prompt_type_label"],
    [T["prompt_type_detail"], T["prompt_type_simple"]],
    index=0
)

# ===== ユーザー認証（CSV） =====
USER_CSV_PATH = "data/users.csv"
users_df = pd.read_csv(USER_CSV_PATH)

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user = None

if not st.session_state.logged_in:
    st.title(T["login_title"])
    input_id = st.text_input(T["user_id"])
    input_pw = st.text_input(T["password"], type="password")
    if st.button(T["login_btn"]):
        matched = users_df[
            (users_df["id"] == input_id) & (users_df["password"] == input_pw)
        ]
        if not matched.empty:
            st.session_state.logged_in = True
            st.session_state.user = input_id
            st.success(T["login_success"].format(user=input_id))
            st.rerun()
        else:
            st.error(T["login_error"])
    st.stop()

# ===== メイン画面 =====
st.title("📘 Confluence QA Bot")

st.sidebar.success(T["logged_in"].format(user=st.session_state.user))
if st.sidebar.button(T["logout"]):
    st.session_state.logged_in = False
    st.session_state.user = None
    st.rerun()

# ===== 履歴読み込み =====
history_path = "logs/confluence_qa_history.json"
if "history" not in st.session_state:
    if os.path.exists(history_path) and os.path.getsize(history_path) > 0:
        with open(history_path, "r", encoding="utf-8") as f:
            st.session_state.history = json.load(f)
    else:
        st.session_state.history = []

if "loading" not in st.session_state:
    st.session_state.loading = False

# ===== 入力状態の保存 =====
if "query_text" not in st.session_state:
    st.session_state.query_text = ""

# ===== 入力欄 =====
st.session_state.query_text = st.text_area(
    T["input_label"],
    placeholder=T["input_placeholder"],
    value=st.session_state.query_text,
    key="query_input",
    label_visibility="visible",
)

input_is_empty = not st.session_state.query_text.strip()
button_disabled = input_is_empty or st.session_state.loading

if st.button(T["ask_btn"], disabled=button_disabled):
    logging.info(f"Question: {st.session_state.query_text}")
    st.session_state.loading = True

    with st.spinner(T["loading"]):
        try:
            refine_res = requests.post(
                "http://localhost:8000/refine_question",
                json={"raw_question": st.session_state.query_text},
            )
            if refine_res.status_code != 200:
                st.error(T["refine_error"])
                st.session_state.loading = False
                raise Exception("Refine error")

            refined_question = refine_res.json()["refined_question"]

            res = requests.post(
                "http://localhost:8000/query",
                json={
                    "question": refined_question,
                    "prompt_type": prompt_type
                }
            )

            if res.status_code == 200:
                result = res.json()
                st.session_state.answer = result["answer"]
                st.session_state.sources = result["sources"]
                st.session_state.last_query = st.session_state.query_text

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.session_state.history.append(
                    {
                        "user_id": st.session_state.user,
                        "question": st.session_state.query_text,
                        "refined_question": refined_question,
                        "answer": st.session_state.answer,
                        "timestamp": timestamp,
                    }
                )

                with open(history_path, "w", encoding="utf-8") as f:
                    json.dump(st.session_state.history, f, ensure_ascii=False, indent=2)

                logging.info("Answer generated successfully")
            else:
                logging.error(f"API error: Status code {res.status_code}")
                st.error(T["api_error"])

        except Exception:
            logging.exception("API call error")
            st.error(T["conn_error"])

        finally:
            st.session_state.loading = False

# ===== 回答セクション =====
if "answer" in st.session_state and not st.session_state.loading:
    st.success(T["answer"])
    st.write(st.session_state.answer)
    st.caption(T["disclaimer"])

    # === 参考文献セクション ===
    if "sources" in st.session_state and st.session_state.sources:
        st.markdown("### 📚 参考文献")
        for i, s in enumerate(st.session_state.sources, start=1):
            title = s["metadata"].get("title", f"Doc {i}")
            url = s["metadata"].get("url", None)
            score = s.get("score", None)

            st.markdown("---")
            if url:
                st.markdown(f"**{i}. [{title}]({url})**")
            else:
                st.markdown(f"**{i}. {title}**")
            if score is not None:
                st.caption(f"関連度スコア: `{score:.2f}`")

            # 本文プレビュー（冒頭だけ表示）
            preview = s.get("page_content", "")
            if preview:
                st.text_area(
                    "抜粋",
                    preview[:300] + ("..." if len(preview) > 300 else ""),
                    height=100,
                    disabled=True,
                )

# ===== 履歴表示 =====
with st.expander(T["history"], expanded=False):
    for idx, item in enumerate(reversed(st.session_state.history)):
        st.markdown(f"👤 **{T['user']}**: {item.get('user_id', 'Unknown')}")
        st.markdown(f"🕒 **{T['time']}**: {item.get('timestamp', 'Unknown time')}")
        st.markdown(f"**Q:** {item['question']}")
        st.markdown(f"**A:** {item['answer']}")

        if st.button("🗑️ この履歴を削除", key=f"delete_{idx}"):
            del st.session_state.history[len(st.session_state.history) - 1 - idx]
            st.success("履歴を削除しました。")
            st.rerun()

        st.markdown("---")
