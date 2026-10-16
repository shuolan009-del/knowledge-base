import os
import shutil
import uuid
from datetime import datetime
from fileinput import filename
from pathlib import Path
from typing import List, Dict, Any

from starlette.responses import FileResponse

from config.storage_config import storage_config
from processor.import_processor.main_graph import KBImportWorkflow
from tool.logger import logger
import uvicorn
from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware

from utils.storage_utils import save_file
from utils.task_utils import (
    update_task_status,
    add_done_task,
    add_running_task,
    get_task_status as get_task_status_async,   # 重命名导入
    get_done_task_list,
    get_running_task_list
)

# 1. 创建应用
app = FastAPI(
    title="BOSS智库-导入API",
    description="此文档是BOSS智库导入流程的API接口说明"
)

# 2. 跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. 静态资源路由：本地存储目录（图片等）挂载到 /storage
os.makedirs(storage_config.local_dir, exist_ok=True)
app.mount("/storage", StaticFiles(directory=storage_config.local_dir), name="storage")

# 4. 静态页面路由
@app.get("/import.html")
async def get_import_page():
    current_dir_parent_path = Path(__file__).absolute().parent.parent
    html_path = current_dir_parent_path / "page" / "import.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail=f"没有查询到页面，地址为：{html_path}")
    return FileResponse(html_path)

# 4. 后台任务：LangGraph全流程执行
def run_graph_task(task_id: str, file_dir: str, import_file_path: str):
    try:
        update_task_status(task_id, "processing")

        init_state = {
            "task_id": task_id,
            "file_dir": file_dir,
            "import_file_path": import_file_path,
        }

        workflow = KBImportWorkflow()
        for event in workflow.run(init_state, stream=True):
            for node_name, node_result in event.items():
                add_done_task(task_id, node_name)

        update_task_status(task_id, "completed")

    except Exception as e:
        update_task_status(task_id, "failed")
        logger.info(f"[{task_id}] LangGraph全流程执行失败，异常信息：{str(e)}", exc_info=True)

# 5. 文件上传接口
@app.post("/upload", summary="文件上传接口", description="支持多文件批量上传，自动触发知识库导入全流程")
async def upload_files(background_tasks: BackgroundTasks, files: List[UploadFile] = File(...)):
    data_based_root_dir = os.getenv("DATA_BASED_ROOT_DIR")
    data_dir = os.path.join(data_based_root_dir, datetime.now().strftime("%Y%m%d"))
    task_ids = []

    for file in files:
        task_id = str(uuid.uuid4())
        task_ids.append(task_id)
        logger.info(f"[{task_id}] 开始处理上传文件，文件名：{file.filename}，文件类型：{file.content_type}")

        add_running_task(task_id, "upload_file")

        file_dir = os.path.join(data_dir, task_id)
        os.makedirs(file_dir, exist_ok=True)
        import_file_path = os.path.join(file_dir, file.filename)

        with open(import_file_path, "wb") as file_buffer:
            shutil.copyfileobj(file.file, file_buffer)
        logger.info(f"[{task_id}] 文件已保存至本地，路径：{import_file_path}")

        # 原始文件已保存在本地 import_file_path，此处额外备份到本地存储目录（对应原 MinIO 备份）
        storage_object_name = f"pdf_files/{datetime.now().strftime('%Y%m%d')}/{file.filename}"
        try:
            if save_file(import_file_path, storage_object_name) is None:
                raise RuntimeError("save_file 返回空")
            logger.info(f"[{task_id}] 文件已成功备份至本地存储，对象名：{storage_object_name}")
        except Exception as e:
            logger.warning(f"[{task_id}] 文件备份本地存储失败，将继续执行本地处理流程，异常信息：{str(e)}", exc_info=True)

        add_done_task(task_id, "upload_file")

        background_tasks.add_task(run_graph_task, task_id, file_dir, import_file_path)
        logger.info(f"[{task_id}] 已将LangGraph全流程加入后台任务，任务已启动")

    logger.info(f"多文件上传处理完毕，共处理{len(files)}个文件，生成TaskID列表：{task_ids}")
    return {
        "code": 200,
        "message": f"文件上传成功, total: {len(files)}",
        "task_ids": task_ids
    }

# 6. 任务状态查询接口（修复后）
# 导入部分（保持原有）
from utils.task_utils import (
    update_task_status,
    add_done_task,
    add_running_task,
    get_task_status,          # 直接导入同步函数
    get_done_task_list,
    get_running_task_list
)

# 状态查询接口
@app.get("/status/{task_id}", summary="任务状态查询", description="根据TaskID查询单个文件的处理进度和全局状态")
async def get_task_status_endpoint(task_id: str):
    # 直接调用同步函数
    status = get_task_status(task_id)
    done_list = get_done_task_list(task_id)
    running_list = get_running_task_list(task_id)

    task_status_info = {
        "code": 200,
        "task_id": task_id,
        "status": status,
        "done_list": done_list,
        "running_list": running_list
    }
    logger.info(f"[{task_id}] 任务状态查询，当前状态：{status}，已完成节点：{done_list}")
    return task_status_info

if __name__ == "__main__":
    logger.info("BOSS智库服务启动中...")
    uvicorn.run(
        app=app,
        host="127.0.0.1",
        port=8000
    )