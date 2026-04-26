"""
淘宝商品发布自动化 - 适配 v2 发布页
URL: https://item.upload.taobao.com/sell/v2/publish.htm
页面结构:
  Tab1 图文描述: 1:1主图 / 3:4主图 / 宝贝详情
  Tab2 基础信息: 标题 / 类目 / 属性
  Tab3 销售信息: 价格 / 库存 / 规格SKU
  Tab4 物流服务: 运费模板
"""
import asyncio
import hashlib
import random
import re
import tempfile
from pathlib import Path
from typing import Callable, Optional

import httpx
from playwright.async_api import Page, Locator, Frame
from loguru import logger

from taobao_publisher.core.csv_parser import ProductItem, ProductSpec, SkuItem
from taobao_publisher.utils.config import config


class TaobaoPublisher:

    # ── 真实 v2 发布页 URL ───────────────────────────────
    PUBLISH_URL = "https://item.upload.taobao.com/sell/v2/publish.htm"

    # ── Tab 文字（用于点击切换）───────────────────────────
    TAB_IMAGE_DESC = "图文描述"
    TAB_BASE_INFO  = "基础信息"
    TAB_SALE_INFO  = "销售信息"
    TAB_LOGISTICS  = "物流服务"

    def __init__(self, page: Page):
        self._page = page
        self._delay_min: int = config.get("publish", "delay_min", default=600)
        self._delay_max: int = config.get("publish", "delay_max", default=1800)
        # 临时图片目录
        self._tmp_dir = Path(tempfile.gettempdir()) / "tbpub_imgs"
        self._tmp_dir.mkdir(exist_ok=True)

    # ══════════════════════════════════════════════════════
    #  基础工具
    # ══════════════════════════════════════════════════════

    async def _delay(self, lo: int = 0, hi: int = 0):
        lo = lo or self._delay_min
        hi = hi or self._delay_max
        await asyncio.sleep(random.randint(lo, hi) / 1000)

    async def _human_type(self, loc: Locator, text: str, clear: bool = True):
        """模拟人工输入（三击选中→删除→逐字符输入）"""
        await loc.scroll_into_view_if_needed()
        await loc.wait_for(state="visible", timeout=10000)
        if clear:
            await loc.click()
            await asyncio.sleep(0.1)
            await self._page.keyboard.press("Control+a")
            await self._page.keyboard.press("Delete")
            await asyncio.sleep(0.1)
        # 分段输入，每段 50 字符，避免页面卡顿
        for i in range(0, len(text), 50):
            chunk = text[i:i + 50]
            await self._page.keyboard.type(chunk, delay=random.randint(15, 40))
        await self._delay(150, 300)

    async def _first_visible(
        self,
        selectors: list[str],
        timeout: int = 6000,
    ) -> Optional[Locator]:
        """依次尝试 selectors，返回第一个可见的 Locator"""
        for sel in selectors:
            try:
                loc = self._page.locator(sel).first
                await loc.wait_for(state="visible", timeout=timeout)
                return loc
            except Exception:
                continue
        return None

    async def _click_first(
        self,
        selectors: list[str],
        timeout: int = 6000,
    ) -> bool:
        loc = await self._first_visible(selectors, timeout)
        if loc:
            await loc.scroll_into_view_if_needed()
            await self._delay(200, 400)
            await loc.click()
            await self._delay(300, 600)
            return True
        return False

    async def _page_dump(self, label: str = ""):
        """
        调试：把页面所有可见 input/button/textarea/[contenteditable]
        的关键属性打印到 debug 日志。
        可在 config publish.debug_selector=false 关闭。
        """
        if not config.get("publish", "debug_selector", default=True):
            return
        try:
            els = await self._page.evaluate("""() => {
                return Array.from(
                    document.querySelectorAll(
                        'input,button,textarea,[contenteditable="true"]'
                    )
                ).slice(0, 100).map(e => ({
                    tag:   e.tagName,
                    type:  e.type || '',
                    id:    e.id   || '',
                    name:  e.name || '',
                    ph:    e.placeholder || '',
                    cls:   (e.className + '').slice(0, 80),
                    text:  (e.innerText || e.value || '').slice(0, 40),
                    vis:   e.offsetParent !== null,
                }));
            }""")
            visible = [e for e in els if e["vis"]]
            logger.debug(f"[dump:{label}] 可见元素 {len(visible)} 个:")
            for e in visible:
                logger.debug(
                    f"  <{e['tag']} type={e['type']} id={e['id']} "
                    f"name={e['name']} ph='{e['ph']}' "
                    f"cls='{e['cls'][:50]}'> '{e['text']}'"
                )
        except Exception as ex:
            logger.debug(f"dump 失败: {ex}")

    # ══════════════════════════════════════════════════════
    #  Tab 切换
    # ══════════════════════════════════════════════════════

    async def _switch_tab(self, tab_text: str) -> bool:
        """
        点击顶部 Tab（图文描述/基础信息/销售信息/物流服务）
        """
        selectors = [
            f".next-tabs-tab:has-text('{tab_text}')",
            f".tab-nav-item:has-text('{tab_text}')",
            f"[role='tab']:has-text('{tab_text}')",
            f"li:has-text('{tab_text}')",
            f"div.tab:has-text('{tab_text}')",
            f"span:has-text('{tab_text}')",
            f"a:has-text('{tab_text}')",
        ]
        ok = await self._click_first(selectors, timeout=8000)
        if ok:
            await self._delay(800, 1400)
            logger.info(f"切换 Tab: {tab_text}")
        else:
            logger.warning(f"未找到 Tab [{tab_text}]，dump 页面...")
            await self._page_dump(f"switch_tab:{tab_text}")
        return ok

    # ══════════════════════════════════════════════════════
    #  导航
    # ══════════════════════════════════════════════════════

    async def navigate_to_publish(self, category_id: str = "") -> bool:
        url = self.PUBLISH_URL
        if category_id:
            url = f"{url}?cat={category_id}"
        try:
            logger.info(f"跳转发布页: {url}")
            await self._page.goto(url, wait_until="domcontentloaded", timeout=40000)
            await self._page.wait_for_load_state("networkidle", timeout=20000)
            await self._delay(1500, 2500)
            if "login" in self._page.url or "passport" in self._page.url:
                logger.warning("需要登录")
                return False
            logger.success("已到达发布页")
            await self._page_dump("navigate_done")
            return True
        except Exception as e:
            logger.error(f"跳转失败: {e}")
            return False

    # ══════════════════════════════════════════════════════
    #  Tab1: 图文描述 — 主图上传
    # ══════════════════════════════════════════════════════

    async def upload_main_images(
        self,
        images: list[str],
        cb: Optional[Callable[[str], None]] = None,
    ) -> int:
        """
        上传 1:1 主图（最多5张）。
        页面结构（从截图）：
          .mainpic-upload 或 [class*="mainPic"] 区域
          每个「上传图片」占位 = 隐藏的 input[type=file]
        """
        if not images:
            return 0

        local_images = await self._resolve_images(images[:5])
        if not local_images:
            return 0

        # 等待主图区域出现
        await self._switch_tab(self.TAB_IMAGE_DESC)
        await self._delay(600, 1000)

        # 真实页面中「上传图片」占位是 label 或 div，
        # 点击后弹出 file input 或触发隐藏 input
        upload_zone_selectors = [
            # v2 页面真实选择器（通过 dump 确认）
            ".mainpic-zone input[type='file']",
            ".main-pic input[type='file']",
            "[class*='mainPic'] input[type='file']",
            "[class*='main-pic'] input[type='file']",
            # 1:1 主图区域
            ".pic-11 input[type='file']",
            "[class*='pic11'] input[type='file']",
            # 通用兜底
            ".upload-list input[type='file']",
            "input[type='file'][accept*='image']",
        ]

        success = 0
        for idx, img_path in enumerate(local_images):
            if not Path(img_path).exists():
                logger.warning(f"图片不存在: {img_path}")
                continue
            try:
                # 找所有 file input，按索引对应槽位
                for sel in upload_zone_selectors:
                    locs = self._page.locator(sel)
                    cnt = await locs.count()
                    if cnt > 0:
                        # 若已有多个槽位则按索引选；否则用第一个
                        target = locs.nth(idx) if idx < cnt else locs.first
                        await target.set_input_files(img_path)
                        await self._delay(2500, 4000)  # 等待上传
                        success += 1
                        if cb:
                            cb(f"主图 {success}/{len(local_images)}: "
                               f"{Path(img_path).name}")
                        break
                else:
                    logger.warning(f"未找到主图上传框，dump...")
                    await self._page_dump("upload_main_images 失败")
            except Exception as e:
                logger.warning(f"主图上传失败 [{Path(img_path).name}]: {e}")

        logger.info(f"主图上传完成: {success}/{len(local_images)}")
        return success

    # ══════════════════════════════════════════════════════
    #  Tab1: 图文描述 — 宝贝详情（图片+文字）
    # ══════════════════════════════════════════════════════

    async def fill_detail_content(
        self,
        description: str,
        detail_images: list[str],
        cb: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        填写「宝贝详情」区域。
        页面结构（从截图）：
          拖动模块区域，有「添加→图片/文字」按钮
        策略：
          1. 先添加图片模块上传详情图
          2. 再添加文字模块输入描述
        """
        await self._switch_tab(self.TAB_IMAGE_DESC)
        await self._delay(500, 800)

        ok_img  = True
        ok_text = True

        # ── 上传详情图 ────────────────────────────────────
        if detail_images:
            local_imgs = await self._resolve_images(detail_images[:10])
            ok_img = await self._upload_detail_images(local_imgs, cb)

        # ── 填写文字描述 ──────────────────────────────────
        if description:
            ok_text = await self._add_text_block(description, cb)

        return ok_img and ok_text

    async def _upload_detail_images(
        self,
        local_imgs: list[str],
        cb: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        点击「添加→图片」按钮，上传详情图
        """
        success = 0
        for idx, img_path in enumerate(local_imgs):
            if not Path(img_path).exists():
                continue
            try:
                # Step1: 点击「添加」按钮展开菜单
                add_ok = await self._click_first([
                    "button:has-text('添加')",
                    ".add-module-btn",
                    "[class*='addModule']",
                    ".description-add button",
                    # 截图中「添加」按钮结构
                    ".editor-toolbar .add-btn",
                    "[data-type='add']",
                ], timeout=6000)

                if not add_ok:
                    logger.warning("未找到「添加」按钮")
                    await self._page_dump("_upload_detail_images 添加按钮")
                    break

                await self._delay(300, 500)

                # Step2: 点击弹出菜单中的「图片」
                img_menu_ok = await self._click_first([
                    "button:has-text('图片')",
                    "li:has-text('图片')",
                    "[class*='addImage']",
                    ".add-image-item",
                    "span:has-text('图片')",
                ], timeout=4000)

                if not img_menu_ok:
                    logger.warning("未找到「图片」菜单项")
                    continue

                await self._delay(400, 700)

                # Step3: 触发 file input 上传
                file_inp = await self._first_visible([
                    ".detail-img-upload input[type='file']",
                    ".module-image input[type='file']",
                    "[class*='detailImg'] input[type='file']",
                    "[class*='detail-img'] input[type='file']",
                    # 新弹出的 input（最后一个）
                    "input[type='file']:last-of-type",
                    "input[type='file']",
                ], timeout=5000)

                if file_inp:
                    await file_inp.set_input_files(img_path)
                    await self._delay(2500, 4000)
                    success += 1
                    if cb:
                        cb(f"详情图 {success}/{len(local_imgs)}: "
                           f"{Path(img_path).name}")
                else:
                    logger.warning(f"未找到详情图 input，跳过 {idx+1}")

            except Exception as e:
                logger.warning(f"详情图上传失败 [{idx+1}]: {e}")

        logger.info(f"详情图上传完成: {success}/{len(local_imgs)}")
        return success > 0 or not local_imgs

    async def _add_text_block(
        self,
        description: str,
        cb: Optional[Callable[[str], None]] = None,
    ) -> bool:
        """
        点击「添加→文字」按钮，在编辑框中输入描述
        """
        try:
            # Step1: 点击「添加」
            await self._click_first([
                "button:has-text('添加')",
                ".add-module-btn",
                "[class*='addModule']",
            ])
            await self._delay(300, 500)

            # Step2: 点击「文字」
            text_ok = await self._click_first([
                "button:has-text('文字')",
                "li:has-text('文字')",
                "[class*='addText']",
                ".add-text-item",
                "span:has-text('文字')",
            ], timeout=4000)

            if not text_ok:
                logger.warning("未找到「文字」菜单项，尝试直接找编辑框")

            await self._delay(400, 700)

            # Step3: 在新出现的文字编辑框中输入
            editor_selectors = [
                # 宝贝详情文字编辑区
                ".text-module [contenteditable='true']",
                ".module-text [contenteditable='true']",
                "[class*='textModule'] [contenteditable='true']",
                # 通用富文本
                ".ql-editor",
                ".ProseMirror",
                "[contenteditable='true']",
                # textarea 降级
                "textarea[placeholder*='描述']",
                "textarea[placeholder*='文字']",
            ]

            editor = await self._first_visible(editor_selectors, timeout=6000)
            if editor:
                await editor.click()
                await self._delay(200, 300)
                # 分段输入长文本
                for i in range(0, len(description), 100):
                    await self._page.keyboard.type(
                        description[i:i+100], delay=8
                    )
                    await self._delay(50, 100)
                if cb:
                    cb(f"描述填写完成（{len(description)} 字）")
                logger.info("宝贝详情文字填写完成")
                return True
            else:
                logger.warning("未找到文字编辑框")
                await self._page_dump("_add_text_block 失败")
                return False

        except Exception as e:
            logger.warning(f"添加文字模块失败: {e}")
            return False

    # ══════════════════════════════════════════════════════
    #  Tab2: 基础信息 — 标题 / 属性
    # ══════════════════════════════════════════════════════

    async def fill_title(self, title: str) -> bool:
        logger.info(f"填写标题: {title[:25]}...")
        await self._switch_tab(self.TAB_BASE_INFO)

        selectors = [
            # v2 页面真实 Selector（根据 dump 扩充）
            "input[name='title']",
            "input[id*='itle']",
            "input[placeholder='请输入商品标题']",
            "input[placeholder*='标题']",
            "input[maxlength='60']",
            "input[maxlength='30']",
            # 基础信息 Tab 内
            ".base-info input[type='text']:first-of-type",
            ".item-title input",
            ".title-input input",
        ]

        loc = await self._first_visible(selectors)
        if loc:
            await self._human_type(loc, title)
            logger.success("标题填写完成")
            return True

        logger.warning("❌ 未找到标题输入框")
        await self._page_dump("fill_title 失败")
        return False

    async def fill_attributes(self, attributes: dict[str, str]) -> bool:
        """填写基础信息 Tab 中的商品属性"""
        if not attributes:
            return True

        await self._switch_tab(self.TAB_BASE_INFO)
        await self._delay(500, 800)

        success = 0
        for attr_name, attr_value in attributes.items():
            ok = await self._fill_single_attr(attr_name, attr_value)
            if ok:
                success += 1
            await self._delay(100, 200)

        logger.info(f"属性填写: {success}/{len(attributes)}")
        return True

    async def _fill_single_attr(self, name: str, value: str) -> bool:
        """
        用 JavaScript 遍历属性标签，匹配后填入值。
        支持：select 下拉 / input 文本框 / 点击标签（单选组）
        """
        try:
            result = await self._page.evaluate("""
                ([name, value]) => {
                    // 找所有属性行容器
                    const rows = document.querySelectorAll(
                        '.item-prop, .prop-row, .attr-row, ' +
                        '[class*="propRow"], [class*="prop-row"], ' +
                        '[class*="itemProp"], .form-item'
                    );
                    for (const row of rows) {
                        const labelEl = row.querySelector(
                            'label, .prop-label, .attr-label, ' +
                            '[class*="propName"], [class*="prop-name"]'
                        );
                        if (!labelEl) continue;
                        if (!labelEl.textContent.includes(name)) continue;

                        // select 下拉
                        const sel = row.querySelector('select');
                        if (sel) {
                            const opt = Array.from(sel.options).find(
                                o => o.text.includes(value) || o.value === value
                            );
                            if (opt) {
                                sel.value = opt.value;
                                sel.dispatchEvent(
                                    new Event('change', {bubbles: true})
                                );
                                return 'select:' + opt.text;
                            }
                        }

                        // input 文本框
                        const inp = row.querySelector(
                            'input[type="text"], input:not([type])'
                        );
                        if (inp) {
                            inp.value = value;
                            inp.dispatchEvent(
                                new Event('input',  {bubbles: true})
                            );
                            inp.dispatchEvent(
                                new Event('change', {bubbles: true})
                            );
                            return 'input:' + value;
                        }

                        // 单选标签点击（如颜色分类标签组）
                        const btns = row.querySelectorAll(
                            '.prop-value, .attr-value, ' +
                            '[class*="propValue"], label, span'
                        );
                        for (const btn of btns) {
                            if (btn.textContent.trim() === value) {
                                btn.click();
                                return 'click:' + btn.textContent.trim();
                            }
                        }
                    }
                    return null;
                }
            """, [name, value])

            if result:
                logger.debug(f"属性 [{name}:{value}] → {result}")
                return True
        except Exception as e:
            logger.debug(f"JS 填属性失败 [{name}]: {e}")

        logger.debug(f"属性 [{name}:{value}] 未找到对应控件")
        return False

    # ══════════════════════════════════════════════════════
    #  Tab3: 销售信息 — 价格 / 库存 / SKU 规格
    # ══════════════════════════════════════════════════════

    async def _goto_sale_tab(self):
        await self._switch_tab(self.TAB_SALE_INFO)
        await self._delay(800, 1200)

    async def fill_price(self, price: float) -> bool:
        await self._goto_sale_tab()
        selectors = [
            "input[name='price']",
            "input[id*='Price']",
            "input[placeholder*='一口价']",
            "input[placeholder*='价格']",
            ".price-input input",
            ".sale-price input",
            "[class*='priceInput'] input",
        ]
        loc = await self._first_visible(selectors)
        if loc:
            await self._human_type(loc, f"{price:.2f}")
            logger.info(f"价格填写: ¥{price:.2f}")
            return True
        logger.warning("未找到价格框")
        await self._page_dump("fill_price 失败")
        return False

    async def fill_stock(self, stock: int) -> bool:
        # 库存通常在销售信息 Tab，也可能随 SKU 联动
        selectors = [
            "input[name='quantity']",
            "input[name='stock']",
            "input[placeholder*='库存']",
            "input[placeholder*='数量']",
            ".quantity-input input",
            "[class*='stockInput'] input",
        ]
        loc = await self._first_visible(selectors)
        if loc:
            await self._human_type(loc, str(stock))
            logger.info(f"库存填写: {stock}")
            return True
        logger.warning("未找到库存框")
        return False

    # ── 规格 & SKU ─────────────────────────────────────────

    async def fill_specs_and_sku(
        self,
        specs: list[ProductSpec],
        sku_list: list[SkuItem],
        cb: Optional[Callable[[str], None]] = None,
    ) -> bool:
        if not specs:
            return True

        await self._goto_sale_tab()

        success_dims = 0
        for spec in specs:
            ok = await self._add_spec_dimension(spec, cb)
            if ok:
                success_dims += 1
            await self._delay(700, 1100)

        # 等待 SKU 表格渲染（React 异步）
        if sku_list:
            await self._fill_sku_price_table(sku_list, cb)

        logger.info(f"规格填写: {success_dims}/{len(specs)} 个维度")
        return success_dims > 0

    async def _add_spec_dimension(
        self,
        spec: ProductSpec,
        cb: Optional[Callable[[str], None]] = None,
    ) -> bool:
        try:
            # Step1: 点击「添加销售属性」/ 「添加规格」
            add_ok = await self._click_first([
                "button:has-text('添加销售属性')",
                "a:has-text('添加销售属性')",
                "button:has-text('添加规格')",
                "a:has-text('添加规格')",
                ".add-sku-prop",
                "[class*='addProp']",
                "[class*='add-prop']",
                "[class*='addSku']",
            ], timeout=6000)

            if not add_ok:
                logger.warning(f"未找到添加规格按钮，dump...")
                await self._page_dump("_add_spec_dimension")
                return False

            # Step2: 输入规格名
            name_loc = await self._first_visible([
                "input[placeholder*='规格名']",
                "input[placeholder*='属性名']",
                "input[placeholder*='销售属性']",
                "[class*='propName'] input",
                "[class*='sku-name'] input",
                ".sku-prop-name input",
            ], timeout=5000)

            if name_loc:
                await self._human_type(name_loc, spec.name)
                await self._page.keyboard.press("Enter")
                await self._delay(200, 400)

            # Step3: 输入各规格值
            for val in spec.values:
                # 找到最新出现的「规格值」输入框
                val_loc = await self._first_visible([
                    "input[placeholder*='规格值']",
                    "input[placeholder*='属性值']",
                    "[class*='propValue'] input",
                    "[class*='sku-value'] input",
                    ".sku-prop-value input",
                ], timeout=4000)

                if val_loc:
                    await self._human_type(val_loc, val, clear=False)
                    await self._page.keyboard.press("Enter")
                    await self._delay(200, 350)
                else:
                    # 尝试点击「添加值」再输入
                    await self._click_first([
                        "button:has-text('添加值')",
                        "a:has-text('添加值')",
                        ".add-prop-value",
                    ], timeout=3000)
                    val_loc2 = await self._first_visible([
                        "input[placeholder*='规格值']",
                        ".sku-prop-value input:last-child",
                    ], timeout=3000)
                    if val_loc2:
                        await self._human_type(val_loc2, val)
                        await self._page.keyboard.press("Enter")
                        await self._delay(200, 350)

            if cb:
                cb(f"规格 [{spec.name}] 添加完成 ({len(spec.values)} 个值)")
            return True

        except Exception as e:
            logger.warning(f"添加规格 [{spec.name}] 失败: {e}")
            return False

    async def _fill_sku_price_table(
        self,
        sku_list: list[SkuItem],
        cb: Optional[Callable[[str], None]] = None,
    ):
        """
        规格选完后等待 SKU 价格表格动态渲染，再填写每行的价格和库存
        """
        logger.info("等待 SKU 价格表格...")

        # 等待表格出现（最多 20 秒，React 渲染可能较慢）
        table_selectors = [
            ".sku-list",
            ".sku-table",
            "[class*='skuList']",
            "[class*='sku-list']",
            "[class*='skuTable']",
            "table[class*='sku']",
        ]
        found = False
        for sel in table_selectors:
            try:
                await self._page.locator(sel).first.wait_for(
                    state="visible", timeout=20000
                )
                found = True
                logger.info(f"SKU 表格已出现: {sel}")
                break
            except Exception:
                continue

        if not found:
            logger.warning("⚠️ SKU 价格表格未出现，dump 页面...")
            await self._page_dump("_fill_sku_price_table 未找到")
            return

        await self._delay(800, 1200)

        # 收集价格输入框
        price_inputs = await self._collect_inputs([
            "input[name*='price']",
            "input[placeholder*='价格']",
            "[class*='skuPrice'] input",
            "[class*='sku-price'] input",
            "td input[type='text']:nth-child(1)",
        ])

        # 收集库存输入框
        stock_inputs = await self._collect_inputs([
            "input[name*='quantity']",
            "input[name*='stock']",
            "input[placeholder*='库存']",
            "[class*='skuStock'] input",
            "[class*='sku-stock'] input",
        ])

        logger.info(
            f"SKU 表格: 价格框 {len(price_inputs)} 个, "
            f"库存框 {len(stock_inputs)} 个, "
            f"SKU {len(sku_list)} 条"
        )

        for i, sku in enumerate(sku_list):
            try:
                if i < len(price_inputs) and sku.price > 0:
                    await self._human_type(
                        price_inputs[i], f"{sku.price:.2f}"
                    )
                if i < len(stock_inputs) and sku.stock > 0:
                    await self._human_type(
                        stock_inputs[i], str(sku.stock)
                    )
                if cb and (i % 5 == 0 or i == len(sku_list) - 1):
                    cb(f"SKU {i+1}/{len(sku_list)}: {sku.combo_str[:20]}")
            except Exception as e:
                logger.warning(f"SKU {i+1} 填写失败: {e}")

        logger.info("SKU 价格库存填写完成")

    async def _collect_inputs(self, selectors: list[str]) -> list[Locator]:
        """找到第一个命中的 selector 并返回所有匹配项"""
        for sel in selectors:
            locs = self._page.locator(sel)
            cnt = await locs.count()
            if cnt > 0:
                return [locs.nth(i) for i in range(cnt)]
        return []

    # ══════════════════════════════════════════════════════
    #  Tab4: 物流服务 — 运费模板
    # ══════════════════════════════════════════════════════

    async def select_freight_template(self, template_id: str) -> bool:
        if not template_id:
            return True

        await self._switch_tab(self.TAB_LOGISTICS)
        await self._delay(600, 1000)

        selectors = [
            "select[name='postage']",
            "select[name='freightTemplate']",
            "[class*='freight'] select",
            "[class*='postage'] select",
            "#J_FreightTemplate",
        ]
        for sel in selectors:
            loc = self._page.locator(sel).first
            if await loc.count() > 0:
                try:
                    await loc.select_option(value=template_id)
                    await self._delay(300, 500)
                    logger.info(f"运费模板: {template_id}")
                    return True
                except Exception:
                    continue

        logger.warning(f"未找到运费模板 {template_id}")
        await self._page_dump("select_freight_template 失败")
        return False

    # ══════════════════════════════════════════════════════
    #  视频上传（图文描述 Tab）
    # ══════════════════════════════════════════════════════

    async def upload_videos(
        self,
        videos: list[str],
        cb: Optional[Callable[[str], None]] = None,
    ) -> int:
        if not videos:
            return 0

        await self._switch_tab(self.TAB_IMAGE_DESC)
        await self._delay(400, 700)

        resolved = await self._resolve_images(videos[:3])
        if not resolved:
            logger.warning("视频 URL 下载或文件不存在，跳过")
            return 0

        video_selectors = [
            "input[type='file'][accept*='video']",
            ".video-uploader input[type='file']",
            "[class*='videoUpload'] input[type='file']",
            "[class*='video-upload'] input[type='file']",
        ]
        success = 0
        for vpath in resolved:
            if not Path(vpath).exists():
                continue
            for sel in video_selectors:
                el = self._page.locator(sel).first
                if await el.count() > 0:
                    await el.set_input_files(vpath)
                    await self._delay(6000, 10000)
                    success += 1
                    if cb:
                        cb(f"视频上传 {success}: {Path(vpath).name}")
                    break

        return success

    # ══════════════════════════════════════════════════════
    #  保存草稿 / 提交宝贝信息
    # ══════════════════════════════════════════════════════

    async def save_draft(self) -> bool:
        """
        点击底部「保存草稿」按钮
        截图确认文字：「保存草稿」
        """
        logger.info("保存草稿...")

        # 确保滚动到底部，按钮才可见
        await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await self._delay(400, 700)

        btn = await self._first_visible([
            # 截图底部确认的按钮文字
            "button:has-text('保存草稿')",
            "span:has-text('保存草稿')",
            "a:has-text('保存草稿')",
            # 英文 class
            "[class*='saveDraft']",
            "[class*='save-draft']",
            "#J_SaveDraft",
            # 输入型按钮
            "input[value='保存草稿']",
        ], timeout=10000)

        if not btn:
            logger.warning("❌ 未找到保存草稿按钮，dump...")
            await self._page_dump("save_draft 失败")
            # 最后尝试：用文字定位点击
            try:
                await self._page.get_by_text("保存草稿", exact=True).click()
                await self._delay(3000, 5000)
                logger.info("草稿保存（通过 get_by_text）")
                return True
            except Exception:
                return False

        await btn.scroll_into_view_if_needed()
        await self._delay(300, 500)
        await btn.click()
        await self._delay(3000, 5000)

        # 检测成功提示（截图底部显示「最后保存于…」）
        success_indicators = [
            "text=最后保存于",
            "text=保存成功",
            "[class*='saveTime']",
            "[class*='save-time']",
            ".ant-message-success",
        ]
        for sel in success_indicators:
            try:
                await self._page.locator(sel).first.wait_for(
                    state="visible", timeout=6000
                )
                logger.success("✅ 草稿保存成功")
                return True
            except Exception:
                continue

        logger.info("草稿保存完成（以底部时间戳为准）")
        return True

    async def submit_publish(self) -> bool:
        """
        点击底部「提交宝贝信息」按钮
        截图确认文字：「提交宝贝信息」
        """
        logger.info("提交宝贝信息...")
        await self._page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await self._delay(400, 700)

        btn = await self._first_visible([
            "button:has-text('提交宝贝信息')",
            "span:has-text('提交宝贝信息')",
            "button:has-text('发布商品')",
            "button:has-text('立即发布')",
            "[class*='submitBtn']",
            "[class*='publishBtn']",
            "#J_Submit",
        ], timeout=10000)

        if not btn:
            logger.warning("❌ 未找到提交按钮，dump...")
            await self._page_dump("submit_publish 失败")
            try:
                await self._page.get_by_text("提交宝贝信息", exact=True).click()
                await self._delay(4000, 6000)
                return True
            except Exception:
                return False

        await btn.scroll_into_view_if_needed()
        await self._delay(300, 500)
        await btn.click()
        await self._delay(4000, 6000)

        try:
            await self._page.wait_for_url(
                lambda url: any(
                    k in url for k in ("success", "published", "done", "detail")
                ),
                timeout=15000,
            )
            logger.success("✅ 商品发布成功！")
            return True
        except Exception:
            logger.info("提交完成（未检测到跳转，假定成功）")
            return True

    # ══════════════════════════════════════════════════════
    #  图片下载（URL → 本地临时文件）
    # ══════════════════════════════════════════════════════

    async def _resolve_images(self, images: list[str]) -> list[str]:
        """
        URL → 下载到 tmp 目录（MD5 缓存，避免重复下载）
        本地路径 → 直接返回
        """
        result = []
        for img in images:
            if not img:
                continue
            if img.startswith("http://") or img.startswith("https://"):
                local = await self._download_image(img)
                if local:
                    result.append(local)
            else:
                result.append(img)
        return result

    async def _download_image(self, url: str) -> Optional[str]:
        ext = url.split("?")[0].rsplit(".", 1)[-1].lower()
        if ext not in ("jpg", "jpeg", "png", "webp", "gif", "mp4", "mov"):
            ext = "jpg"
        fname = hashlib.md5(url.encode()).hexdigest()[:16] + f".{ext}"
        local = self._tmp_dir / fname
        if local.exists():
            return str(local)
        try:
            async with httpx.AsyncClient(
                timeout=30, follow_redirects=True
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                local.write_bytes(resp.content)
            logger.debug(f"下载: {url[:50]} → {local.name}")
            return str(local)
        except Exception as e:
            logger.warning(f"下载失败 [{url[:50]}]: {e}")
            return None

    # ══════════════════════════════════════════════════════
    #  完整发布流程（按 4 个 Tab 顺序）
    # ══════════════════════════════════════════════════════

    async def publish_product(
        self,
        product: ProductItem,
        progress_callback: Optional[Callable[[str], None]] = None,
        auto_submit: bool = False,
    ) -> bool:

        def cb(msg: str):
            product.status = "publishing"
            if progress_callback:
                progress_callback(msg)
            logger.info(msg)

        try:
            # ① 导航到发布页（含类目 ID）
            cb("📄 跳转发布页面...")
            ok = await self.navigate_to_publish(product.category_id)
            if not ok:
                product.status = "error"
                product.error_msg = "跳转失败（未登录或网络异常）"
                return False

            # ── Tab1: 图文描述 ──────────────────────────────
            # ② 主图上传
            if product.main_images:
                cb(f"🖼️ 上传主图（{len(product.main_images)} 张）...")
                await self.upload_main_images(product.main_images, cb=cb)

            # ③ 视频上传
            if product.videos:
                cb(f"🎬 上传视频（{len(product.videos)} 个）...")
                await self.upload_videos(product.videos, cb=cb)

            # ④ 宝贝详情（详情图 + 文字描述）
            if product.detail_images or product.display_description:
                cb("📝 填写宝贝详情...")
                await self.fill_detail_content(
                    product.display_description,
                    product.detail_images,
                    cb=cb,
                )

            # ── Tab2: 基础信息 ──────────────────────────────
            # ⑤ 标题
            cb(f"✍️ 填写标题: {product.display_title[:20]}...")
            await self.fill_title(product.display_title)

            # ⑥ 属性
            if product.attributes:
                cb(f"🏷️ 填写属性（{len(product.attributes)} 条）...")
                await self.fill_attributes(product.attributes)

            # ── Tab3: 销售信息 ──────────────────────────────
            specs = product.ai_specs or product.specs
            if specs:
                # ⑦ 规格 + SKU
                cb(f"📋 填写规格（{len(specs)} 个维度）...")
                await self.fill_specs_and_sku(specs, product.sku_list, cb=cb)
            else:
                # ⑧ 单规格：直接填价格库存
                if product.price > 0:
                    cb(f"💰 填写价格: ¥{product.price}")
                    await self.fill_price(product.price)
                if product.stock > 0:
                    cb(f"📦 填写库存: {product.stock}")
                    await self.fill_stock(product.stock)

            # ── Tab4: 物流服务 ──────────────────────────────
            # ⑨ 运费模板
            if product.freight_template_id:
                cb(f"🚚 运费模板: {product.freight_template_id}")
                await self.select_freight_template(product.freight_template_id)

            # ── 底部按钮 ─────────────────────────────────────
            # ⑩ 保存草稿 / 提交宝贝信息
            if auto_submit:
                cb("🚀 提交宝贝信息...")
                success = await self.submit_publish()
            else:
                cb("💾 保存草稿...")
                success = await self.save_draft()

            product.status = "done" if success else "error"
            if not success:
                product.error_msg = "保存/提交操作失败"
            return success

        except Exception as e:
            product.status = "error"
            product.error_msg = str(e)
            logger.error(f"发布异常: {e}", exc_info=True)
            return False