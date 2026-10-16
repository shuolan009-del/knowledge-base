# -*- coding: utf-8 -*-
"""
零中间件栈运行时验证（服务器 2C2G 部署前自检）
用法：uv run python scripts/verify_standalone_stack.py

覆盖 4 块（全部本地、零外部服务）：
  1. Milvus Lite 进程内：dense-only 建表 / 插入 / 稠密检索 / expr 过滤（走真实生产代码）
  2. SQLite 会话历史：save / get / update / clear 四接口
  3. 本地目录存储：save_file / build_url / clean_dir
  4. FastAPI 双 app：可导入 + /storage 静态路由已挂载

注意：EMBED_MODE=local-onnx 首次运行需下载 fastembed 模型（BAAI/bge-small-zh-v1.5 ~100MB），
直连 HuggingFace 失败时可设 HF_ENDPOINT=https://hf-mirror.com；本脚本不覆盖该链路。
"""
import os
import random
import shutil
import sys

# 允许从任意目录调用：把项目根加入 sys.path（脚本位于 <root>/scripts/ 下）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 隔离验证产物：.env 各模块均用 load_dotenv()（无 override），行内环境变量优先
os.environ["HISTORY_DB_PATH"] = "./data/verify_history.db"
os.environ["STORAGE_LOCAL_DIR"] = "./data/verify_storage"
os.environ["STORAGE_IMG_DIR"] = "verify-images"

PASS, FAIL = "✅", "❌"
results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))
    print(f"{PASS if cond else FAIL} {name}" + (f"  {extra}" if extra else ""))


# ============ 1. Milvus Lite ============
print("\n===== 1. Milvus Lite 进程内 + dense-only =====")
from pymilvus import MilvusClient  # noqa: E402
from processor.import_processor.nodes.node_import_milvus import NodeImportMilvus  # noqa: E402
from utils.milvus_utils import search_by_embeddings  # noqa: E402

DB = "./milvus_verify.db"
COLL = "verify_chunks"
# Milvus Lite 的 ./milvus.db 是目录（LMDB），不是文件——清理必须 rmtree
shutil.rmtree(DB, ignore_errors=True)
client = MilvusClient(uri=DB)  # 本地路径 → 进程内 Lite，零外部进程
check("MilvusClient(Lite) 实例化", client is not None)

NodeImportMilvus._create_chunks_collection(None, COLL, client, 512)
check("dense-only 集合创建", client.has_collection(COLL))
desc = client.describe_collection(COLL)
fields = {f["name"] for f in desc["fields"]}
check("schema 无 sparse_vector 字段", "sparse_vector" not in fields, f"fields={sorted(fields)}")

random.seed(7)
rows = [
    {"content": "电磁炉功率调节说明", "title": "电磁炉", "full_title": "电磁炉使用手册",
     "parent_title": "厨房电器", "part": 1, "file_title": "厨电手册", "item_name": "电磁炉",
     "dense_vector": [random.uniform(-1, 1) for _ in range(512)]},
    {"content": "电饭煲预约煮饭教程", "title": "电饭煲", "full_title": "电饭煲使用手册",
     "parent_title": "厨房电器", "part": 2, "file_title": "厨电手册", "item_name": "电饭煲",
     "dense_vector": [random.uniform(-1, 1) for _ in range(512)]},
    {"content": "空调滤网清洗步骤", "title": "空调", "full_title": "空调使用手册",
     "parent_title": "家电", "part": 1, "file_title": "家电手册", "item_name": "空调",
     "dense_vector": [random.uniform(-1, 1) for _ in range(512)]},
]
client.insert(collection_name=COLL, data=rows)
client.flush(collection_name=COLL)
check("dense-only 插入 3 行", client.query(COLL, "chunk_id >= 0", output_fields=["chunk_id"]) is not None)

q = rows[0]["dense_vector"]
res = search_by_embeddings(client, COLL, q, sparse_vector=None, limit=3, output_fields=["item_name"])
hits = res[0] if res else []
check("dense-only 检索返回命中", len(hits) > 0, f"top1={hits[0]['entity']['item_name'] if hits else None}")

