# 智能智库（knowledge-base）

面向商品说明书的 RAG 知识库。文档经「解析 → 切分 → 商品名识别 → 向量化 → Milvus」入库；
查询经「商品名确认 → 三路并行检索 → RRF 融合 → 重排 → LLM 生成」作答——
商品名无法唯一确认时直接澄清或拒答，**跳过检索**，从源头抑制幻觉。

两条管线均为 LangGraph 工作流，各自由独立 FastAPI 服务暴露。

## 系统组成

| 服务 | 启动命令 | 端口 | 页面 |
|---|---|---|---|
| 导入 API | `python web/api/import_service.py` | 8000 | `/import.html` |
| 查询 API | `python web/api/query_service.py` | 8001 | `/chat.html` |

主要接口：`POST /upload`（多文件，后台跑导入图）、`GET /status/{task_id}`、
`POST /query`（同步或 `is_stream=true` 走 SSE）、`GET /stream/{session_id}`、
`GET|DELETE /history/{session_id}`、`GET /health`。

## 依赖的基础设施

全部外部部署，通过 `.env` 配置（模板见 `.env.example`，按子系统分组注释）：

- **Milvus** — 向量库（chunk 与商品名两个 collection）
- **MongoDB** — 会话历史
- **MinIO** — 对象存储（文档 / 图片）
- **OpenAI 兼容 LLM** — Qwen via DashScope
- **本地 GPU 模型**（`cuda:0`，fp16）— BGE-M3 向量、BGE-reranker-large 重排、MinerU 文档解析

## 快速开始

```bash
uv sync                    # 或使用已有 .venv
cp .env.example .env       # 填写各子系统 Key / 地址
# 先拉起 Milvus / MongoDB / MinIO
python web/api/import_service.py   # 导入服务 :8000
python web/api/query_service.py    # 查询服务 :8001
```

## 架构

**导入管线** `processor/import_processor/`：

```
node_entry（按类型路由：PDF → MinerU 解析；MD → 图片题注 VL 解析回填）
  → node_document_split → node_item_name_recognition
  → node_bge_embedding → node_import_milvus → END
```

**查询管线** `processor/query_processor/`：

```
node_item_name_confirm（无法唯一确认 → 直接澄清/拒答，跳过检索）
  → 三路并行检索：
      node_search_embedding          （向量检索）
      node_search_embedding_hyde     （假设文档向量检索）
      node_web_search_mcp            （联网搜索）
  → node_rrf（RRF 融合）→ node_rerank（BGE 重排）
  → node_answer_output（LLM 流式生成）→ END
```

**节点契约**：所有节点继承 `processor/base.py` 的抽象基类并实现
`process(state: Dict) -> Dict`，基类 `__call__` 统一包装日志与任务跟踪。

## 说明

- 更详细的开发 guidance 与易踩坑清单见 `CLAUDE.md`。
- ⚠️ `DATA_BASED_ROOT_DIR` 环境变量无默认值且不在 `.env.example` 中，
  不设置会导致 `/upload` 在 `os.path.join` 处失败。
