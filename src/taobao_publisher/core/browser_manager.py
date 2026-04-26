"""Playwright 浏览器管理器 - 使用全局单一事件循环"""
from typing import Optional
from playwright.async_api import (
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    Playwright,
)
from loguru import logger

from taobao_publisher.utils.config import config
from taobao_publisher.core.async_runner import async_runner


class BrowserManager:
    """浏览器生命周期管理（所有操作在同一个 loop 中执行）"""

    def __init__(self):
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

    async def _do_launch(self) -> Page:
        """实际启动逻辑（在 async_runner 的 loop 中执行）"""
        logger.info("启动浏览器...")

        self._playwright = await async_playwright().start()

        headless = config.get("browser", "headless", default=False)
        slow_mo = config.get("browser", "slow_mo", default=80)

        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            slow_mo=slow_mo,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security",
                "--disable-features=VizDisplayCompositor",
                "--start-maximized",
            ],
        )

        self._context = await self._browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )

        # 注入反检测脚本
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
            window.chrome = {runtime: {}};
        """)

        self._page = await self._context.new_page()
        self._page.set_default_timeout(config.get("browser", "timeout", default=30000))

        logger.success("浏览器启动成功")
        return self._page

    def launch(self) -> Page:
        """启动浏览器（同步包装，在工作线程中调用）"""
        return async_runner.run(self._do_launch(), timeout=60)

    async def _do_navigate_to_taobao(self) -> None:
        """跳转到淘宝登录页（协程）"""
        if not self._page:
            raise RuntimeError("浏览器未启动，请先调用 launch()")
        logger.info("跳转到淘宝卖家后台...")
        await self._page.goto(
            "https://login.taobao.com/member/login.jhtml",
            wait_until="domcontentloaded",
            timeout=30000,
        )

    def navigate_to_taobao(self) -> None:
        """跳转到淘宝登录页（同步包装）"""
        async_runner.run(self._do_navigate_to_taobao(), timeout=35)

    async def _do_wait_for_login(self, timeout_ms: int = 120000) -> bool:
        """等待用户登录（协程）"""
        if not self._page:
            return False
        logger.info("等待用户登录...")
        try:
            await self._page.wait_for_url(
                lambda url: "login" not in url and "taobao.com" in url,
                timeout=timeout_ms,
            )
            logger.success("登录成功！")
            return True
        except Exception:
            logger.warning("登录超时或失败")
            return False

    def wait_for_login(self, timeout_ms: int = 120000) -> bool:
        """等待登录（同步包装）"""
        # 超时秒数要比 timeout_ms 多一点，留给协程处理时间
        return async_runner.run(
            self._do_wait_for_login(timeout_ms),
            timeout=timeout_ms / 1000 + 10,
        )

    async def _do_close(self) -> None:
        """关闭浏览器（协程）并清理所有资源"""
        try:
            if self._page and not self._page.is_closed():
                # 先关闭页面
                await self._page.close()
                logger.debug("Page 已关闭")
        except Exception as ex:
            logger.warning(f"关闭 Page 时出错: {ex}")
        finally:
            self._page = None

        try:
            if self._context:
                # 清理 cookies 和 storage
                await self._context.clear_cookies()
                await self._context.close()
                logger.debug("Context 已关闭")
        except Exception as ex:
            logger.warning(f"关闭 Context 时出错: {ex}")
        finally:
            self._context = None

        try:
            if self._browser and self._browser.is_connected():
                # 关闭浏览器
                await self._browser.close()
                logger.debug("Browser 已关闭")
        except Exception as ex:
            logger.warning(f"关闭 Browser 时出错: {ex}")
        finally:
            self._browser = None

        try:
            if self._playwright:
                # 停止 Playwright
                await self._playwright.stop()
                logger.debug("Playwright 已停止")
        except Exception as ex:
            logger.warning(f"停止 Playwright 时出错: {ex}")
        finally:
            self._playwright = None

        logger.info("浏览器资源已全部清理")

    def close(self) -> None:
        """关闭浏览器（同步包装）"""
        try:
            # 使用submit而非run，避免阻塞
            future = async_runner.submit(self._do_close())
            # 等待最多3秒
            try:
                future.result(timeout=3)
            except Exception as e:
                logger.warning(f"等待浏览器关闭超时: {e}")
        except Exception as e:
            logger.warning(f"关闭浏览器时出错: {e}")

    async def _do_is_logged_in(self) -> bool:
        """检测登录状态（协程）"""
        if not self._page or self._page.is_closed():
            return False
        try:
            url = self._page.url
            cookies = await self._context.cookies()
            return "sellercenter" in url or any(
                c["name"] in ("_tb_token_", "cookie2", "t") for c in cookies
            )
        except Exception:
            return False

    def is_logged_in(self) -> bool:
        """检测登录状态（同步包装）"""
        return async_runner.run(self._do_is_logged_in(), timeout=5)

    @property
    def page(self) -> Optional[Page]:
        return self._page

    @property
    def is_alive(self) -> bool:
        return (
            self._browser is not None
            and self._browser.is_connected()
            and self._page is not None
            and not self._page.is_closed()
        )