# config/storage_config.py
"""
本地文件存储配置（替代原 MinIO 对象存储，服务器 2C2G 部署零中间件）

目录结构：
    <STORAGE_LOCAL_DIR>/
    ├── <STORAGE_IMG_DIR>/<文档名>/<图片>      # 知识库图片（MD 引用）
    └── pdf_files/<日期>/<原始PDF>              # 上传备份

访问方式：API 将 STORAGE_LOCAL_DIR 挂载到 /storage 静态路由，
URL = <STORAGE_URL_BASE>/<object_name>，默认相对路径 /storage/...
"""
from dataclasses import dataclass
import os

from dotenv import load_dotenv

# 注意：不加 override=True——真实环境变量优先（docker -e / CI / systemd），
# 与本项目其他模块的 load_dotenv() 行为一致，.env 只做缺省兜底
load_dotenv()


@dataclass
class StorageConfig:
    local_dir: str  # 本地存储根目录
    img_dir: str    # 图片子目录（兼容读取旧变量 MINIO_IMG_DIR）
    url_base: str   # 对外 URL 前缀（静态路由挂载点）

    @property
    def img_root(self) -> str:
        """图片存储根目录（绝对路径）"""
        return os.path.join(self.local_dir, self.img_dir)


storage_config = StorageConfig(
    local_dir=os.getenv("STORAGE_LOCAL_DIR", "./storage"),
    img_dir=os.getenv("STORAGE_IMG_DIR") or os.getenv("MINIO_IMG_DIR") or "images",
    url_base=(os.getenv("STORAGE_URL_BASE") or "/storage").rstrip("/"),
)
