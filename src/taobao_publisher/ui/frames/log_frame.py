"""日志面板"""
import tkinter as tk
from tkinter import ttk
from datetime import datetime

from taobao_publisher.ui.styles import COLORS


class LogFrame(ttk.Frame):
    """实时日志显示面板"""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        self.configure(style="Card.TFrame")
        self._max_lines = 500
        self._setup_ui()

    def _setup_ui(self):
        # 标题栏
        header = ttk.Frame(self, style="Card.TFrame")
        header.pack(fill=tk.X, padx=12, pady=(12, 0))

        ttk.Label(header, text="📋 运行日志", style="CardTitle.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="清除", style="Ghost.TButton",
                   command=self.clear).pack(side=tk.RIGHT)

        # 日志文本区
        text_frame = ttk.Frame(self, style="Card.TFrame")
        text_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        self._text = tk.Text(
            text_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg=COLORS["bg_dark"],
            fg=COLORS["text_secondary"],
            font=("Consolas", 9),
            borderwidth=0,
            highlightthickness=0,
            insertbackground=COLORS["text_primary"],
            selectbackground=COLORS["primary"],
            padx=8, pady=4,
        )

        scrollbar = ttk.Scrollbar(text_frame, orient=tk.VERTICAL,
                                  command=self._text.yview)
        self._text.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 配置日志级别颜色
        self._text.tag_configure("TIME", foreground=COLORS["text_muted"])
        self._text.tag_configure("INFO", foreground=COLORS["text_secondary"])
        self._text.tag_configure("SUCCESS", foreground=COLORS["success"])
        self._text.tag_configure("WARNING", foreground=COLORS["warning"])
        self._text.tag_configure("ERROR", foreground=COLORS["error"])
        self._text.tag_configure("DEBUG", foreground=COLORS["text_muted"])
        self._text.tag_configure("AI", foreground="#9B59B6")
        self._text.tag_configure("PUBLISH", foreground=COLORS["primary"])

    def append(self, message: str, level: str = "INFO"):
        """追加一条日志"""
        self._text.configure(state=tk.NORMAL)

        # 限制行数
        current_lines = int(self._text.index("end-1c").split(".")[0])
        if current_lines > self._max_lines:
            self._text.delete("1.0", "100.0")

        time_str = datetime.now().strftime("%H:%M:%S")
        level_upper = level.upper()

        # 确定标签
        if "成功" in message or "✅" in message or "完成" in message:
            tag = "SUCCESS"
        elif "错误" in message or "失败" in message or "❌" in message:
            tag = "ERROR"
        elif "警告" in message or "⚠️" in message:
            tag = "WARNING"
        elif "AI" in message or "🤖" in message:
            tag = "AI"
        elif "发布" in message or "📤" in message:
            tag = "PUBLISH"
        else:
            tag = level_upper if level_upper in ("INFO", "DEBUG", "WARNING", "ERROR") else "INFO"

        self._text.insert(tk.END, f"{time_str} ", "TIME")
        self._text.insert(tk.END, f"{message}\n", tag)

        self._text.configure(state=tk.DISABLED)
        self._text.see(tk.END)

    def clear(self):
        """清除日志"""
        self._text.configure(state=tk.NORMAL)
        self._text.delete("1.0", tk.END)
        self._text.configure(state=tk.DISABLED)

    def log_sink(self, message):
        """作为 loguru sink 使用"""
        record = message.record
        level = record["level"].name
        msg = record["message"]
        self.after(0, lambda: self.append(msg, level))