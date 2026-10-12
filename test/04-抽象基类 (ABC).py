from abc import ABC, abstractmethod

class BaseWorker(ABC):

    def __call__(self, text: str):
        print("--- [日志] 开始干活啦 ---")  # 统一的公共逻辑

        result = self.do_work(text)  # 调用具体的工作（由子类决定）

        print("--- [日志] 干完收工啦 ---")  # 统一的公共逻辑
        return result

    def do_work(self, text: str):
        pass

class UpperWorker(BaseWorker):
    def do_work(self, text: str):
        return text.upper()

class ReverseWorker(BaseWorker):
    def do_work(self, text: str):
        return text[::-1]

if __name__ == "__main__":
    # 让大写员工干活
    worker_a = UpperWorker()
    print("结果:", worker_a("hello"))# 等价 worker_a.__call__("hello")

    print("\n" + "=" * 30 + "\n")

    # 让倒序员工干活
    worker_b = ReverseWorker()
    print("结果:", worker_b("hello"))