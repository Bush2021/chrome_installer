import os
from pathlib import Path

# 工作目录相关设置
WORKSPACE_DIR = "./output"

# fetch.py 相关设置
FETCH_API_URL = "https://tools.google.com/service/update2"
FETCH_CHANNELS = ["stable", "beta", "dev", "canary"]
FETCH_PLATFORMS = ["win"]  # 'win' 对应 Windows
FETCH_OUTPUT_JSON_PATH = os.path.join(WORKSPACE_DIR, "data.json")

# download.py 相关设置
DOWNLOAD_ARCH = ["win_stable_x64"]  # 可以是单个字符串或列表
DOWNLOAD_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "downloads")
DOWNLOAD_FORCE = False
DOWNLOAD_THREADS = 4

# gen_plus.py 相关设置
GEN_PLUS_OUTPUT_DIR = os.path.join(WORKSPACE_DIR, "plus")
GEN_PLUS_FORCE = False
GEN_PLUS_REPACK = True

# gen_markdown.py 相关设置
GEN_MARKDOWN_OUTPUT_PATH = os.path.join(WORKSPACE_DIR, "readme.md")





# 确保工作目录存在
def ensure_dir(dir_path):
    """确保目录存在，如果不存在则创建"""
    path = Path(dir_path)
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
    return str(path)

# 确保所有必要的目录都存在
ensure_dir(WORKSPACE_DIR)
ensure_dir(DOWNLOAD_OUTPUT_DIR)
ensure_dir(GEN_PLUS_OUTPUT_DIR)
ensure_dir(os.path.dirname(FETCH_OUTPUT_JSON_PATH))
ensure_dir(os.path.dirname(GEN_MARKDOWN_OUTPUT_PATH)) 