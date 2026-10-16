import json
import logging
from typing import Dict, Any, List

from pymilvus import DataType
from pymilvus.exceptions import MilvusException

from config.milvus_config import milvus_config
from processor.import_processor.base import BaseNode, setup_logging
from processor.import_processor.exceptions import StateFieldError, MilvusError
from processor.import_processor.state import ImportGraphState
from utils.milvus_utils import get_milvus_client, escape_milvus_string

# 导入milvus
class NodeImportMilvus(BaseNode):
    """
    导入向量库节点：数据持久化
    修复：title超长报错，新增full_title存完整标题，title截断；批量入库容错
    """

    name: str = "node_import_milvus"

    def process(self, state: ImportGraphState) -> ImportGraphState:
        """
        LangGraph核心节点：Milvus切片数据入库主流程
        执行流程（串行执行，一步一校验，保证数据一致性）：
            1. 输入校验：验证切片有效性、向量字段完整性，提取向量维度
            2. 环境准备：连接Milvus，集合不存在则自动创建Schema+索引
            3. 幂等清理：删除同file_title旧数据，避免重复存储
            4. 批量插入：预处理截断title，分批容错入库，回填Milvus自增chunk_id
            5. 状态更新：将回填了chunk_id的切片更新回全局状态，供下游使用

        异常处理：
            任一步骤失败抛出异常，终止节点执行，保证数据不脏写
        """

        # 步骤1：输入数据有效性校验
        chunks_json_data, vector_dimension = self._step_1_check_input(state)

        # 步骤2：Milvus客户端连接+集合准备（自动建表）
        client = self._step_2_prepare_collection(vector_dimension)

        # 步骤3：幂等性处理 - 清理同file_title旧数据
        self._step_3_clean_old_data(client, chunks_json_data)

        # 步骤4：批量插入数据+主键chunk_id回填（已做标题截断+分批容错）
        updated_chunks = self._step_4_insert_data(client, chunks_json_data)

        # 步骤5：更新全局状态，将回填后的切片回传下游
        state["chunks"] = updated_chunks

        return state

    def _step_1_check_input(self, state: Dict[str, Any]) -> tuple[List[Dict[str, Any]], int]:
        """
        步骤1：输入数据有效性校验
        """
        chunks = state.get("chunks")

        if not chunks:
            raise StateFieldError(field_name="chunks", message="chunks不能为空", expected_type=list)

        if not isinstance(chunks, list):
            raise StateFieldError(field_name="chunks", message="chunks数据类型不正确", expected_type=list)

        first_chunk = chunks[0]
        if 'dense_vector' not in first_chunk:
            raise StateFieldError(field_name="chunks", message="错误: 数据中缺失dense_vector字段")

        vector_dimension = len(first_chunk['dense_vector'])
        return chunks, vector_dimension

    def _step_2_prepare_collection(self, vector_dimension: int):
        """
        步骤2：Milvus客户端连接+集合准备
        """
        milvus_client = get_milvus_client()
        if not milvus_client:
            self.logger.error("Milvus 连接失败")
            raise MilvusError("Milvus 连接失败")

        collections_name = milvus_config.chunks_collection
        if not milvus_client.has_collection(collections_name):
            self._create_chunks_collection(collections_name, milvus_client, vector_dimension)

        return milvus_client

    def _create_chunks_collection(self, collections_name, milvus_client, vector_dimension):
        """
        新建切片集合 schema（dense-only）
        注意：local-onnx / api 模式不含 sparse_vector 字段；
        若使用旧版 (dense+sparse) 集合残留，请改 .env 的 CHUNKS_COLLECTION 换新集合名，或手动 drop 旧集合。
        """
        # 新建schema，新增full_title完整标题字段
        schema = milvus_client.create_schema(auto_id=True, enable_dynamic_field=True)
        schema.add_field(field_name="chunk_id", datatype=DataType.INT64, is_primary=True, auto_id=True)
        schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=65535)
        schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=100)  # 保留原有100限制
        schema.add_field(field_name="full_title", datatype=DataType.VARCHAR, max_length=500, default_value="")  # 新增：完整标题
        schema.add_field(field_name="parent_title", datatype=DataType.VARCHAR, max_length=100, default_value="")
        schema.add_field(field_name="part", datatype=DataType.INT8)
        schema.add_field(field_name="file_title", datatype=DataType.VARCHAR, max_length=100)
        schema.add_field(field_name="item_name", datatype=DataType.VARCHAR, max_length=100)
        schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=vector_dimension)

        # 索引逻辑：仅保留稠密向量索引
        index_params = milvus_client.prepare_index_params()
        index_params.add_index(
            field_name="dense_vector",
            index_name="dense_vector_index",
            index_type="AUTOINDEX",
            metric_type="COSINE"
        )

        milvus_client.create_collection(
            collection_name=collections_name,
            schema=schema,
            index_params=index_params
        )

    def _step_3_clean_old_data(self, client, chunks_json_data):
        """幂等清理"""
        file_title = chunks_json_data[0].get("file_title")
        self._clear_chunks_by_file_title(client, file_title)

    def _clear_chunks_by_file_title(self, client, file_title):
        try:
            file_title = escape_milvus_string(file_title)
            client.delete(
                collection_name=milvus_config.chunks_collection,
                filter=f"file_title=='{file_title}'"
            )
        except Exception as e:
            self.logger.error(f"Milvus 数据删除失败: {str(e)}")
            raise MilvusError(f"Milvus 数据删除失败: {str(e)}")

    @staticmethod
    def _truncate_short_title(text: str, max_len=100) -> str:
        """标题截断工具：严格控制100字符，末尾加省略号"""
        if len(text) <= max_len:
            return text
        return text[:max_len - 3] + "..."

    def _step_4_insert_data(self, client, chunks_json_data):
        """
        步骤4：入库主逻辑
        1. 预处理：原始标题存入full_title，title截断到100字符
        2. 分批入库，单条异常不阻塞全量，错误日志落地
        3. 最终回填chunk_id给所有正常数据
        """
        # ========== 1、统一预处理所有chunk，解决超长 ==========
        for item in chunks_json_data:
            item["part"] = 0
            raw_title = item.get("title", "")
            # 完整标题存入新字段
            item["full_title"] = raw_title
            # 短标题强制截断适配varchar(100)
            item["title"] = self._truncate_short_title(raw_title, max_len=100)

        coll_name = milvus_config.chunks_collection
        batch_size = 30  # 可根据业务调整批次大小
        final_success_data = []
        error_rows = []

        # ========== 2、分批循环入库，容错重试 ==========
        total_count = len(chunks_json_data)
        for start in range(0, total_count, batch_size):
            end = start + batch_size
            batch = chunks_json_data[start:end]
            try:
                # 尝试整批插入
                insert_res = client.insert(collection_name=coll_name, data=batch)
                ids = insert_res.get("ids", [])
                # 绑定id
                for idx, row in enumerate(batch):
                    row["chunk_id"] = ids[idx]
                final_success_data.extend(batch)
            except MilvusException as e:
                # 捕获Milvus报错，超长问题走单行降级重试
                self.logger.warning(f"批次 {start}~{end} 批量插入失败，原因：{str(e)}，开始单行重试")
                if "exceeds max length" in str(e):
                    # 逐条尝试，跳过坏数据
                    for row_idx, single_row in enumerate(batch):
                        real_index = start + row_idx
                        try:
                            single_res = client.insert(collection_name=coll_name, data=[single_row])
                            single_row["chunk_id"] = single_res["ids"][0]
                            final_success_data.append(single_row)
                        except Exception as err:
                            error_rows.append({
                                "global_row_index": real_index,
                                "title": single_row.get("title"),
                                "full_title": single_row.get("full_title"),
                                "error": str(err)
                            })
                            self.logger.error(f"第{real_index}行入库彻底失败: {err}")
                else:
                    # 非超长异常，直接抛出终止
                    raise MilvusError(f"批量Milvus入库异常：{e}") from e
            except Exception as other_err:
                raise MilvusError(f"批量入库未知异常：{other_err}") from other_err

        # ========== 3、日志汇总 ==========
        self.logger.info(f"Milvus入库完成，总条数：{total_count}，成功入库：{len(final_success_data)}，失败：{len(error_rows)}")
        if error_rows:
            self.logger.error(f"入库失败明细：{json.dumps(error_rows, ensure_ascii=False)}")

        return final_success_data

#测试
if __name__ == "__main__":
    setup_logging()

    json_path = r"D:\output\hak180产品安全手册\state_vector.json"
    with open(json_path, "r", encoding="utf-8") as f:
        state_json = f.read()

    state = json.loads(state_json)

    init_state = {
        "chunks": state.get("chunks")
    }

    node_import_milvus = NodeImportMilvus()
    result = node_import_milvus(init_state)

    logging.getLogger().info(json.dumps(result, ensure_ascii=False, indent=4))