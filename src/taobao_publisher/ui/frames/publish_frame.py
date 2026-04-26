"""发布控制面板 - 使用全局 async_runner"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable

from loguru import logger

from taobao_publisher.core.ai_processor import AIProcessor
from taobao_publisher.core.async_runner import async_runner
from taobao_publisher.core.browser_manager import BrowserManager
from taobao_publisher.core.csv_parser import ProductItem
from taobao_publisher.utils.config import config
from taobao_publisher.ui.styles import COLORS, get_default_font


class PublishFrame(ttk.Frame):
    """发布控制界面"""

    def __init__(self, parent, get_products: Callable, log_callback: Callable,
                 refresh_csv_callback: Callable, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style="TFrame")
        # 获取系统可用字体
        self._default_font = get_default_font()

        self._get_products = get_products
        self._log = log_callback
        self._refresh_csv = refresh_csv_callback

        # 启动全局事件循环
        async_runner.start()

        self._browser_manager: Optional[BrowserManager] = None
        self._ai_processor = AIProcessor()
        self._is_running = False

        self._setup_ui()

    def _setup_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_browser_section()
        self._build_main_section()
        self._build_action_buttons()

    def _build_browser_section(self):
        card = ttk.LabelFrame(self, text="  🌐 浏览器控制  ", style="TLabelframe")
        card.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        card.columnconfigure(3, weight=1)

        ttk.Label(card, text="浏览器状态：", style="Card.TLabel").grid(
            row=0, column=0, padx=(12, 4), pady=12)

        self._browser_status = tk.StringVar(value="⭕ 未启动")
        self._browser_status_label = ttk.Label(
            card, textvariable=self._browser_status,
            style="Card.TLabel", foreground=COLORS["text_muted"]
        )
        self._browser_status_label.grid(row=0, column=1, padx=(0, 16), pady=12)

        ttk.Button(card, text="🚀 启动浏览器", style="Secondary.TButton",
                   command=self._launch_browser).grid(row=0, column=2, padx=4, pady=8)
        ttk.Button(card, text="🔗 打开淘宝登录", style="Ghost.TButton",
                   command=self._open_taobao_login).grid(
            row=0, column=3, padx=4, pady=8, sticky="w")
        ttk.Button(card, text="❌ 关闭浏览器", style="Danger.TButton",
                   command=self._close_browser).grid(
            row=0, column=4, padx=(4, 12), pady=8)

        self._headless_var = tk.BooleanVar(
            value=config.get("browser", "headless", default=False))
        ttk.Checkbutton(card, text="无头模式（后台运行）",
                        variable=self._headless_var,
                        style="Card.TCheckbutton",
                        command=self._on_headless_change).grid(
            row=1, column=0, columnspan=3, padx=12, pady=(0, 8), sticky="w")

    def _build_main_section(self):
        main_frame = ttk.Frame(self, style="TFrame")
        main_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=0)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.rowconfigure(0, weight=1)
        self._build_publish_settings(main_frame)
        self._build_progress_panel(main_frame)

    def _build_publish_settings(self, parent):
        card = ttk.LabelFrame(parent, text="  ⚙️ 发布设置  ", style="TLabelframe")
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=8)

        row = 0
        self._use_ai_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(card, text="🤖 发布前进行 AI 优化",
                        variable=self._use_ai_var,
                        style="Card.TCheckbutton").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=12, pady=8); row += 1

        self._auto_submit_var = tk.BooleanVar(
            value=config.get("publish", "auto_submit", default=False))
        ttk.Checkbutton(card, text="📤 自动提交发布（否则保存草稿）",
                        variable=self._auto_submit_var,
                        style="Card.TCheckbutton").grid(
            row=row, column=0, columnspan=2, sticky="w", padx=12, pady=4); row += 1

        ttk.Label(card, text="商品间隔(秒)：", style="Card.TLabel").grid(
            row=row, column=0, sticky="w", padx=(12, 4), pady=8)
        self._interval_var = tk.IntVar(
            value=config.get("publish", "batch_interval", default=3))
        ttk.Spinbox(card, from_=1, to=60, textvariable=self._interval_var,
                    width=8, font=(self._default_font, 10)).grid(
            row=row, column=1, sticky="w", pady=8); row += 1

        ttk.Label(card, text="操作延迟(毫秒)：", style="Card.TLabel").grid(
            row=row, column=0, sticky="w", padx=(12, 4), pady=8)
        delay_frame = ttk.Frame(card, style="Card.TFrame")
        delay_frame.grid(row=row, column=1, sticky="w", pady=8)
        self._delay_min_var = tk.IntVar(
            value=config.get("publish", "delay_min", default=500))
        self._delay_max_var = tk.IntVar(
            value=config.get("publish", "delay_max", default=1500))
        ttk.Spinbox(delay_frame, from_=100, to=5000,
                    textvariable=self._delay_min_var, width=6).pack(side=tk.LEFT)
        ttk.Label(delay_frame, text=" ~ ", style="Card.TLabel").pack(side=tk.LEFT)
        ttk.Spinbox(delay_frame, from_=100, to=10000,
                    textvariable=self._delay_max_var, width=6).pack(side=tk.LEFT)
        row += 1

        ttk.Separator(card, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=8); row += 1

        # 图片生成选项
        self._generate_images_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(card, text="🎨 生成优化图片（需要AI支持图片生成）",
                        variable=self._generate_images_var,
                        style="Card.TCheckbutton",
                        command=self._on_image_gen_change).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=12, pady=4); row += 1
        
        # 图片输出目录
        self._image_output_frame = ttk.Frame(card, style="Card.TFrame")
        self._image_output_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=4); row += 1
        
        self._image_output_var = tk.StringVar(value="./generated_images")
        ttk.Label(self._image_output_frame, text="图片输出目录：", style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 4))
        ttk.Entry(self._image_output_frame, textvariable=self._image_output_var, width=30).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(self._image_output_frame, text="浏览", 
                  command=self._browse_image_dir, 
                  style="Ghost.TButton").pack(side=tk.LEFT, padx=(4, 0))
        
        # 初始状态隐藏图片输出选项
        self._image_output_frame.grid_remove()
        
        ttk.Separator(card, orient=tk.HORIZONTAL).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=12, pady=8); row += 1

        ttk.Label(card, text="发布范围：", style="Card.TLabel").grid(
            row=row, column=0, sticky="w", padx=(12, 4), pady=8)
        self._range_var = tk.StringVar(value="all")
        range_frame = ttk.Frame(card, style="Card.TFrame")
        range_frame.grid(row=row, column=1, sticky="w")
        for label, value in [("全部", "all"), ("选中项", "selected"), ("未处理", "pending")]:
            ttk.Radiobutton(range_frame, text=label,
                            variable=self._range_var, value=value,
                            style="Card.TCheckbutton").pack(side=tk.LEFT, padx=4)

    def _build_progress_panel(self, parent):
        card = ttk.LabelFrame(parent, text="  📊 发布进度  ", style="TLabelframe")
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=8)
        card.columnconfigure(0, weight=1)

        ttk.Label(card, text="总进度", style="CardTitle.TLabel").grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 4))
        self._total_progress = ttk.Progressbar(card, orient=tk.HORIZONTAL,
                                               mode="determinate")
        self._total_progress.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._total_progress_label = ttk.Label(card, text="0 / 0", style="Card.TLabel",
                                               foreground=COLORS["text_muted"])
        self._total_progress_label.grid(row=2, column=0, sticky="e", padx=12)

        ttk.Label(card, text="AI 处理", style="CardTitle.TLabel").grid(
            row=3, column=0, sticky="w", padx=12, pady=(12, 4))
        self._ai_progress = ttk.Progressbar(card, orient=tk.HORIZONTAL,
                                            mode="determinate")
        self._ai_progress.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 4))
        self._ai_progress_label = ttk.Label(card, text="0 / 0", style="Card.TLabel",
                                            foreground=COLORS["text_muted"])
        self._ai_progress_label.grid(row=5, column=0, sticky="e", padx=12)

        ttk.Label(card, text="当前操作", style="CardTitle.TLabel").grid(
            row=6, column=0, sticky="w", padx=12, pady=(12, 4))
        self._current_op_var = tk.StringVar(value="等待开始...")
        ttk.Label(card, textvariable=self._current_op_var,
                  style="Card.TLabel",
                  foreground=COLORS["warning"],
                  wraplength=280).grid(row=7, column=0, sticky="w", padx=12, pady=(0, 8))

        ttk.Separator(card, orient=tk.HORIZONTAL).grid(
            row=8, column=0, sticky="ew", padx=12, pady=8)

        stats_frame = ttk.Frame(card, style="Card.TFrame")
        stats_frame.grid(row=9, column=0, sticky="ew", padx=12, pady=(0, 12))
        stats_frame.columnconfigure((0, 1, 2), weight=1)

        self._stat_success_var = tk.StringVar(value="0")
        self._stat_error_var = tk.StringVar(value="0")
        self._stat_skip_var = tk.StringVar(value="0")

        for col, (label, var, color) in enumerate([
            ("✅ 成功", self._stat_success_var, COLORS["success"]),
            ("❌ 失败", self._stat_error_var, COLORS["error"]),
            ("⏭️ 跳过", self._stat_skip_var, COLORS["text_muted"]),
        ]):
            f = ttk.Frame(stats_frame, style="Card.TFrame")
            f.grid(row=0, column=col, padx=4)
            ttk.Label(f, textvariable=var, style="Card.TLabel",
                      font=(self._default_font, 18, "bold"), foreground=color).pack()
            ttk.Label(f, text=label, style="Card.TLabel").pack()

    def _build_action_buttons(self):
        bar = ttk.Frame(self, style="Card.TFrame")
        bar.grid(row=2, column=0, sticky="ew")

        btn_frame = ttk.Frame(bar, style="Card.TFrame")
        btn_frame.pack(padx=16, pady=12, anchor=tk.W)

        self._btn_ai_only = ttk.Button(
            btn_frame, text="🤖 仅 AI 处理",
            style="Secondary.TButton",
            command=self._start_ai_only,
        )
        self._btn_ai_only.pack(side=tk.LEFT, padx=(0, 8))

        self._btn_save_results = ttk.Button(
            btn_frame, text="💾 保存AI结果",
            style="Secondary.TButton",
            command=self._save_ai_results,
        )
        self._btn_save_results.pack(side=tk.LEFT, padx=(0, 8))

        self._btn_publish = ttk.Button(
            btn_frame, text="🚀 开始发布",
            style="Success.TButton",
            command=self._start_publish,
        )
        self._btn_publish.pack(side=tk.LEFT, padx=(0, 8))

        self._btn_stop = ttk.Button(
            btn_frame, text="⏹️ 停止",
            style="Danger.TButton",
            command=self._stop_task,
            state=tk.DISABLED,
        )
        self._btn_stop.pack(side=tk.LEFT, padx=(0, 16))

        self._task_status_var = tk.StringVar(value="就绪")
        ttk.Label(bar, textvariable=self._task_status_var,
                  style="Card.TLabel",
                  foreground=COLORS["text_muted"]).pack(side=tk.LEFT, padx=8)

    # ── 事件处理 ──────────────────────────────────────────────

    def _on_headless_change(self):
        config.set("browser", "headless", self._headless_var.get())
        config.save()
    
    def _on_image_gen_change(self):
        """图片生成选项变化时的处理"""
        if self._generate_images_var.get():
            self._image_output_frame.grid()
        else:
            self._image_output_frame.grid_remove()
    
    def _browse_image_dir(self):
        """浏览选择图片输出目录"""
        from tkinter import filedialog
        directory = filedialog.askdirectory(
            title="选择图片输出目录",
            initialdir=self._image_output_var.get()
        )
        if directory:
            self._image_output_var.set(directory)

    def _set_browser_status(self, text: str, color: str):
        """线程安全地更新浏览器状态标签"""
        def _update():
            self._browser_status.set(text)
            self._browser_status_label.configure(foreground=color)
        self.after(0, _update)

    def _launch_browser(self):
        """启动浏览器（在工作线程中调用同步包装）"""
        if self._browser_manager and self._browser_manager.is_alive:
            messagebox.showinfo("提示", "浏览器已在运行中")
            return

        self._set_browser_status("⏳ 启动中...", COLORS["warning"])
        self._log("启动 Playwright 浏览器...")

        def _run():
            try:
                self._browser_manager = BrowserManager()
                self._browser_manager.launch()  # 同步包装，内部用 async_runner
                self._set_browser_status("🟢 已启动", COLORS["success"])
                self.after(0, lambda: self._log("✅ 浏览器启动成功"))
            except Exception as ex:
                err_msg = str(ex)
                self._set_browser_status("❌ 启动失败", COLORS["error"])
                self.after(0, lambda: self._log(f"❌ 浏览器启动失败: {err_msg}"))
                self._browser_manager = None

        threading.Thread(target=_run, name="BrowserLaunch", daemon=True).start()

    def _open_taobao_login(self):
        """打开淘宝登录页并等待登录"""
        if not self._browser_manager or not self._browser_manager.is_alive:
            messagebox.showwarning("提示", "请先启动浏览器")
            return

        self._log("正在跳转到淘宝登录页...")

        def _run():
            try:
                # 使用同步包装（内部走 async_runner）
                self._browser_manager.navigate_to_taobao()
                self.after(0, lambda: self._log("已到达淘宝登录页，请扫码或输入账号登录..."))

                # 等待登录（最多 3 分钟）
                success = self._browser_manager.wait_for_login(timeout_ms=180000)
                if success:
                    self._set_browser_status("🟢 已登录", COLORS["success"])
                    self.after(0, lambda: self._log("✅ 淘宝登录成功！"))
                else:
                    self.after(0, lambda: self._log("⚠️ 登录超时，请重试"))
            except Exception as ex:
                err_msg = str(ex)
                self.after(0, lambda: self._log(f"❌ 打开登录页失败: {err_msg}"))

        threading.Thread(target=_run, name="TaobaoLogin", daemon=True).start()

    def _close_browser(self):
        """关闭浏览器"""
        if not self._browser_manager:
            return

        # 立即更新UI状态，不等待浏览器关闭完成
        self._set_browser_status("⏳ 关闭中...", COLORS["warning"])
        self._log("正在关闭浏览器...")

        def _run():
            try:
                self._browser_manager.close()
                self._browser_manager = None
                self._set_browser_status("⭕ 已关闭", COLORS["text_muted"])
                self.after(0, lambda: self._log("浏览器已关闭"))
            except Exception as ex:
                err_msg = str(ex)
                self._browser_manager = None
                self.after(0, lambda: self._log(f"⚠️ 关闭浏览器时出错: {err_msg}"))
                self._set_browser_status("⭕ 已关闭", COLORS["text_muted"])

        # 使用非daemon线程确保关闭完成
        threading.Thread(target=_run, name="BrowserClose", daemon=False).start()

    def _get_target_products(self) -> list[ProductItem]:
        products = self._get_products()
        if not products:
            return []
        scope = self._range_var.get()
        if scope == "pending":
            return [p for p in products if p.status == "pending"]
        elif scope == "selected":
            return [p for p in products if p.status in ("ai_done", "pending")]
        return products

    def _save_publish_config(self):
        config.set("publish", "auto_submit", self._auto_submit_var.get())
        config.set("publish", "batch_interval", self._interval_var.get())
        config.set("publish", "delay_min", self._delay_min_var.get())
        config.set("publish", "delay_max", self._delay_max_var.get())
        config.save()

    def _set_buttons_running(self, running: bool):
        def _update():
            state_normal = tk.DISABLED if running else tk.NORMAL
            state_stop = tk.NORMAL if running else tk.DISABLED
            self._btn_publish.configure(state=state_normal)
            self._btn_ai_only.configure(state=state_normal)
            self._btn_stop.configure(state=state_stop)
        self.after(0, _update)
        self._is_running = running

    def _stop_task(self):
        self._is_running = False
        self._log("⏹️ 用户请求停止任务...")
        self._task_status_var.set("正在停止...")
        self._set_buttons_running(False)
    
    def _save_ai_results(self):
        """保存所有AI处理结果到文件"""
        from tkinter import filedialog, messagebox
        
        products = self._get_products()
        if not products:
            messagebox.showwarning("提示", "没有可保存的商品，请先导入数据包")
            return
        
        # 检查是否有AI处理过的商品
        ai_processed = any(p.status == "ai_done" for p in products)
        if not ai_processed:
            messagebox.showinfo("提示", "没有AI处理过的商品，请先进行AI处理")
            return
        
        # 选择保存目录
        save_dir = filedialog.askdirectory(
            title="选择保存AI处理结果的目录",
            initialdir="./ai_results"
        )
        
        if not save_dir:
            return
        
        self._log(f"💾 开始保存AI处理结果到: {save_dir}")
        
        def _run():
            try:
                # 通过 async_runner 运行协程
                summary_file = async_runner.run(
                    self._ai_processor.save_all_ai_results(products, save_dir),
                    timeout=60,
                )
                
                def _done():
                    self._log(f"✅ AI处理结果已保存到: {summary_file}")
                    messagebox.showinfo(
                        "保存成功",
                        f"AI处理结果已保存到:\n{summary_file}\n\n包含汇总文件和详细商品数据"
                    )
                
                self.after(0, _done)
            except Exception as e:
                err_msg = str(e)
                
                def _error():
                    self._log(f"❌ 保存AI处理结果失败: {err_msg}")
                    messagebox.showerror("保存失败", f"保存AI处理结果失败:\n{err_msg}")
                
                self.after(0, _error)
        
        threading.Thread(target=_run, name="SaveAIResults", daemon=True).start()

    def _update_progress(self, current: int, total: int, msg: str, is_ai: bool = False):
        def _update():
            pct = int(current / total * 100) if total > 0 else 0
            if is_ai:
                self._ai_progress["value"] = pct
                self._ai_progress_label.config(text=f"{current} / {total}")
            else:
                self._total_progress["value"] = pct
                self._total_progress_label.config(text=f"{current} / {total}")
            self._current_op_var.set(msg)
        self.after(0, _update)

    def _update_stats(self, success: int, error: int, skip: int):
        def _update():
            self._stat_success_var.set(str(success))
            self._stat_error_var.set(str(error))
            self._stat_skip_var.set(str(skip))
        self.after(0, _update)

    def _start_ai_only(self):
        """仅执行 AI 处理"""
        products = self._get_target_products()
        if not products:
            messagebox.showwarning("提示", "没有可处理的商品，请先导入数据包")
            return
        
        # 检查图片生成选项
        generate_images = self._generate_images_var.get()
        image_output_dir = ""
        if generate_images:
            image_output_dir = self._image_output_var.get()
            if not image_output_dir:
                messagebox.showwarning("提示", "请设置图片输出目录")
                return
            
            # 检查是否有图片的商品
            has_images = any(p.main_images for p in products)
            if not has_images:
                messagebox.showwarning("提示", "所选商品中没有图片，无法生成新图片")
                return
        
        confirm_msg = f"将对 {len(products)} 个商品进行 AI 优化"
        if generate_images:
            confirm_msg += "\n并生成优化后的图片"
        confirm_msg += "，继续？"
        
        if not messagebox.askyesno("确认", confirm_msg):
            return

        self._save_publish_config()
        self._set_buttons_running(True)
        self.after(0, lambda: self._task_status_var.set("AI 处理中..."))
        
        if generate_images:
            self._log(f"🎨 开始 AI 批量处理 {len(products)} 个商品，并生成优化图片...")
        else:
            self._log(f"🤖 开始 AI 批量处理 {len(products)} 个商品...")

        def _run():
            import time
            success_cnt = error_cnt = 0
            total = len(products)

            for i, product in enumerate(products):
                if not self._is_running:
                    break

                product.status = "ai_processing"
                self.after(0, lambda p=products: self._refresh_csv(p))

                try:
                    def _cb(msg, idx=i):
                        self._update_progress(idx + 1, total, msg, is_ai=True)

                    # 通过 async_runner 运行协程
                    async_runner.run(
                        self._ai_processor.process_product(
                            product, 
                            _cb, 
                            generate_images=generate_images, 
                            image_output_dir=image_output_dir
                        ),
                        timeout=180 if generate_images else 120,
                    )
                    success_cnt += 1
                except Exception as ex:
                    err_msg = str(ex)
                    product.status = "ai_error"
                    product.error_msg = err_msg
                    error_cnt += 1
                    self.after(0, lambda m=err_msg: self._log(f"❌ AI 处理失败: {m}"))

                self._update_stats(success_cnt, error_cnt, 0)
                self.after(0, lambda p=products: self._refresh_csv(p))
                time.sleep(0.8)

            sc, ec = success_cnt, error_cnt

            def _done():
                self._set_buttons_running(False)
                self._task_status_var.set("AI 处理完成")
                self._log(f"✅ AI 处理完成！成功: {sc}, 失败: {ec}")
                messagebox.showinfo("完成", f"AI 处理完成！\n成功: {sc} 个\n失败: {ec} 个")

            self.after(0, _done)

        threading.Thread(target=_run, name="AIProcess", daemon=True).start()

    def _start_publish(self):
        """开始发布流程"""
        if not self._browser_manager or not self._browser_manager.is_alive:
            messagebox.showwarning("提示", "请先启动浏览器并登录淘宝")
            return

        products = self._get_target_products()
        if not products:
            messagebox.showwarning("提示", "没有可发布的商品，请先导入数据包")
            return

        use_ai = self._use_ai_var.get()
        auto_submit = self._auto_submit_var.get()
        interval = self._interval_var.get()
        generate_images = self._generate_images_var.get()
        image_output_dir = self._image_output_var.get() if generate_images else ""
        
        # 检查图片生成选项
        if generate_images and not image_output_dir:
            messagebox.showwarning("提示", "请设置图片输出目录")
            return
        
        # 构建确认信息
        confirm_msg = f"即将处理 {len(products)} 个商品\n\n"
        confirm_msg += f"• AI 优化：{'是' if use_ai else '否'}\n"
        if generate_images:
            confirm_msg += f"• 生成图片：是\n"
        confirm_msg += f"• 发布方式：{'直接发布' if auto_submit else '保存草稿'}\n"
        confirm_msg += f"• 商品间隔：{interval} 秒\n\n确认开始？"

        if not messagebox.askyesno("确认发布", confirm_msg):
            return

        self._save_publish_config()
        self._set_buttons_running(True)
        self.after(0, lambda: self._task_status_var.set("发布中..."))
        self._log(f"🚀 开始发布 {len(products)} 个商品")

        # 重置进度条
        def _reset():
            self._total_progress["value"] = 0
            self._ai_progress["value"] = 0
            self._stat_success_var.set("0")
            self._stat_error_var.set("0")
            self._stat_skip_var.set("0")
        self.after(0, _reset)

        def _run():
            import time
            from taobao_publisher.core.taobao_publisher import TaobaoPublisher

            success_cnt = error_cnt = skip_cnt = 0
            total = len(products)

            page = self._browser_manager.page
            publisher = TaobaoPublisher(page)
            publisher._delay_min = self._delay_min_var.get()
            publisher._delay_max = self._delay_max_var.get()

            try:
                for i, product in enumerate(products):
                    if not self._is_running:
                        skip_cnt += total - i
                        break

                    title_preview = product.title[:20]
                    self.after(0, lambda t=title_preview, idx=i:
                               self._current_op_var.set(f"处理 {idx + 1}/{total}: {t}..."))

                    # Step 1: AI 处理
                    if use_ai and product.status not in ("ai_done",):
                        product.status = "ai_processing"
                        self.after(0, lambda p=products: self._refresh_csv(p))
                        try:
                            def _ai_cb(msg, idx=i):
                                self._update_progress(idx + 1, total,
                                                      f"[AI] {msg}", is_ai=True)
                            async_runner.run(
                                self._ai_processor.process_product(
                                    product, 
                                    _ai_cb, 
                                    generate_images=generate_images, 
                                    image_output_dir=image_output_dir
                                ),
                                timeout=180 if generate_images else 120,
                            )
                        except Exception as ex:
                            err_msg = str(ex)
                            self.after(0, lambda m=err_msg:
                                       self._log(f"⚠️ AI 处理失败(继续发布): {m}"))

                    # Step 2: 发布到淘宝
                    try:
                        def _pub_cb(msg, idx=i):
                            self._update_progress(idx + 1, total,
                                                  f"[发布 {idx + 1}/{total}] {msg}")

                        success = async_runner.run(
                            publisher.publish_product(
                                product,
                                progress_callback=_pub_cb,
                                auto_submit=auto_submit,
                            ),
                            timeout=180,
                        )
                        if success:
                            success_cnt += 1
                        else:
                            error_cnt += 1
                    except Exception as ex:
                        err_msg = str(ex)
                        product.status = "error"
                        product.error_msg = err_msg
                        error_cnt += 1
                        self.after(0, lambda m=err_msg: self._log(f"❌ 发布失败: {m}"))

                    self._update_stats(success_cnt, error_cnt, skip_cnt)
                    self.after(0, lambda p=products: self._refresh_csv(p))

                    # 商品间隔
                    if i < total - 1 and self._is_running:
                        for _ in range(interval * 10):
                            if not self._is_running:
                                break
                            time.sleep(0.1)

            except Exception as ex:
                err_msg = str(ex)
                self.after(0, lambda m=err_msg:
                           self._log(f"❌ 发布任务异常终止: {m}"))

            finally:
                sc, ec, sk = success_cnt, error_cnt, skip_cnt

                def _done():
                    self._set_buttons_running(False)
                    self._task_status_var.set("发布任务完成")
                    summary = f"发布完成！\n✅ 成功: {sc}\n❌ 失败: {ec}\n⏭️ 跳过: {sk}"
                    self._log(f"🏁 成功:{sc} 失败:{ec} 跳过:{sk}")
                    messagebox.showinfo("发布完成", summary)

                self.after(0, _done)

        threading.Thread(target=_run, name="PublishTask", daemon=True).start()