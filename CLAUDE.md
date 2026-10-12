# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

A RAG knowledge-base ("智能智库") that ingests product-manual documents and answers queries over them. Logic is two **LangGraph** workflows, exposed through two separate **FastAPI** services. Python ≥ 3.11, dependency-managed with **uv** (`uv.lock`; venv at `.venv`).

Expected infrastructure (all external, configured via env): Milvus (vector DB), MongoDB (chat history), MinIO (object storage), an OpenAI-compatible LLM (Qwen via DashScope), and local GPU models (BGE-M3 embedding, BGE-reranker-large, MinerU document parsing). The ML pieces require GPU (`cuda:0`, fp16).

There is **no** `README`, `Makefile`, or lint/test configuration in the repo. Setup is done entirely through `.env`.

## Environment & setup

All configuration lives in `.env` (template: `.env.example` — copy it and fill in the keys). Config modules and graphs read it at import time via `load_dotenv()` (see `.env.example` for the full list of variables per subsystem: LLM, BGE embedding/rerank, Milvus, Mongo, MinIO, MinerU, MCP web search).

- Install deps: `uv sync` (or use the existing `.venv/Scripts/python.exe`).
- Run any module's `__main__` demo directly: `python <module>.py`. Several modules (the graph files, `config_base.py`, `state.py`, config modules) ship an `if __name__ == "__main__"` sample you can run to exercise that piece standalone.
- The scripts under `test/` are plain Python scripts run the same way (e.g. `python test/06-日志.py`); there is no test runner.

## Running the services

Each service is a self-executing FastAPI app (its own `uvicorn.run`), so start it by running the module directly. Bring the infra up first (Milvus/Mongo/MinIO).

- **Import API** — `python web/api/import_service.py` → `http://127.0.0.1:8000` (OpenAPI at `/docs`, upload page at `/import.html`). Endpoints: `POST /upload` (multi-file, runs the import graph as a background task), `GET /status/{task_id}`, `GET /import.html`.
- **Query API** — `python web/api/query_service.py` → `http://127.0.0.1:8001` (chat page at `/chat.html`). Endpoints: `POST /query` (sync or SSE-streamed), `GET /stream/{session_id}`, `GET /history/{session_id}`, `DELETE /history/{session_id}`, `GET /health`.

## Architecture

Both workflows are `StateGraph`s over a `TypedDict` state, built and compiled in a workflow class, and invoked via `.run(state, stream=True|False)` which maps to `graph.stream` / `graph.invoke`. State schemas live in `processor/*/state.py`.

### Import pipeline — `processor/import_processor/`

`node_entry` → (conditional) → `node_pdf_to_md` | `node_md_img` → `node_document_split` → `node_item_name_recognition` → `node_bge_embedding` → `node_import_milvus` → END

- `node_entry` inspects the file and routes: PDF → `node_pdf_to_md` (MinerU PDF→Markdown); MD → `node_md_img` (parses image captions with the VL model and embeds them back into the doc).
- Then sequentially: split into chunks → recognize the product/item name → embed with BGE-M3 → store vectors + metadata into Milvus (chunks and item names go into separate collections).

### Query pipeline — `processor/query_processor/`

Entry `node_item_name_confirm`:
- If the product name cannot be uniquely confirmed, this node writes a disambiguation or refusal directly into `state["answer"]` and routes straight to `node_answer_output`, **skipping retrieval entirely**.
- Otherwise it fans out to three parallel retrievers — `node_search_embedding`, `node_search_embedding_hyde` (hypothetical-document embedding), `node_web_search_mcp` — then `node_rrf` (reciprocal-rank fusion) → `node_rerank` (BGE reranker) → `node_answer_output` (LLM generation, streams deltas).

There are **two** query graph files:
- `main_graph.py` (`KBQueryWorkflow`) — uses `node_multi_search`/`node_join` virtual branching nodes. **This is the one the HTTP service imports.**
- `main_graph_v2.py` (`KBQueryWorkflowV2`) — a newer variant that drops the virtual nodes (each search edge goes straight to `node_rrf`). Not yet wired into the service.

### Node contract — `processor/base.py` (both pipelines)

All nodes subclass an abstract base (`BaseNode` in import, `NodeBase` in query), set a `name` attribute, and implement:

```python
def process(self, state: Dict) -> Dict: ...
```

LangGraph calls the node object; the base's `__call__` wraps `process` with logging and task tracking. Node files live in `*_processor/nodes/node_*.py` (classes named `Node*`); workflow classes register fresh instances via `add_node("<node_id>", instance)`.

### Configuration

Two patterns coexist:
- Simple per-area dataclasses with a **module-level singleton instance** reading `.env` directly (e.g. `config/lm_config.py` → `lm_config`, `config/milvus_config.py` → `milvus_config`, `config/minio_config.py` → `minio_config`).
- `processor/import_processor/config_base.py` — an `ImportConfig` dataclass plus a lazily-created `get_config()` singleton; this is what the import nodes receive.

### Infrastructure utilities — `utils/`

- `task_utils.py` — in-memory (single-process) task registry keyed by `task_id`/`session_id`: per-node running/done lists, a node-id→Chinese map for the frontend, statuses, and stored results (`answer`, `image_urls`).
- `sse_utils.py` — per-`session_id` `queue.Queue`; nodes/services `push_to_session(...)` events (`ready/progress/delta/final/error`) that `/stream` yields as SSE.
- `milvus_utils.py`, `minio_utils.py`, `mongo_history_utils.py`, `reranker_http_utils.py` — thin wrappers around their backends; plus `embedding_utils.py`, `llm_utils.py`, `json_format_utils.py`.
- `tool/logger.py` — the shared colorlog `logger` used by query nodes/services. Import nodes instead call `setup_logging` from their own `base.py`.

## Gotchas

- `web/api/query_service.py` imports `KBQueryWorkflow` (V1) — edits to V2 (`main_graph_v2.py`) won't affect the running service until it is re-pointed.
- `web/api/import_service.py` reads `DATA_BASED_ROOT_DIR` from env with **no default**, and it is **not** in `.env.example` — set it manually or `/upload` will fail at `os.path.join`.
- Streaming is real: with `is_stream=true`, `/query` returns immediately with a `session_id` and the frontend connects to `/stream/{session_id}` to receive SSE events.
- Task tracking is in-memory and per-process — parallel service instances will not share progress/status.
- The frontend pages (`web/page/import.html`, `chat.html`) are static HTML served by API routes; no build step.
