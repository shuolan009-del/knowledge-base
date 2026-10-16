# utils/history_utils.py
"""
会话历史存储（SQLite，原 MongoDB 的轻量替代）

服务器 2C2G 部署：零中间件、零常驻进程，数据即一个 .db 文件（默认 ./data/history.db）。
对外接口与原 MongoDB 版完全一致：save_chat_message / update_message_item_names /
get_recent_messages / clear_history。
历史数据如需从旧 MongoDB 迁移，可按 _to_message_dict 的字段结构导出导入。
"""
import json
import os
import sqlite3
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from tool.logger import logger

load_dotenv()

# 写操作用锁串行化（SQLite 单文件写并发），读走 WAL 快照不阻塞
_LOCK = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _db_path() -> str:
    path = os.getenv("HISTORY_DB_PATH", "./data/history.db")
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    return path


def _get_conn() -> sqlite3.Connection:
    """单例连接（懒加载）：首次调用时自动建表建索引"""
    global _conn
    if _conn is None:
        conn = sqlite3.connect(_db_path(), check_same_thread=False, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_message (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                rewritten_query TEXT DEFAULT '',
                item_names TEXT,
                image_urls TEXT,
                ts REAL NOT NULL
            )
        """)
        # 复合索引：session_id 升序 + ts 降序，适配"按会话查最近记录"
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_chat_message_session_ts
            ON chat_message(session_id, ts)
        """)
        conn.commit()
        _conn = conn
        logger.info(f"SQLite 历史库已连接: {_db_path()}")
    return _conn


def _to_message_dict(row: sqlite3.Row) -> Dict[str, Any]:
    """行数据转消息字典（字段名与原 MongoDB 版对齐，含 _id 字符串）"""
    item_names = row["item_names"]
    image_urls = row["image_urls"]
    return {
        "_id": str(row["id"]),
        "session_id": row["session_id"],
        "role": row["role"],
        "text": row["text"],
        "rewritten_query": row["rewritten_query"] or "",
        "item_names": json.loads(item_names) if item_names else None,
        "image_urls": json.loads(image_urls) if image_urls else None,
        "ts": row["ts"],
    }


def save_chat_message(
        session_id: str, role: str, text: str,
        rewritten_query: str = "",
        item_names: List[str] = None,
        image_urls: List[str] = None,
        message_id: str = None
) -> str:
    """
    写入/更新单条会话记录到 SQLite
    支持两种模式：无message_id时新增记录，有message_id时更新已有记录
    :param session_id: 会话唯一标识，关联对话所属的会话
    :param role: 消息角色，固定值：user（用户）/assistant（助手）
    :param text: 对话核心内容，用户的提问或助手的回答
    :param rewritten_query: 重写后的查询语句（可选，用于检索增强等场景，默认空字符串）
    :param item_names: 关联的商品名称列表（可选，支持多商品，默认None）
    :param image_urls: 关联的图片URL列表（可选，默认None）
    :param message_id: 记录主键ID（可选，有值则更新，无值则新增）
    :return: 插入/更新的记录唯一标识（新增返回自增ID字符串，更新返回传入的message_id）
    """
    ts = datetime.now().timestamp()
    item_names_json = json.dumps(item_names, ensure_ascii=False) if item_names is not None else None
    image_urls_json = json.dumps(image_urls, ensure_ascii=False) if image_urls is not None else None

    with _LOCK:
        conn = _get_conn()
        if message_id:
            # 更新：按主键定位，保留与原 MongoDB $set 语义一致
            try:
                numeric_id = int(message_id)
            except (TypeError, ValueError):
                logger.error(f"非法的 message_id: {message_id!r}，无法更新")
                return message_id
            conn.execute(
                """UPDATE chat_message
                   SET session_id=?, role=?, text=?, rewritten_query=?,
                       item_names=?, image_urls=?, ts=?
                   WHERE id=?""",
                (session_id, role, text, rewritten_query or "",
                 item_names_json, image_urls_json, ts, numeric_id)
            )
            conn.commit()
            return message_id

        cursor = conn.execute(
            """INSERT INTO chat_message
               (session_id, role, text, rewritten_query, item_names, image_urls, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (session_id, role, text, rewritten_query or "",
             item_names_json, image_urls_json, ts)
        )
        conn.commit()
        return str(cursor.lastrowid)


def update_message_item_names(ids: List[str], item_names: List[str]) -> int:
    """
    批量更新历史会话记录的关联商品名称
    :param ids: 要更新的记录主键ID列表（字符串类型）
    :param item_names: 要设置的新商品名称列表
    :return: 实际更新的记录数量，失败返回0
    """
    try:
        numeric_ids = [int(i) for i in ids]
    except (TypeError, ValueError) as e:
        logger.error(f"非法的记录ID列表: {ids}，错误: {e}")
        return 0
    if not numeric_ids:
        return 0

    item_names_json = json.dumps(item_names, ensure_ascii=False) if item_names is not None else None
    placeholders = ",".join("?" * len(numeric_ids))
    try:
        with _LOCK:
            conn = _get_conn()
            cursor = conn.execute(
                f"UPDATE chat_message SET item_names=? WHERE id IN ({placeholders})",
                (item_names_json, *numeric_ids)
            )
            conn.commit()
            count = cursor.rowcount
        logger.info(f"Updated {count} records to item_names: {item_names}")
        return count
    except Exception as e:
        logger.error(f"Error updating history item_names: {e}")
        return 0


def get_recent_messages(session_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    查询指定会话的最近N条对话记录，返回原始字典格式
    结果按时间正序排列，可直接喂给LLM作为上下文
    :param session_id: 会话唯一标识，用于筛选指定会话的记录
    :param limit: 条数限制，默认返回最近10条
    :return: 对话记录列表（字典格式），查询失败返回空列表
    """
    try:
        with _LOCK:
            conn = _get_conn()
            rows = conn.execute(
                "SELECT * FROM chat_message WHERE session_id=? ORDER BY ts ASC LIMIT ?",
                (session_id, limit)
            ).fetchall()
        return [_to_message_dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting recent messages: {e}")
        return []


def clear_history(session_id: str) -> int:
    """
    清空指定会话的所有历史对话记录
    :param session_id: 会话唯一标识，用于筛选要删除的记录
    :return: 实际删除的记录数量，删除失败返回0
    """
    try:
        with _LOCK:
            conn = _get_conn()
            cursor = conn.execute(
                "DELETE FROM chat_message WHERE session_id=?",
                (session_id,)
            )
            conn.commit()
        count = cursor.rowcount
        logger.info(f"Deleted {count} messages for session {session_id}")
        return count
    except Exception as e:
        logger.error(f"Error clearing history for session {session_id}: {e}")
        return 0


if __name__ == "__main__":
    clear_history("test_session_002")
