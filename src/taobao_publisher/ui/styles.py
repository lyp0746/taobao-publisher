"""UI 样式配置"""
import tkinter as tk
from tkinter import ttk
import sys
import platform


# 颜色主题
COLORS = {
    "primary": "#FF4400",       # 淘宝橙红
    "primary_dark": "#CC3300",
    "primary_light": "#FF6633",
    "secondary": "#1890FF",     # 蓝色强调
    "success": "#52C41A",
    "warning": "#FAAD14",
    "error": "#FF4D4F",
    "bg_dark": "#1A1A2E",       # 深色背景
    "bg_card": "#16213E",
    "bg_input": "#0F3460",
    "text_primary": "#FFFFFF",
    "text_secondary": "#A0AEC0",
    "text_muted": "#718096",
    "border": "#2D3748",
    "hover": "#2A4A7F",
    "gradient_start": "#FF4400",
    "gradient_end": "#FF8C00",
}

# 状态颜色
STATUS_COLORS = {
    "pending": "#718096",
    "ai_processing": "#1890FF",
    "ai_done": "#52C41A",
    "ai_error": "#FAAD14",
    "publishing": "#FF8C00",
    "done": "#52C41A",
    "error": "#FF4D4F",
}

STATUS_LABELS = {
    "pending": "⏳ 等待中",
    "ai_processing": "🤖 AI处理中",
    "ai_done": "✨ AI完成",
    "ai_error": "⚠️ AI失败",
    "publishing": "📤 发布中",
    "done": "✅ 已完成",
    "error": "❌ 出错",
}


def get_default_font():
    """获取系统默认字体，优先使用微软雅黑，否则回退到系统默认"""
    if platform.system() == "Windows":
        # 在 Windows 上尝试使用微软雅黑
        try:
            # 测试字体是否可用
            test_label = tk.Label(font=("微软雅黑", 10))
            test_label.destroy()
            return "微软雅黑"
        except (tk.TclError, Exception):
            # 如果微软雅黑不可用，使用系统默认
            return "TkDefaultFont"
    else:
        # 非 Windows 系统使用系统默认字体
        return "TkDefaultFont"


