import asyncio

from fastapi import BackgroundTasks, FastAPI
import time

app = FastAPI()


def write_log1(email: str , content:str):
    while True:
        print(f"异步任务正在执行。。。向{email} 发送邮件 内容是 {content} {time.asctime()}")
        time.sleep(1)

async def write_log2(email: str, content: str):
    while True:
        print(f"异步任务正在执行...... 向 {email} 发邮件，内容是：{content}  {time.asctime()}")
        await asyncio.sleep(1)
@app.post("/send-task/{email}")
async def send_task(email: str, background_tasks: BackgroundTasks):
    # 1. 添加任务到后台队列
    background_tasks.add_task(write_log2, email, "你好")

    # 2. 立即返回响应给用户，不需要等待 write_log 执行完毕
    return {"message": "异步任务已启动"}



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
