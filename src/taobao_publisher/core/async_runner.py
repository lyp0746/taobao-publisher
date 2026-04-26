"""全局单一异步事件循环管理器 - 解决多线程/多loop冲突问题"""
import asyncio
import threading
from concurrent.futures import Future
from typing import Coroutine, Any
from loguru import logger


class AsyncRunner:
    """
    在独立后台线程中运行单一永久事件循环。
    所有 Playwright 操作必须通过此 Runner 提交，
    确保所有 async 对象共享同一个 loop。
    """
    _instance: "AsyncRunner | None" = None
    _lock = threading.Lock()

    def __new__(cls) -> "AsyncRunner":
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._started = False
        return cls._instance

    def start(self) -> None:
        """启动后台事件循环线程（幂等）"""
        if self._started:
            return

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="AsyncRunnerThread",
            daemon=True,
        )
        self._thread.start()
        self._started = True
        logger.debug("AsyncRunner 后台事件循环已启动")

    def _run_loop(self) -> None:
        """后台线程：永久运行事件循环"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def submit(self, coro: Coroutine) -> Future:
        """
        向后台 loop 提交协程，返回 concurrent.futures.Future。
        可在任意线程中调用，通过 future.result() 阻塞等待结果。
        """
        if not self._started:
            self.start()
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def run(self, coro: Coroutine, timeout: float | None = None) -> Any:
        """
        提交协程并阻塞等待结果（带超时）。
        适合在工作线程中同步调用异步方法。
        """
        future = self.submit(coro)
        return future.result(timeout=timeout)

    def stop(self) -> None:
        """停止事件循环并清理资源"""
        if not self._started:
            return

        try:
            # 先停止事件循环（不阻塞）
            if self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)

            # 等待线程结束（缩短超时时间）
            self._thread.join(timeout=2)

            # 清理循环引用
            self._loop = None
            self._started = False
            logger.debug("AsyncRunner 已停止并清理资源")
        except Exception as e:
            logger.warning(f"停止 AsyncRunner 时出错: {e}")
            self._loop = None
            self._started = False

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if not self._started:
            self.start()
        return self._loop


# 全局单例
async_runner = AsyncRunner()