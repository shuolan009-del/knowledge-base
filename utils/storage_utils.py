# utils/storage_utils.py
"""
本地文件存储工具（替代 MinIO）：
- save_file : 将本地文件复制进存储目录，返回对外访问 URL
- build_url : 由存储内相对路径生成访问 URL
- clean_dir : 清理存储内某个子目录（按文档维度幂等）

对应原 MinIO 的 fput_object / URL 拼接 / remove_objects 三件套，
服务器部署时零中间件、零额外内存。
"""
import os
import shutil

from config.storage_config import storage_config
from tool.logger import logger


def ensure_dirs() -> None:
    """确保存储根目录存在（幂等）"""
    os.makedirs(storage_config.img_root, exist_ok=True)
    os.makedirs(storage_config.local_dir, exist_ok=True)


def build_url(object_name: str) -> str:
    """
    由存储内相对路径生成对外访问 URL
    :param object_name: 如 images/hak180手册/abc.jpg
    :return: 如 /storage/images/hak180手册/abc.jpg
    """
    return f"{storage_config.url_base}/{object_name}".replace("\\", "/")


def save_file(local_path: str, object_name: str) -> str | None:
    """
    将本地文件复制到存储目录，返回访问 URL
    :param local_path: 源文件完整路径
    :param object_name: 存储内相对路径
    :return: 访问 URL，失败返回 None
    """
    try:
        ensure_dirs()
        dest = os.path.join(storage_config.local_dir, object_name)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(local_path, dest)
        return build_url(object_name)
    except Exception as e:
        logger.error(f"保存文件到本地存储失败: {local_path} -> {object_name}, 错误: {e}")
        return None


def clean_dir(prefix: str) -> None:
    """
    删除存储目录下指定子目录（对应原 MinIO 按文档清理旧图片）
    :param prefix: 存储内相对目录，如 images/hak180手册
    """
    prefix = prefix.strip("/")
    if not prefix:
        return
    target = os.path.join(storage_config.local_dir, prefix)
    try:
        if os.path.isdir(target):
            shutil.rmtree(target)
            logger.info(f"已清理本地存储目录: {target}")
    except Exception as e:
        logger.error(f"清理本地存储目录失败: {target}, 错误: {e}")


def get_storage_root() -> str:
    """存储根目录绝对路径（供静态路由挂载使用）"""
    return os.path.abspath(storage_config.local_dir)
