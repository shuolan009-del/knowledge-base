# config/embedding_config.py
"""
向量嵌入配置（EMBED_MODE 三档模式）

模式说明：
- local-gpu : BGE-M3 本地推理（flagembedding，需 uv sync --extra gpu），dense + sparse 双向量
- local-onnx: fastembed 本地 ONNX CPU 推理，仅 dense（服务器 2C2G 推荐）
- api       : DashScope text-embedding API，仅 dense（最轻，按量计费）
"""
from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()

# 各模式默认向量维度（EMBEDDING_DIM 可覆盖，但改 EMBED_MODE 时必须同步核对）：
#   local-gpu : BAAI/bge-m3（本地）                = 1024
#   local-onnx: BAAI/bge-small-zh-v1.5（fastembed）= 512
#   api       : DashScope text-embedding-v4        = 1536
_MODE_DEFAULT_DIM = {
    "local-gpu": 1024,
    "local-onnx": 512,
    "api": 1536,
}


@dataclass
class EmbeddingConfig:
    embed_mode: str   # local-gpu / local-onnx / api
    bge_m3_path: str  # local-gpu：BGE-M3 本地模型目录
    bge_m3: str       # local-gpu：模型名称（仅记录）
    bge_device: str   # local-gpu：cpu / cuda:0
    bge_fp16: bool    # local-gpu：半精度
    onnx_model: str   # local-onnx：fastembed 模型名
    api_model: str    # api：DashScope embedding 模型名
    dim: int          # 向量维度


def _load_embedding_config() -> EmbeddingConfig:
    mode = (os.getenv("EMBED_MODE") or "local-gpu").strip().lower()
    if mode not in _MODE_DEFAULT_DIM:
        raise ValueError(
            f"不支持的 EMBED_MODE: {mode!r}，可选值: {sorted(_MODE_DEFAULT_DIM)}"
        )
    dim_env = os.getenv("EMBEDDING_DIM")
    dim = int(dim_env) if dim_env else _MODE_DEFAULT_DIM[mode]
    if dim_env and int(dim_env) != _MODE_DEFAULT_DIM[mode]:
        print(
            f"⚠️ EMBEDDING_DIM={dim_env} 与 EMBED_MODE={mode} 的默认维度 "
            f"{_MODE_DEFAULT_DIM[mode]} 不一致：请确认所用模型实际输出维度，"
            "否则建表/检索会因维度不符报错"
        )
    return EmbeddingConfig(
        embed_mode=mode,
        bge_m3_path=os.getenv("BGE_M3_PATH", ""),
        bge_m3=os.getenv("BGE_M3", "BAAI/bge-m3"),
        bge_device=os.getenv("BGE_DEVICE", "cpu"),
        bge_fp16=os.getenv("BGE_FP16") in ("1", "true", "True"),
        onnx_model=os.getenv("EMBEDDING_ONNX_MODEL", "BAAI/bge-small-zh-v1.5"),
        api_model=os.getenv("EMBEDDING_MODEL", "text-embedding-v4"),
        dim=dim,
    )


embedding_config = _load_embedding_config()
