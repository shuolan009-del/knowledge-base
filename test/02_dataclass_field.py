# test/02_dataclass_field.py

from dataclasses import dataclass, field


@dataclass
class User:
    # 1. 必需字段：没有默认值，创建实例时必须提供
    username: str

    # 2. 简单默认值：适用于不可变类型 (str, int, float等)
    age: int = 18

    # 3. 动态默认值：适用于可变类型 (list, dict等)，防止实例间共享状态
    tags: list = field(default_factory=list)


# --- 开始测试 ---

print("--- 测试 1: 只提供必需字段 ---")
user1 = User("Alice")
print(f"user1: {user1}")
# 输出: user1: User(username='Alice', age=18, tags=[])

print("\n--- 测试 2: 提供所有字段 ---")
user2 = User("Bob", 25, ["developer", "pythonist"])
print(f"user2: {user2}")
# 输出: user2: User(username='Bob', age=25, tags=['developer', 'pythonist'])

print("\n--- 测试 3: 验证可变默认值的独立性 ---")
# 这是使用 field(default_factory=list) 的关键原因
user3 = User("Charlie")
user4 = User("David")

# 修改 user3 的 tags 列表
user3.tags.append("new_tag")

print(f"user3.tags: {user3.tags}")
print(f"user4.tags: {user4.tags}")

# 如果这里使用的是 tags: list = []，那么 user4.tags 也会包含 'new_tag'
# 但因为使用了 default_factory，每个实例都有自己独立的列表
# 输出:
# user3.tags: ['new_tag']
# user4.tags: []
# ----------------------------------------------------------
# class User:
#     tags: list = []
# 
# 
# print("\n--- 测试 3: 验证可变默认值的独立性 ---")
# user3 = User()
# user4 = User()
# user3.tags.append("new_tag")
# 
# print(f"user3.tags: {user3.tags}")
# print(f"user4.tags: {user4.tags}")
# =====================单例设计模式=============================
"""
单例模式 (Singleton Pattern) 介绍：
确保一个类在整个程序运行期间“有且仅有一个实例”，并提供一个全局访问点。
在 Python 中，通过【全局变量 + 检查实例化状态】可以最直接地实现单例，
既避免了重复创建对象造成的资源浪费，又保证了全局数据的状态一致性。
"""

from dataclasses import dataclass, field
from typing import Optional
import datetime


@dataclass
class SimpleLogger:
    """日志记录器类"""
    # 简单默认值
    log_level: str = "INFO"

    # 动态默认值：每次实例化时动态获取当前时间
    init_time: str = field(
        default_factory=lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    def log(self, message: str):
        print(f"[{self.init_time}] [{self.log_level}] {message}")


# ==================== 单例核心实现 ====================
# 1. 定义一个私有的全局变量，初始为 None，用来存放唯一的实例
_logger_instance: Optional[SimpleLogger] = None


def get_logger() -> SimpleLogger:
    """
    获取日志记录器的单例对象。
    与 config.py 中的 get_config() 逻辑完全一致。
    """
    global _logger_instance

    # 2. 只有在第一次调用时，才会真正创建对象（懒加载）
    if _logger_instance is None:
        _logger_instance = SimpleLogger()

    # 3. 后续调用直接返回已经创建好的唯一对象
    return _logger_instance


# ==================== 验证测试 ====================
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