def setup_styles(root: tk.Tk) -> ttk.Style:
    """配置全局 TTK 样式"""
    style = ttk.Style(root)
    style.theme_use("clam")

    # 获取可用字体
    default_font = get_default_font()
    
    bg = COLORS["bg_dark"]
    card = COLORS["bg_card"]
    primary = COLORS["primary"]
    text = COLORS["text_primary"]
    text2 = COLORS["text_secondary"]
    border = COLORS["border"]

    # ── 通用 Frame 样式 ──
    style.configure("TFrame", background=bg)
    style.configure("Card.TFrame", background=card, relief="flat")
    style.configure("Sidebar.TFrame", background=COLORS["bg_input"])

    # ── Label 样式 ──
    style.configure("TLabel", background=bg, foreground=text, font=(default_font, 10))
    style.configure("Title.TLabel", background=bg, foreground=text,
                    font=(default_font, 20, "bold"))
    style.configure("Subtitle.TLabel", background=bg, foreground=primary,
                    font=(default_font, 11, "bold"))
    style.configure("Card.TLabel", background=card, foreground=text,
                    font=(default_font, 10))
    style.configure("CardTitle.TLabel", background=card, foreground=primary,
                    font=(default_font, 12, "bold"))
    style.configure("Muted.TLabel", background=bg, foreground=text2,
                    font=(default_font, 9))
    style.configure("Success.TLabel", background=bg, foreground=COLORS["success"],
                    font=(default_font, 10))
    style.configure("Error.TLabel", background=bg, foreground=COLORS["error"],
                    font=(default_font, 10))

    # ── Button 样式 ──
    style.configure(
        "Primary.TButton",
        background=primary, foreground="white",
        font=("微软雅黑", 10, "bold"),
        borderwidth=0, focusthickness=0, relief="flat",
        padding=(16, 8),
    )
    style.map("Primary.TButton",
              background=[("active", COLORS["primary_dark"]),
                          ("disabled", "#555555")],
              foreground=[("disabled", "#888888")])

    style.configure(
        "Secondary.TButton",
        background=COLORS["secondary"], foreground="white",
        font=("微软雅黑", 10),
        borderwidth=0, focusthickness=0, relief="flat",
        padding=(12, 6),
    )
    style.map("Secondary.TButton",
              background=[("active", "#0D70D0")])

    style.configure(
        "Success.TButton",
        background=COLORS["success"], foreground="white",
        font=("微软雅黑", 10, "bold"),
        borderwidth=0, focusthickness=0, relief="flat",
        padding=(16, 8),
    )
    style.map("Success.TButton",
              background=[("active", "#389E0D")])

    style.configure(
        "Danger.TButton",
        background=COLORS["error"], foreground="white",
        font=("微软雅黑", 10),
        borderwidth=0, focusthickness=0, relief="flat",
        padding=(12, 6),
    )

    style.configure(
        "Ghost.TButton",
        background=card, foreground=text2,
        font=("微软雅黑", 9),
        borderwidth=1, relief="flat",
        padding=(8, 4),
    )
    style.map("Ghost.TButton",
              background=[("active", COLORS["hover"])],
              foreground=[("active", text)])

    # ── Notebook 样式 ──
    style.configure(
        "TNotebook",
        background=bg, borderwidth=0,
        tabmargins=[0, 0, 0, 0],
    )
    style.configure(
        "TNotebook.Tab",
        background=card, foreground=text2,
        font=("微软雅黑", 10),
        padding=[16, 8],
        borderwidth=0,
    )
    style.map("TNotebook.Tab",
              background=[("selected", primary)],
              foreground=[("selected", "white")])

    # ── Entry 样式 ──
    style.configure(
        "TEntry",
        fieldbackground=COLORS["bg_input"],
        foreground=text,
        insertcolor=text,
        borderwidth=1,
        relief="flat",
        font=("微软雅黑", 10),
    )
    style.map("TEntry",
              fieldbackground=[("focus", COLORS["hover"])],
              bordercolor=[("focus", primary)])

    # ── Combobox 样式 ──
    style.configure(
        "TCombobox",
        fieldbackground=COLORS["bg_input"],
        background=COLORS["bg_input"],
        foreground=text,
        selectbackground=primary,
        borderwidth=1,
        font=("微软雅黑", 10),
    )

    # ── Progressbar 样式 ──
    style.configure(
        "TProgressbar",
        background=primary,
        troughcolor=card,
        borderwidth=0,
        thickness=6,
    )

    # ── Scrollbar 样式 ──
    style.configure(
        "TScrollbar",
        background=card,
        troughcolor=bg,
        borderwidth=0,
        arrowcolor=text2,
        width=8,
    )
    style.map("TScrollbar", background=[("active", primary)])

    # ── Treeview 样式 ──
    style.configure(
        "TTreeview",
        background=card,
        fieldbackground=card,
        foreground=text,
        rowheight=32,
        borderwidth=0,
        font=("微软雅黑", 9),
    )
    style.configure(
        "TTreeview.Heading",
        background=COLORS["bg_input"],
        foreground=primary,
        font=("微软雅黑", 9, "bold"),
        borderwidth=0,
        relief="flat",
    )
    style.map("TTreeview",
              background=[("selected", COLORS["hover"])],
              foreground=[("selected", text)])

    # ── Checkbutton 样式 ──
    style.configure(
        "TCheckbutton",
        background=bg, foreground=text,
        font=("微软雅黑", 10),
    )
    style.configure(
        "Card.TCheckbutton",
        background=card, foreground=text,
        font=("微软雅黑", 10),
    )

    # ── Separator 样式 ──
    style.configure("TSeparator", background=border)

    # ── LabelFrame 样式 ──
    style.configure(
        "TLabelframe",
        background=card, bordercolor=border,
        relief="solid", borderwidth=1,
    )
    style.configure(
        "TLabelframe.Label",
        background=card, foreground=primary,
        font=("微软雅黑", 10, "bold"),
    )

    return style