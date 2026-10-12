import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from tool.logger import logger
from fastapi import HTTPException
app = FastAPI()


@app.get("/" , summary="第一个测试")
async def read_root():
    return {"Hello": "World"}

@app.get("/items/{item_id}", summary="获取指定参数")
async def read_item(item_id: int , q: str | None = None):
    return {"item_id": item_id, "q": q}

@app.get("/items" , summary="分页")
async def read_items(skip: int = 0 , limit: int = 10):
    return {"skip": skip, "limit": limit}

class Item(BaseModel):
    name: str
    price: float
    is_offer:bool = None

@app.post('/items/', summary="类型检查")
async def create_item(item: Item):
    return {"name": item.name, "price": item.price, "is_offer": item.is_offer}

@app.post("/items/return", summary="返回 pydantic 模型实例")
async def create_item(item: Item):
    return item

@app.delete("/items/{item_id}")
async def read_item(item_id: int):
    if item_id == 42:
        raise
    HTTPException(status_code=404,
                  detail="ITEm 找不到")
    return {"item_id": item_id}




if __name__ == "__main__":
    """服务启动入口：本地开发环境直接运行"""
    logger.info("File Import Service 服务启动中...")
    # 启动uvicorn服务，绑定本地IP和8000端口，关闭自动重载（生产环境建议用workers多进程）
    uvicorn.run(
        app=app,
        host="127.0.0.1",  # 仅本地访问，生产环境改为0.0.0.0（允许所有IP访问）
        port=8000  # 服务端口
    )




