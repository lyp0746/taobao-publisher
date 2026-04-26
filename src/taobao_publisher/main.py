"""程序入口"""
import sys
import asyncio
from pathlib import Path


def _fix_windows_asyncio():
    """
    Windows 上 Python 3.8+ 默认使用 ProactorEventLoop，
    但 Playwright 在某些情况下与之有冲突。
    使用 WindowsSelectorEventLoopPolicy 可避免管道警告。
    注意：仅在不需要 subprocess 的场景适用。
    这里我们保持 Proactor（Playwright 需要它），
    但通过 async_runner 统一管理来避免多 loop 问题。
    """
    if sys.platform == "win32":
        # 保持 ProactorEventLoop（Playwright 在 Windows 需要它）
        # 关键是不要创建多个 loop
        pass


def check_dependencies():
    missing = []
    required = [
        ("playwright", "playwright"),
        ("pandas", "pandas"),
        ("httpx", "httpx"),
        ("loguru", "loguru"),
        ("chardet", "chardet"),
        ("dotenv", "python-dotenv"),
    ]
    for module, display in required:
        try:
            __import__(module)
        except ImportError:
            missing.append(display)

    if missing:
        print("缺少以下依赖，请运行: uv sync")
        for m in missing:
            print(f"  - {m}")
        return False
    return True


def check_playwright_browsers():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser_path = p.chromium.executable_path
            return Path(browser_path).exists()
    except Exception:
        return False


def main():
    _fix_windows_asyncio()

    print("=" * 50)
    print("  淘宝商品 AI 智能发布软件  v1.0.0")
    print("=" * 50)

    if not check_dependencies():
        sys.exit(1)

    if not check_playwright_browsers():
        print("\n⚠️  Playwright 浏览器未安装，正在安装 Chromium...")
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=False,
        )
        if result.returncode != 0:
            print("❌ 安装失败，请手动运行: uv run playwright install chromium")
            sys.exit(1)
        print("✅ Chromium 安装成功！")

    print("✅ 环境检查通过，启动界面...")

    # 启动全局 async_runner（在主线程之前启动确保 loop 就绪）
    from taobao_publisher.core.async_runner import async_runner
    async_runner.start()

    from taobao_publisher.ui.main_window import MainWindow
    app = MainWindow()
    app.run()

    # 程序退出时停止 loop
    async_runner.stop()


if __name__ == "__main__":
    main()