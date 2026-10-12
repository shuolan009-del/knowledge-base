from dataclasses import  dataclass , field
from typing import Optional
import datetime

@dataclass
class SimpleLogger:
    """日志记录器类"""
    #简单默认值
    log_level: str = 'INFO'
    # 动态默认值：每次实例化时动态获取当前时间
    init_time : str = field(default=lambda : datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))

    def log(self , message : str):
        print(f"[{self.init_time}]  [{self.log_level}] {message}")

_logger_instance : Optional[SimpleLogger] = None

def get_logger() -> SimpleLogger:
    global _logger_instance
    if _logger_instance is None:
        _logger_instance = SimpleLogger()

    return _logger_instance

if __name__ == "__main__":
    print("--- 第一次获取 Logger ---")
    logger1 = get_logger()
    logger1.log("这是第一条日志。")

    # 故意延迟一下，验证 init_time 是否会变
    import time

    time.sleep(1)

    print("\n--- 第二次获取 Logger ---")
    logger2 = get_logger()
    logger2.log("这是第二条日志。")

    print("\n--- 验证唯一性 ---")
    # 检查两个变量指向的是否是内存中的同一个对象
    is_same = logger1 is logger2
    print(f"logger1 和 logger2 是同一个实例吗？ {is_same}")
    # 输出: True