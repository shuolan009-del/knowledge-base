# processor/query_processor/nodes/node_rerank.py
from typing import Dict, Any, List

from processor.query_processor.base import NodeBase
from processor.query_processor.state import QueryGraphState
from tool.logger import logger
from utils.json_format_utils import serialize_json
from utils.reranker_http_utils import rerank_documents
from utils.task_utils import add_done_task

# -----------------------------
# Rerank / TopK 全局常量
# -----------------------------
RERANK_MAX_TOPK: int = 10          # 硬上限
RERANK_MIN_TOPK: int = 3           # 最小保留条数
RERANK_GAP_ABS: float = 0.5        # 绝对断崖阈值
RERANK_GAP_RATIO: float = 0.25     # 相对断崖阈值


class NodeRerank(NodeBase):
    name: str = "node_rerank"

    def process(self, state: QueryGraphState) -> QueryGraphState:
        # 1. 合并多源文档（已做空值保护）
        merged_multi_docs = self._step_1_merge_multi_source_docs(state)

        if not merged_multi_docs:
            logger.warning("合并后的文档列表为空，跳过重排序。")
            state["reranked_docs"] = []
            add_done_task(state.get("session_id"), self.name, state.get("is_stream"))
            return state

        # 2. Rerank 精排
        reranked_docs = self._step_2_rerank_merged_docs(state, merged_multi_docs)

        # 3. 动态 Top_K 截取（断崖检测）
        cutoff_docs = self._step_3_cliff_cutoff(reranked_docs)

        state["reranked_docs"] = cutoff_docs
        add_done_task(state.get("session_id"), self.name, state.get("is_stream"))
        return state

    def _step_1_merge_multi_source_docs(self, state: QueryGraphState) -> List[Dict[str, Any]]:
        """合并本地 RRF 结果和网络搜索结果为统一格式，并防御 None"""
        final_docs = []

        # 安全获取 rrf_chunks，若不存在或为 None 则用空列表
        rrf_chunks = state.get("rrf_chunks") or []
        for rrf_doc in rrf_chunks:
            format_rrf_doc = {
                "content": rrf_doc.get("content"),
                "title": rrf_doc.get("title"),
                "chunk_id": rrf_doc.get("chunk_id"),
                "url": None,
                "source": "local",
            }
            final_docs.append(format_rrf_doc)

        # 安全获取 web_search_docs
        web_docs = state.get("web_search_docs") or []
        for web_doc in web_docs:
            format_web_doc = {
                "content": web_doc.get("snippet"),
                "title": web_doc.get("title"),
                "chunk_id": None,
                "url": web_doc.get("url"),
                "source": "web",
            }
            final_docs.append(format_web_doc)

        return final_docs

    def _step_2_rerank_merged_docs(
        self, state: QueryGraphState, merged_multi_docs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """使用 Reranker 模型对文档进行精排"""
        try:
            user_query = state.get("rewritten_query")
            if not user_query:
                logger.warning("rewritten_query 为空，无法进行重排序，返回原始顺序。")
                # 无 query 时，直接给每个文档赋 score=None，保持原有顺序
                return [{**doc, "score": None} for doc in merged_multi_docs]

            # 提取内容列表
            contents = [doc.get("content", "") for doc in merged_multi_docs]
            if not contents or all(c is None or c == "" for c in contents):
                logger.warning("文档内容为空，无法重排序，返回原始顺序。")
                return [{**doc, "score": None} for doc in merged_multi_docs]

            # 调用重排序服务
            rerank_scores = rerank_documents(user_query, contents)
            if len(rerank_scores) != len(merged_multi_docs):
                logger.error(f"重排序返回的分数数量 ({len(rerank_scores)}) 与文档数量 ({len(merged_multi_docs)}) 不匹配，降级返回原始顺序。")
                return [{**doc, "score": None} for doc in merged_multi_docs]

            # 组装得分
            scored_docs = [{**doc, "score": float(score)} for doc, score in zip(merged_multi_docs, rerank_scores)]

            # 按分数降序排序
            sorted_score_docs = sorted(scored_docs, key=lambda x: x["score"], reverse=True)
            return sorted_score_docs

        except Exception as e:
            logger.error(f"Rerank 重排序失败: {str(e)}，降级返回原始顺序（无得分）。")
            return [{**doc, "score": None} for doc in merged_multi_docs]

    def _step_3_cliff_cutoff(self, ranked_docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """断崖检测截断：相邻得分差距超过阈值时截断。"""
        if not ranked_docs:
            return []

        total = len(ranked_docs)
        upper_bound = min(RERANK_MAX_TOPK, total)
        lower_bound = min(RERANK_MIN_TOPK, upper_bound)

        cutoff_pos = upper_bound  # 默认取满上限

        # 从第 lower_bound 条开始检测，直到第 upper_bound-1 条
        for idx in range(lower_bound - 1, upper_bound - 1):
            current_score = ranked_docs[idx].get("score")
            next_score = ranked_docs[idx + 1].get("score")

            # 若任一分数缺失，跳过该次检测
            if current_score is None or next_score is None:
                continue

            abs_gap = current_score - next_score  # 因已降序，非负
            rel_gap = abs_gap / (abs(current_score) + 1e-6)

            if abs_gap >= RERANK_GAP_ABS or rel_gap >= RERANK_GAP_RATIO:
                cutoff_pos = idx + 1
                logger.debug(f"断崖检测触发: 位置 {idx + 1}, abs_gap={abs_gap:.4f}, rel_gap={rel_gap:.4f}")
                break

        return ranked_docs[:cutoff_pos]


if __name__ == "__main__":
    mock_state = {
        "rewritten_query": "怎么测这块主板的短路问题？",
        "rrf_chunks": [
            {
                "chunk_id": "local_1",
                "title": "主板维修手册",
                "content": "主板短路通常表现为通电后风扇转一下就停，可以使用万用表的蜂鸣档测量。"
            },
            {
                "chunk_id": "local_2",
                "title": "闲聊",
                "content": "今天中午去吃猪脚饭吧，这块主板外观很漂亮。"
            },
        ],
        "web_search_docs": [
            {
                "url": "https://example.com/repair",
                "title": "短路查修指南",
                "snippet": "主板通电前先打各主供电电感对地阻值，阻值偏低就是短路。"
            },
            {
                "url": "https://example.com/news",
                "title": "科技新闻",
                "snippet": "苹果发布新款手机，A系列芯片性能提升20%。"
            },
        ],
    }

    node_rerank = NodeRerank()
    result = node_rerank(mock_state)
    logger.info(serialize_json(result, indent=4))