"""全局日志管理器"""
import sys
from pathlib import Path
from loguru import logger


def setup_logger(log_level: str = "INFO") -> None:
    """配置全局日志"""
    logger.remove()

    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    # 控制台输出
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
               "<level>{level: <8}</level> | "
               "<cyan>{name}</cyan>:<cyan>{line}</cyan> - "
               "<level>{message}</level>",
        level=log_level,
        colorize=True,
    )

    # 文件输出
    logger.add(
        log_dir / "taobao_publisher_{time:YYYY-MM-DD}.log",
        rotation="1 day",
        retention="7 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}",
        level="DEBUG",
    )


# GUI 日志回调列表
_gui_log_callbacks: list = []


def add_gui_log_callback(callback) -> None:
    """注册 GUI 日志回调"""
    _gui_log_callbacks.append(callback)
    logger.add(
        callback,
        format="{time:HH:mm:ss} [{level}] {message}",
        level="INFO",
    )


setup_logger()