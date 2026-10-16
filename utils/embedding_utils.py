# utils/embedding_utils.py
"""
向量嵌入工具（EMBED_MODE 三档模式，配置见 config/embedding_config.py）：
- local-gpu : BGE-M3 本地推理（flagembedding，需 uv sync --extra gpu），dense + sparse 双向量
- local-onnx: fastembed 本地 ONNX CPU 推理，仅 dense（服务器 2C2G 推荐）
- api       : DashScope text-embedding API，仅 dense（最轻，按量计费）

统一入口：generate_embeddings(texts) -> {"dense": [[...], ...], "sparse": [...]}
- local-gpu 模式 sparse 为真实稀疏向量列表（字典格式）
- local-onnx / api 模式 sparse 恒为 []，调用方需做空值保护（见各节点写法）
"""
import os

from config.embedding_config import embedding_config
from processor.import_processor.base import setup_logging

setup_logging()

# 模型单例对象，避免重复初始化
_bge_m3_ef = None        # local-gpu
_onnx_model = None       # local-onnx


def _get_bge_m3_ef():
    """local-gpu 模式：加载本地 BGE-M3（flagembedding），缺失时给出明确指引"""
    global _bge_m3_ef
    if _bge_m3_ef is None:
        # 延迟导入：local-onnx / api 模式无需安装 flagembedding
        from pymilvus.model.hybrid import BGEM3EmbeddingFunction

        # 模型目录优先取配置（.env 的 BGE_M3_PATH），其次兼容旧硬编码路径
        model_path = embedding_config.bge_m3_path or r"F:\ai_models\bge-m3"

        if not os.path.isdir(model_path):
            raise FileNotFoundError(
                f"模型目录不存在: {model_path}\n"
                "请在 .env 中配置 BGE_M3_PATH，或从 HuggingFace/ModelScope 下载 BAAI/bge-m3 放置到该目录。"
            )

        # 强制离线模式（可选，双重保险）
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_OFFLINE"] = "1"

        _bge_m3_ef = BGEM3EmbeddingFunction(
            model_name=model_path,
            device=embedding_config.bge_device or "cpu",
            local_files_only=True,
            trust_remote_code=True
        )
    return _bge_m3_ef


def _get_onnx_model():
    """local-onnx 模式：加载 fastembed ONNX 模型（CPU 推理，自动缓存到用户目录）"""
    global _onnx_model
    if _onnx_model is None:
        from fastembed import TextEmbedding

        _onnx_model = TextEmbedding(model_name=embedding_config.onnx_model)
    return _onnx_model


def _embed_bge_m3(texts):
    """local-gpu：BGE-M3 双向量（dense 1024 维 + sparse）"""
    model = _get_bge_m3_ef()
    embeddings = model.encode_documents(texts)
    processed_sparse = []
    for i in range(len(texts)):
        sparse_indices = embeddings["sparse"].indices[
            embeddings["sparse"].indptr[i]:embeddings["sparse"].indptr[i + 1]].tolist()
        sparse_data = embeddings["sparse"].data[
            embeddings["sparse"].indptr[i]:embeddings["sparse"].indptr[i + 1]].tolist()
        sparse_dict = {k: v for k, v in zip(sparse_indices, sparse_data)}
        processed_sparse.append(sparse_dict)

    return {
        "dense": [emb.tolist() for emb in embeddings["dense"]],
        "sparse": processed_sparse
    }


def _embed_onnx(texts):
    """local-onnx：fastembed CPU 推理，仅 dense"""
    model = _get_onnx_model()
    # fastembed 返回 numpy 数组，统一转 list
    return [list(map(float, emb)) for emb in model.embed(texts)]


def _embed_api(texts):
    """api：DashScope text-embedding，仅 dense（单批上限 10 条，内部自动分批）"""
    import dashscope

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("api 模式缺少密钥：请在 .env 配置 OPENAI_API_KEY（DashScope 密钥）")

    model = embedding_config.api_model
    batch_size = 10
    dense_all = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        resp = dashscope.TextEmbedding.call(
            api_key=api_key,
            model=model,
            input=batch,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"DashScope embedding 调用失败: code={resp.code}, message={resp.message}")
        embeddings = list(resp.output.embeddings)
        # 按 text_index 排序，保证与输入顺序一致
        embeddings.sort(key=lambda e: (e.get("text_index", 0) if isinstance(e, dict) else 0))
        for emb in embeddings:
            vec = emb.get("embedding") if isinstance(emb, dict) else emb.embedding
            dense_all.append(list(map(float, vec)))
    return dense_all


def generate_embeddings(texts):
    """
    为文本生成向量嵌入（统一入口，按 EMBED_MODE 分发）
    :param texts: 要生成嵌入的文本列表
    :return: {"dense": [[...], ...], "sparse": [...]}  # onnx/api 模式 sparse 恒为 []
    """
    mode = embedding_config.embed_mode
    if mode == "local-gpu":
        return _embed_bge_m3(texts)
    if mode == "local-onnx":
        return {"dense": _embed_onnx(texts), "sparse": []}
    if mode == "api":
        return {"dense": _embed_api(texts), "sparse": []}
    # 配置加载时已校验，理论上不可达
    raise ValueError(f"未知的 EMBED_MODE: {mode!r}")


def get_embedding_dim() -> int:
    """当前模式的向量维度（建表/检索对齐用）"""
    return embedding_config.dim


# ================= 单元测试主入口 =================
if __name__ == "__main__":
    test_data = ["大功率电磁炉", "Car"]
    print(f"👉 当前 EMBED_MODE = {embedding_config.embed_mode}，模型 = {embedding_config.api_model if embedding_config.embed_mode == 'api' else embedding_config.onnx_model if embedding_config.embed_mode == 'local-onnx' else embedding_config.bge_m3}，维度 = {embedding_config.dim}")
    print(f"👉 开始单独测试 generate_embeddings 函数...")
    print(f"👉 测试文本: {test_data}\n")
    try:
        output = generate_embeddings(test_data)
        print("\n" + "=" * 20 + " 🎉 测试结果 🎉 " + "=" * 20)
        print(f"【稠密向量 (Dense)】")
        print(f"   - 成功生成数量: {len(output['dense'])} 条")
        print(f"   - 第一条文本的维度大小: {len(output['dense'][0])} 维")
        print(f"   - 第一条文本的前 5 维特征值: {output['dense'][0][:5]} ...")
        print(f"\n【稀疏向量 (Sparse)】")
        if output["sparse"]:
            print(f"   - 第一条文本的关键字字典 (词ID : 权重):")
            print(f"     {output['sparse'][0]}")
        else:
            print("   - 当前模式不产出稀疏向量（dense-only）")
        print("=" * 54)
        print("💡 结论：函数单独测试通过！输出数据结构符合 Milvus 入库标准。")
    except Exception as e:
        print(f"\n❌ 测试失败！拦截到异常: {e}")
        print("💡 排查建议：")
        print("   1. local-gpu 模式：确认 .env 的 BGE_M3_PATH 指向完整模型目录，且已 uv sync --extra gpu。")
        print("   2. local-onnx 模式：确认已 uv sync（含 fastembed），模型可自动下载（国内可设 HF_ENDPOINT=https://hf-mirror.com）。")
        print("   3. api 模式：确认 .env 的 OPENAI_API_KEY 有效且账户可调用 text-embedding 模型。")
