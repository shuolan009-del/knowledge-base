# processor/query_processor/nodes/node_rrf.py
from typing import List, Tuple, Dict, Optional

from processor.query_processor.base import NodeBase
from processor.query_processor.state import QueryGraphState
from tool.logger import logger
from utils.json_format_utils import serialize_json
from utils.task_utils import add_done_task


class NodeRrf(NodeBase):
    """
    节点功能：Reciprocal Rank Fusion
    将多路召回的结果（向量、HyDE）进行加权融合排序。
    """

    name: str = "node_rrf"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        """
        节点逻辑
        :param state: 工作流状态对象
        :return: 更新后的状态对象
        """

        embedding_chunks_list = state.get("embedding_chunks") or []
        hyde_embedding_chunks_list = state.get("hyde_embedding_chunks") or []

        # 提取 entity，并过滤掉非字典或缺失 chunk_id 的文档
        embedding_search_list = []
        for doc in embedding_chunks_list:
            if isinstance(doc, dict):
                entity = doc.get("entity")
                if isinstance(entity, dict) and entity.get("chunk_id") is not None:
                    embedding_search_list.append(entity)

        hyde_embedding_search_list = []
        for doc in hyde_embedding_chunks_list:
            if isinstance(doc, dict):
                entity = doc.get("entity")
                if isinstance(entity, dict) and entity.get("chunk_id") is not None:
                    hyde_embedding_search_list.append(entity)

        # 支持从 state 中读取权重（可配置），未设置时默认为 1.0
        weight_embedding = state.get("rrf_weight_embedding", 1.0)
        weight_hyde = state.get("rrf_weight_hyde", 1.0)

        rrf_inputs = [
            (embedding_search_list, weight_embedding),
            (hyde_embedding_search_list, weight_hyde)
        ]

        # 融合，取 Top-3（可根据需要调整）
        rrf_merge_results = self._rrf_merge(rrf_inputs, max_results=3)
        rrf_chunks = [doc for doc, _ in rrf_merge_results]

        state["rrf_chunks"] = rrf_chunks
        add_done_task(state.get("session_id"), self.name, state.get("is_stream"))
        return state

    def _rrf_merge(
        self,
        rrf_inputs: List[Tuple[List[Dict], float]],
        k: int = 60,
        max_results: Optional[int] = None
    ) -> List[Tuple[Dict, float]]:
        """
        RRF (Reciprocal Rank Fusion) 融合算法
        :param rrf_inputs: 输入数据列表，每个元素是一个元组 (文档列表, 权重)
        :param k: RRF中的平滑参数
        :param max_results: 最大结果数量限制，None 表示返回全部
        :return: 融合后的结果列表 [({}, 得分), ...]
        """

        chunk_data = {}      # chunk_id -> 文档实体（保留第一次出现的）
        chunk_scores = {}    # chunk_id -> 累计 RRF 得分

        for doc_list, weight in rrf_inputs:
            for rank, doc in enumerate(doc_list, start=1):
                chunk_id = doc.get("chunk_id")
                if chunk_id is None:
                    continue  # 跳过无标识文档

                # 累加得分
                score = weight / (k + rank)
                chunk_scores[chunk_id] = chunk_scores.get(chunk_id, 0.0) + score

                # 保留第一次出现的文档（通常同一 chunk_id 内容一致）
                if chunk_id not in chunk_data:
                    chunk_data[chunk_id] = doc

        # 组装并排序
        unsorted = [(chunk_data[cid], score) for cid, score in chunk_scores.items()]
        sorted_results = sorted(unsorted, key=lambda x: x[1], reverse=True)
        return sorted_results[:max_results] if max_results else sorted_results


if __name__ == '__main__':
    # 模拟两路检索结果
    mock_state = {
        "embedding_chunks": [
            {"entity": {"chunk_id": "chunk_1", "content": "向量搜索结果#1"}},
            {"entity": {"chunk_id": "chunk_2", "content": "向量搜索结果#2"}},
            {"entity": {"chunk_id": "chunk_3", "content": "向量搜索结果#3"}},
        ],
        "hyde_embedding_chunks": [
            {"entity": {"chunk_id": "chunk_1", "content": "HyDE搜索结果#1"}},
            {"entity": {"chunk_id": "chunk_4", "content": "HyDE搜索结果#2"}},
            {"entity": {"chunk_id": "chunk_2", "content": "HyDE搜索结果#3"}},
        ]
    }

    node_rrf = NodeRrf()
    result = node_rrf(mock_state)
    logger.info(serialize_json(result, indent=4))