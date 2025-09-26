from huggingface_hub import snapshot_download

# 保存先をプロジェクト配下に指定
local_dir = "./phase2/models/bge-m3"

snapshot_download(
    repo_id="BAAI/bge-m3",
    local_dir=local_dir,
    ignore_patterns=["*.h5", "*.onnx"]
)

print(f"モデルを {local_dir} に保存しました")
