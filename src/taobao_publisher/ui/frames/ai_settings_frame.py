"""AI 设置面板"""
import asyncio
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from taobao_publisher.utils.config import config
from taobao_publisher.ui.styles import COLORS, get_default_font


class AISettingsFrame(ttk.Frame):
    """AI 配置界面"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style="TFrame")
        # 获取系统可用字体
        self._default_font = get_default_font()
        self._vars: dict[str, tk.Variable] = {}
        self._setup_ui()
        self._load_config()

    def _setup_ui(self):
        # 滚动容器
        canvas = tk.Canvas(self, bg=COLORS["bg_dark"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._inner = ttk.Frame(canvas, style="TFrame")
        self._canvas_window = canvas.create_window((0, 0), window=self._inner, anchor="nw")

        self._inner.bind("<Configure>",
                         lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
                    lambda e: canvas.itemconfig(self._canvas_window, width=e.width))
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        inner = self._inner
        inner.columnconfigure(0, weight=1)

        # 标题
        title_frame = ttk.Frame(inner, style="TFrame")
        title_frame.grid(row=0, column=0, sticky="ew", padx=24, pady=(24, 8))
        ttk.Label(title_frame, text="🤖 AI 设置",
                  style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Label(title_frame, text="配置 AI 服务商及优化选项",
                  style="Muted.TLabel").pack(side=tk.LEFT, padx=(12, 0))

        # AI 提供商选择
        self._build_provider_section(inner, row=1)

        # 火山云配置
        self._build_volcano_section(inner, row=2)

        # OpenAI 配置
        self._build_openai_section(inner, row=3)

        # 自定义配置
        self._build_custom_section(inner, row=4)

        # AI 优化选项
        self._build_optimize_section(inner, row=5)

        # 测试按钮
        self._build_test_section(inner, row=6)

    def _make_card(self, parent, row: int, title: str) -> ttk.Frame:
        """创建卡片容器"""
        card = ttk.LabelFrame(parent, text=title, style="TLabelframe")
        card.grid(row=row, column=0, sticky="ew", padx=24, pady=8)
        card.columnconfigure(1, weight=1)
        return card

    def _add_entry_row(
        self, card, row: int, label: str, var_name: str,
        show: str = "", placeholder: str = ""
    ) -> ttk.Entry:
        """添加输入行"""
        ttk.Label(card, text=label, style="Card.TLabel").grid(
            row=row, column=0, sticky="w", padx=(12, 8), pady=6
        )
        var = tk.StringVar()
        self._vars[var_name] = var
        entry = ttk.Entry(card, textvariable=var, show=show,
                          font=("Consolas", 10), width=50)
        entry.grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=6)
        return entry

    def _build_provider_section(self, parent, row: int):
        card = self._make_card(parent, row, "  🌐 AI 服务提供商  ")

        providers = [
            ("🌋 火山云 (ByteDance)", "volcano"),
            ("🤖 OpenAI", "openai"),
            ("⚙️ 自定义接口", "custom"),
        ]

        self._vars["provider"] = tk.StringVar(value="volcano")
        for i, (label, value) in enumerate(providers):
            rb = ttk.Radiobutton(
                card, text=label, variable=self._vars["provider"],
                value=value, style="Card.TCheckbutton",
                command=self._on_provider_change,
            )
            rb.grid(row=0, column=i, padx=16, pady=12, sticky="w")

    def _build_volcano_section(self, parent, row: int):
        self._volcano_card = self._make_card(parent, row, "  🌋 火山云配置  ")
        self._add_entry_row(self._volcano_card, 0, "API Key：", "volcano_api_key", show="*")
        self._add_entry_row(self._volcano_card, 1, "Base URL：", "volcano_base_url")
        self._add_entry_row(self._volcano_card, 2, "文本模型 ID：", "volcano_model",
                            placeholder="ep-xxxxxxxx-xxxxx")
        self._add_entry_row(self._volcano_card, 3, "图片模型 ID：", "volcano_image_model",
                            placeholder="ep-xxxxxxxx-xxxxx（支持图片生成）")

        tip = ttk.Label(
            self._volcano_card,
            text="💡 前往 https://ark.cn-beijing.volces.com 创建 API Key 和模型接入点\n图片生成需要使用支持图片生成的模型",
            style="Card.TLabel",
            foreground=COLORS["text_muted"],
            font=(self._default_font, 8),
        )
        tip.grid(row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(0, 8))

    def _build_openai_section(self, parent, row: int):
        self._openai_card = self._make_card(parent, row, "  🤖 OpenAI 配置  ")
        self._add_entry_row(self._openai_card, 0, "API Key：", "openai_api_key", show="*")
        self._add_entry_row(self._openai_card, 1, "Base URL：", "openai_base_url")
        self._add_entry_row(self._openai_card, 2, "模型：", "openai_model")

    def _build_custom_section(self, parent, row: int):
        self._custom_card = self._make_card(parent, row, "  ⚙️ 自定义 API 配置  ")
        self._add_entry_row(self._custom_card, 0, "API Key：", "custom_api_key", show="*")
        self._add_entry_row(self._custom_card, 1, "Base URL：", "custom_base_url")
        self._add_entry_row(self._custom_card, 2, "模型：", "custom_model")

    def _build_optimize_section(self, parent, row: int):
        card = self._make_card(parent, row, "  ✨ AI 优化选项  ")

        opts = [
            ("optimize_title", "优化商品标题（提升搜索排名和点击率）"),
            ("optimize_description", "优化商品详情（增强转化率）"),
            ("optimize_specs", "优化规格属性（规范化名称和值）"),
        ]

        for i, (var_name, label) in enumerate(opts):
            var = tk.BooleanVar(value=True)
            self._vars[var_name] = var
            cb = ttk.Checkbutton(card, text=label, variable=var,
                                 style="Card.TCheckbutton")
            cb.grid(row=i, column=0, columnspan=2, sticky="w", padx=12, pady=4)

        # 标题风格
        ttk.Label(card, text="标题风格：", style="Card.TLabel").grid(
            row=len(opts), column=0, sticky="w", padx=(12, 8), pady=8
        )
        styles = ["电商爆款风格", "简洁专业", "时尚潮流", "性价比突出", "高端品质"]
        self._vars["title_style"] = tk.StringVar(value=styles[0])
        style_combo = ttk.Combobox(
            card, textvariable=self._vars["title_style"],
            values=styles, state="readonly", font=(self._default_font, 10), width=20,
        )
        style_combo.grid(row=len(opts), column=1, sticky="w", padx=(0, 12), pady=8)

        # 描述风格
        ttk.Label(card, text="描述风格：", style="Card.TLabel").grid(
            row=len(opts) + 1, column=0, sticky="w", padx=(12, 8), pady=8
        )
        desc_styles = ["专业详细", "简洁清晰", "故事营销", "数据驱动", "情感共鸣"]
        self._vars["description_style"] = tk.StringVar(value=desc_styles[0])
        desc_combo = ttk.Combobox(
            card, textvariable=self._vars["description_style"],
            values=desc_styles, state="readonly", font=(self._default_font, 10), width=20,
        )
        desc_combo.grid(row=len(opts) + 1, column=1, sticky="w", padx=(0, 12), pady=8)

    def _build_test_section(self, parent, row: int):
        btn_frame = ttk.Frame(parent, style="TFrame")
        btn_frame.grid(row=row, column=0, sticky="ew", padx=24, pady=16)

        ttk.Button(
            btn_frame, text="💾 保存配置", style="Primary.TButton",
            command=self.save_config,
        ).pack(side=tk.LEFT, padx=(0, 12))

        ttk.Button(
            btn_frame, text="🔌 测试连接", style="Secondary.TButton",
            command=self._test_connection,
        ).pack(side=tk.LEFT)

        self._test_status = ttk.Label(btn_frame, text="", style="Muted.TLabel")
        self._test_status.pack(side=tk.LEFT, padx=12)

    def _on_provider_change(self):
        """切换提供商时更新 UI"""
        provider = self._vars.get("provider")
        if provider:
            self.save_config()

    def _load_config(self):
        """从配置加载到 UI"""
        field_map = {
            "provider": ("ai", "provider"),
            "volcano_api_key": ("ai", "volcano_api_key"),
            "volcano_base_url": ("ai", "volcano_base_url"),
            "volcano_model": ("ai", "volcano_model"),
            "volcano_image_model": ("ai", "volcano_image_model"),
            "openai_api_key": ("ai", "openai_api_key"),
            "openai_base_url": ("ai", "openai_base_url"),
            "openai_model": ("ai", "openai_model"),
            "custom_api_key": ("ai", "custom_api_key"),
            "custom_base_url": ("ai", "custom_base_url"),
            "custom_model": ("ai", "custom_model"),
            "optimize_title": ("ai", "optimize_title"),
            "optimize_description": ("ai", "optimize_description"),
            "optimize_specs": ("ai", "optimize_specs"),
            "title_style": ("ai", "title_style"),
            "description_style": ("ai", "description_style"),
        }
        for var_name, keys in field_map.items():
            if var_name in self._vars:
                value = config.get(*keys, default="")
                if value is not None:
                    try:
                        self._vars[var_name].set(value)
                    except Exception:
                        pass

    def save_config(self):
        """保存配置"""
        field_map = {
            "provider": ("ai", "provider"),
            "volcano_api_key": ("ai", "volcano_api_key"),
            "volcano_base_url": ("ai", "volcano_base_url"),
            "volcano_model": ("ai", "volcano_model"),
            "openai_api_key": ("ai", "openai_api_key"),
            "openai_base_url": ("ai", "openai_base_url"),
            "openai_model": ("ai", "openai_model"),
            "custom_api_key": ("ai", "custom_api_key"),
            "custom_base_url": ("ai", "custom_base_url"),
            "custom_model": ("ai", "custom_model"),
            "optimize_title": ("ai", "optimize_title"),
            "optimize_description": ("ai", "optimize_description"),
            "optimize_specs": ("ai", "optimize_specs"),
            "title_style": ("ai", "title_style"),
            "description_style": ("ai", "description_style"),
        }
        for var_name, keys in field_map.items():
            if var_name in self._vars:
                config.set(*keys, self._vars[var_name].get())
        config.save()
        self._test_status.config(text="✅ 配置已保存", foreground=COLORS["success"])
        self.after(2000, lambda: self._test_status.config(text=""))

    def _test_connection(self):
        """异步测试 AI 连接"""
        self.save_config()
        self._test_status.config(text="⏳ 测试中...", foreground=COLORS["warning"])

        def _run():
            from taobao_publisher.core.ai_processor import AIProcessor
            processor = AIProcessor()
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            success, msg = loop.run_until_complete(processor.test_connection())
            loop.close()
            color = COLORS["success"] if success else COLORS["error"]
            self.after(0, lambda: self._test_status.config(text=msg[:60], foreground=color))

        threading.Thread(target=_run, daemon=True).start()