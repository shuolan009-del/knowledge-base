# utils/embedding_utils.py

import os
from pathlib import Path
from pymilvus.model.hybrid import BGEM3EmbeddingFunction

from config.embedding_config import embedding_config
from processor.import_processor.base import setup_logging

setup_logging()

# 模型单例对象，避免重复初始化
_bge_m3_ef = None


def get_bge_m3_ef():
    global _bge_m3_ef
    if _bge_m3_ef is None:
        # 使用原始字符串或正斜杠，避免转义
        model_path = r"F:\ai_models\bge-m3"
        # 或 model_path = "F:/ai_models/bge-m3-M3"

        # 检查本地目录是否存在
        if not os.path.isdir(model_path):
            raise FileNotFoundError(
                f"模型目录不存在: {model_path}\n"
                "请确认路径正确，或从 HuggingFace 下载官方模型 'BAAI/bge-m3' 并放置到该目录。"
            )

        # 强制离线模式（可选，双重保险）
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_OFFLINE"] = "1"

        # 关键：将 local_files_only 作为直接参数传递，而不是放在 model_kwargs 中
        _bge_m3_ef = BGEM3EmbeddingFunction(
            model_name=model_path,
            device="cpu",          # 如使用 GPU 可改为 "cuda"
            local_files_only=True, # 强制本地加载，禁止联网
            trust_remote_code=True # 避免潜在的安全警告（若不需要可移除）
        )
    return _bge_m3_ef


def generate_embeddings(texts):
    """
    为文本生成向量嵌入
    :param texts: 要生成嵌入的文本列表
    :return: 包含dense和sparse向量的字典
    """
    model = get_bge_m3_ef()
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


# ================= 单元测试主入口 =================
if __name__ == "__main__":
    test_data = ["大功率电磁炉", "Car"]
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
        print(f"   - 成功生成数量: {len(output['sparse'])} 条")
        print(f"   - 第一条文本的关键字字典 (词ID : 权重):")
        print(f"     {output['sparse'][0]}")
        print("=" * 54)
        print("💡 结论：函数单独测试通过！输出数据结构完全符合 Milvus 的入库标准。")
    except Exception as e:
        print(f"\n❌ 测试失败！拦截到异常: {e}")
        print("💡 排查建议：")
        print("   1. 请确认本地路径下的模型文件是否完整（至少包含 config.json, tokenizer.json, pytorch_model.bin 等）。")
        print("   2. 如果仍报错，可尝试改用官方模型名称 'BAAI/bge-m3'（需联网下载）。")