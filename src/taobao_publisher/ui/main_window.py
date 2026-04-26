"""主窗口"""
import tkinter as tk
from tkinter import ttk
from pathlib import Path

from loguru import logger

from taobao_publisher.ui.styles import COLORS, setup_styles, get_default_font
from taobao_publisher.ui.frames.csv_frame import CSVFrame
from taobao_publisher.ui.frames.ai_settings_frame import AISettingsFrame
from taobao_publisher.ui.frames.publish_frame import PublishFrame
from taobao_publisher.ui.frames.log_frame import LogFrame
from taobao_publisher.core.csv_parser import ProductItem


class MainWindow:
    """主窗口管理器"""

    APP_TITLE = "淘宝商品 AI 智能发布软件"
    APP_VERSION = "v1.0.0"
    WIN_SIZE = "1280x820"
    WIN_MIN = (1100, 700)

    def __init__(self):
        self.root = tk.Tk()
        self._products: list[ProductItem] = []
        # 获取系统可用字体
        self._default_font = get_default_font()
        self._setup_window()
        self._setup_styles()
        self._build_ui()
        self._setup_logger()
        self._on_start()

    def _setup_window(self):
        """配置主窗口属性"""
        self.root.title(f"{self.APP_TITLE}  {self.APP_VERSION}")
        self.root.geometry(self.WIN_SIZE)
        self.root.minsize(*self.WIN_MIN)
        self.root.configure(bg=COLORS["bg_dark"])

        # 窗口居中
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        # 尝试设置图标
        icon_path = Path(__file__).parent.parent.parent.parent / "assets" / "icon.ico"
        if icon_path.exists():
            try:
                self.root.iconbitmap(str(icon_path))
            except Exception:
                pass

        # 退出确认
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_styles(self):
        """应用 UI 样式"""
        self._style = setup_styles(self.root)

    def _build_ui(self):
        """构建完整 UI 布局"""
        # ── 顶部 Header ──
        self._build_header()

        # ── 主体区域（左侧导航 + 右侧内容）──
        main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        # 左侧导航
        sidebar = self._build_sidebar(main_pane)
        main_pane.add(sidebar, weight=0)

        # 右侧内容区（上方 Notebook + 下方日志）
        right_pane = ttk.PanedWindow(main_pane, orient=tk.VERTICAL)
        main_pane.add(right_pane, weight=1)

        # 内容 Notebook
        content = self._build_content(right_pane)
        right_pane.add(content, weight=3)

        # 日志面板
        log_panel = self._build_log_panel(right_pane)
        right_pane.add(log_panel, weight=1)

        # ── 底部状态栏 ──
        self._build_statusbar()

    def _build_header(self):
        """顶部 Header 区域"""
        header = tk.Frame(self.root, bg=COLORS["primary"], height=56)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)

        # Logo + 标题
        logo_frame = tk.Frame(header, bg=COLORS["primary"])
        logo_frame.pack(side=tk.LEFT, padx=20, pady=8)

        tk.Label(
            logo_frame,
            text="🛍️",
            bg=COLORS["primary"], fg="white",
            font=(self._default_font, 22),
        ).pack(side=tk.LEFT)

        tk.Label(
            logo_frame,
            text=self.APP_TITLE,
            bg=COLORS["primary"], fg="white",
            font=(self._default_font, 16, "bold"),
        ).pack(side=tk.LEFT, padx=8)

        tk.Label(
            logo_frame,
            text=self.APP_VERSION,
            bg=COLORS["primary_dark"], fg="white",
            font=(self._default_font, 9),
            padx=6, pady=2,
        ).pack(side=tk.LEFT, padx=4)

        # 右侧信息
        right_info = tk.Frame(header, bg=COLORS["primary"])
        right_info.pack(side=tk.RIGHT, padx=20)

        self._header_status_var = tk.StringVar(value="就绪")
        tk.Label(
            right_info,
            textvariable=self._header_status_var,
            bg=COLORS["primary"], fg="white",
            font=(self._default_font, 10),
        ).pack(side=tk.RIGHT)

    def _build_sidebar(self, parent) -> ttk.Frame:
        """左侧导航栏"""
        sidebar = ttk.Frame(parent, style="Sidebar.TFrame", width=200)
        sidebar.pack_propagate(False)

        # 导航标题
        tk.Label(
            sidebar,
            text="功 能 菜 单",
            bg=COLORS["bg_input"],
            fg=COLORS["text_muted"],
            font=("微软雅黑", 9),
        ).pack(pady=(20, 8), padx=16, anchor=tk.W)

        nav_items = [
            ("📦", "数据包管理", 0),
            ("🤖", "AI 设置", 1),
            ("🚀", "发布管理", 2),
        ]

        self._nav_btns = []
        for icon, label, tab_idx in nav_items:
            btn = tk.Button(
                sidebar,
                text=f"  {icon}  {label}",
                bg=COLORS["bg_input"],
                fg=COLORS["text_secondary"],
                activebackground=COLORS["primary"],
                activeforeground="white",
                font=("微软雅黑", 11),
                borderwidth=0,
                anchor=tk.W,
                padx=16,
                pady=12,
                cursor="hand2",
                command=lambda idx=tab_idx: self._switch_tab(idx),
            )
            btn.pack(fill=tk.X, padx=4, pady=2)
            self._nav_btns.append(btn)

        # 分割线
        ttk.Separator(sidebar, orient=tk.HORIZONTAL).pack(
            fill=tk.X, padx=12, pady=16
        )

        # 快速说明
        tips = [
            "使用流程:",
            "① 导入 CSV 数据包",
            "② 配置 AI 参数",
            "③ 启动浏览器登录",
            "④ 点击开始发布",
        ]
        for tip in tips:
            color = COLORS["primary"] if tip.endswith(":") else COLORS["text_muted"]
            font_weight = "bold" if tip.endswith(":") else "normal"
            tk.Label(
                sidebar, text=tip,
                bg=COLORS["bg_input"],
                fg=color,
                font=("微软雅黑", 9, font_weight),
                anchor=tk.W,
            ).pack(fill=tk.X, padx=20, pady=1)

        return sidebar

    def _build_content(self, parent) -> ttk.Notebook:
        """右侧内容区 Notebook"""
        self._notebook = ttk.Notebook(parent, style="TNotebook")

        # Tab 1: 数据包管理
        self._csv_frame = CSVFrame(
            self._notebook,
            on_products_loaded=self._on_products_loaded,
        )
        self._notebook.add(self._csv_frame, text="  📦 数据包管理  ")

        # Tab 2: AI 设置
        self._ai_frame = AISettingsFrame(self._notebook)
        self._notebook.add(self._ai_frame, text="  🤖 AI 设置  ")

        # Tab 3: 发布管理
        self._publish_frame = PublishFrame(
            self._notebook,
            get_products=lambda: self._products,
            log_callback=self._log,
            refresh_csv_callback=self._on_products_refresh,
        )
        self._notebook.add(self._publish_frame, text="  🚀 发布管理  ")

        self._notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        return self._notebook

    def _build_log_panel(self, parent) -> LogFrame:
        """底部日志面板"""
        self._log_frame = LogFrame(parent)
        return self._log_frame

    def _build_statusbar(self):
        """底部状态栏"""
        statusbar = tk.Frame(self.root, bg=COLORS["bg_card"], height=28)
        statusbar.pack(fill=tk.X, side=tk.BOTTOM)
        statusbar.pack_propagate(False)

        self._status_var = tk.StringVar(value="就绪")
        tk.Label(
            statusbar,
            textvariable=self._status_var,
            bg=COLORS["bg_card"],
            fg=COLORS["text_muted"],
            font=("微软雅黑", 9),
        ).pack(side=tk.LEFT, padx=12)

        self._product_count_var = tk.StringVar(value="商品: 0")
        tk.Label(
            statusbar,
            textvariable=self._product_count_var,
            bg=COLORS["bg_card"],
            fg=COLORS["primary"],
            font=("微软雅黑", 9),
        ).pack(side=tk.RIGHT, padx=12)

    # ── 逻辑回调 ──────────────────────────────────────────────

    def _setup_logger(self):
        """注册 GUI 日志 sink"""
        logger.add(self._log_frame.log_sink, format="{message}", level="INFO")

    def _on_start(self):
        """启动后初始化"""
        self._log("欢迎使用淘宝商品 AI 智能发布软件！")
        self._log("请先导入 CSV 数据包，然后配置 AI 参数，最后启动浏览器开始发布。")
        self._switch_tab(0)

    def _switch_tab(self, idx: int):
        """切换标签页并高亮导航按钮"""
        self._notebook.select(idx)
        for i, btn in enumerate(self._nav_btns):
            if i == idx:
                btn.configure(
                    bg=COLORS["primary"],
                    fg="white",
                )
            else:
                btn.configure(
                    bg=COLORS["bg_input"],
                    fg=COLORS["text_secondary"],
                )

    def _on_tab_changed(self, event):
        """Notebook 标签切换事件"""
        idx = self._notebook.index(self._notebook.select())
        self._switch_tab(idx)

    def _on_products_loaded(self, products: list[ProductItem]):
        """CSV 导入完成回调"""
        self._products = products
        self._product_count_var.set(f"商品: {len(products)}")
        self._status_var.set(f"已导入 {len(products)} 个商品")
        self._log(f"📦 数据包导入成功，共 {len(products)} 个商品")

    def _on_products_refresh(self, products: list[ProductItem]):
        """发布过程中刷新列表"""
        self._products = products
        self._csv_frame.refresh(products)
        done = sum(1 for p in products if p.status == "done")
        self._product_count_var.set(f"商品: {len(products)} | 完成: {done}")

    def _log(self, msg: str):
        """统一日志方法（线程安全）"""
        self.root.after(0, lambda: self._log_frame.append(msg))
        logger.info(msg)

    def _on_close(self):
        """退出确认"""
        from tkinter import messagebox
        if messagebox.askyesno("退出确认", "确定要退出软件吗？\n浏览器将同时关闭。"):
            # 使用全局 async_runner 关闭浏览器
            if (hasattr(self._publish_frame, '_browser_manager')
                    and self._publish_frame._browser_manager):
                try:
                    self._publish_frame._browser_manager.close()
                except Exception as e:
                    from loguru import logger
                    logger.warning(f"关闭浏览器时出错: {e}")
            # 停止全局 async_runner
            try:
                from taobao_publisher.core.async_runner import async_runner
                async_runner.stop()
            except Exception as e:
                from loguru import logger
                logger.warning(f"停止 async_runner 时出错: {e}")
            # 清理临时文件
            try:
                import tempfile
                import shutil
                tmp_dir = Path(tempfile.gettempdir()) / "tbpub_imgs"
                if tmp_dir.exists():
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
            self.root.destroy()

    def run(self):
        """启动主循环"""
        self.root.mainloop()