res_f = search_by_embeddings(client, COLL, q, sparse_vector=None,
                             expr="item_name == \"电磁炉\"", limit=3, output_fields=["item_name"])
hits_f = res_f[0] if res_f else []
check("dense-only + expr 过滤", len(hits_f) == 1 and hits_f[0]["entity"]["item_name"] == "电磁炉")

client.drop_collection(COLL)
check("清理验证集合", not client.has_collection(COLL))

# ============ 2. SQLite 历史 ============
print("\n===== 2. SQLite 会话历史 =====")
from utils.history_utils import (  # noqa: E402
    save_chat_message, update_message_item_names, get_recent_messages, clear_history,
)

sid = "verify-sess-1"
mid = save_chat_message(sid, "user", "电磁炉怎么用", "电磁炉使用方法")
check("save_chat_message 返回 id", bool(mid))
recent = get_recent_messages(sid, limit=10)
check("get_recent_messages 读到 1 条", len(recent) == 1, f"role={recent[0]['role'] if recent else None}")
n = update_message_item_names([mid], ["电磁炉", "电饭煲"])
check("update_message_item_names 更新 1 条", n == 1)
recent2 = get_recent_messages(sid, limit=10)
check("item_names 回读生效", recent2[0].get("item_names") == ["电磁炉", "电饭煲"],
      f"got={recent2[0].get('item_names')}")
d = clear_history(sid)
check("clear_history 删除 1 条", d == 1)
check("清空后查询为 0", len(get_recent_messages(sid, limit=10)) == 0)

# ============ 3. 本地存储 ============
print("\n===== 3. 本地目录存储 =====")
from utils.storage_utils import save_file, build_url, clean_dir, ensure_dirs  # noqa: E402
from config.storage_config import storage_config  # noqa: E402

ensure_dirs()
tmp_f = "./data/verify_src.txt"
with open(tmp_f, "w", encoding="utf-8") as f:
    f.write("hello storage")
url = save_file(tmp_f, "verify-images/a.txt")
disk = os.path.join(os.path.abspath(storage_config.local_dir), "verify-images", "a.txt")
check("save_file 落盘", bool(url) and os.path.exists(disk), f"url={url}")
check("build_url 形如 /storage/...", url == "/storage/verify-images/a.txt")
save_file(tmp_f, "verify-images/sub/b.txt")
clean_dir("verify-images")
check("clean_dir 清掉子目录", not os.path.exists(os.path.join(os.path.abspath(storage_config.local_dir), "verify-images")))

# ============ 4. FastAPI app ============
print("\n===== 4. FastAPI 双 app =====")
from web.api.import_service import app as app_import  # noqa: E402
from web.api.query_service import app as app_query  # noqa: E402

paths_i = {r.path for r in app_import.routes}
paths_q = {r.path for r in app_query.routes}
check("import_service 挂载 /storage", any(p.startswith("/storage") for p in paths_i))
check("query_service 挂载 /storage", any(p.startswith("/storage") for p in paths_q))
check("app 标题正常", app_import.title == "BOSS智库-导入API")

# ============ 汇总 + 自清理 ============
print("\n===== 汇总 =====")
bad = [r for r in results if not r[1]]
print(f"共 {len(results)} 项，通过 {len(results) - len(bad)} 项，失败 {len(bad)} 项")
for name, ok, extra in bad:
    print(f"  ❌ {name} {extra}")

shutil.rmtree(DB, ignore_errors=True)
shutil.rmtree("./data/verify_storage", ignore_errors=True)
for junk in ("./data/verify_history.db", "./data/verify_history.db-wal",
             "./data/verify_history.db-shm", "./data/verify_src.txt"):
    try:
        os.remove(junk)
    except OSError:
        pass
print("（验证产物已自动清理）")
sys.exit(1 if bad else 0)
