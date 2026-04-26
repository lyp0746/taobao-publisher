"""CSV 数据预览面板 - 支持多图/视频/SKU 字段显示"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Callable, Optional
from pathlib import Path

from loguru import logger

from taobao_publisher.core.csv_parser import ProductItem, CSVParser, ProductAggregator
from taobao_publisher.ui.styles import COLORS, get_default_font


class CSVFrame(ttk.Frame):
    """CSV 导入与预览面板"""

    # 表格显示列配置（字段名 → (表头, 宽度, 对齐)）
    TABLE_COLUMNS: list[tuple[str, str, int, str]] = [
        ("row_index",    "#",       45,  "center"),
        ("status_icon",  "状态",    60,  "center"),
        ("display_title","标题",    220, "w"),
        ("category_id",  "类目ID",  80,  "center"),
        ("price_display","价格",    80,  "center"),
        ("stock_display","库存",    60,  "center"),
        ("main_img_cnt", "主图",    55,  "center"),
        ("detail_img_cnt","详情图", 60,  "center"),
        ("video_cnt",    "视频",    55,  "center"),
        ("spec_summary", "规格",    120, "w"),
        ("attr_summary", "属性",    150, "w"),
        ("status_text",  "处理状态",100, "center"),
    ]

    STATUS_ICONS = {
        "pending":       "⏳",
        "ai_processing": "🤖",
        "ai_done":       "✨",
        "ai_error":      "⚠️",
        "publishing":    "🔄",
        "done":          "✅",
        "error":         "❌",
    }

    STATUS_TEXT = {
        "pending":       "待处理",
        "ai_processing": "AI处理中",
        "ai_done":       "AI完成",
        "ai_error":      "AI失败",
        "publishing":    "发布中",
        "done":          "已完成",
        "error":         "发布失败",
    }

    def __init__(
        self,
        parent,
        on_products_loaded: Optional[Callable[[list[ProductItem]], None]] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)
        self.configure(style="TFrame")
        # 获取系统可用字体
        self._default_font = get_default_font()
        self._on_products_loaded = on_products_loaded
        self._products: list[ProductItem] = []
        self._parser = CSVParser()
        self._setup_ui()

    # ── UI 构建 ───────────────────────────────────────────────

    def _setup_ui(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_toolbar()
        self._build_table()
        self._build_statusbar()

    def _build_toolbar(self):
        bar = ttk.Frame(self, style="Card.TFrame")
        bar.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        bar.columnconfigure(6, weight=1)

        ttk.Button(
            bar, text="📂 导入 CSV/Excel",
            style="Primary.TButton",
            command=self._import_file,
        ).grid(row=0, column=0, padx=(12, 4), pady=10)

        ttk.Button(
            bar, text="🔄 重置状态",
            style="Secondary.TButton",
            command=self._reset_status,
        ).grid(row=0, column=1, padx=4, pady=10)

        ttk.Button(
            bar, text="🗑️ 清空数据",
            style="Ghost.TButton",
            command=self._clear_data,
        ).grid(row=0, column=2, padx=4, pady=10)

        ttk.Separator(bar, orient=tk.VERTICAL).grid(
            row=0, column=3, sticky="ns", padx=8, pady=6)

        ttk.Button(
            bar, text="👁️ 查看详情",
            style="Ghost.TButton",
            command=self._view_selected_detail,
        ).grid(row=0, column=4, padx=4, pady=10)

        ttk.Button(
            bar, text="📊 统计信息",
            style="Ghost.TButton",
            command=self._show_statistics,
        ).grid(row=0, column=5, padx=(4, 12), pady=10)

        # 聚合选项
        self._aggregate_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            bar, text="自动聚合同名商品（多行SKU→单商品）",
            variable=self._aggregate_var,
            style="Card.TCheckbutton",
        ).grid(row=0, column=6, padx=8, pady=10, sticky="e")

    def _build_table(self):
        frame = ttk.Frame(self, style="TFrame")
        frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        col_ids = [c[0] for c in self.TABLE_COLUMNS]
        self._tree = ttk.Treeview(
            frame,
            columns=col_ids,
            show="headings",
            selectmode="extended",
            style="Treeview",
        )

        for col_id, heading, width, anchor in self.TABLE_COLUMNS:
            self._tree.heading(col_id, text=heading,
                               command=lambda c=col_id: self._sort_by(c))
            self._tree.column(col_id, width=width, anchor=anchor,
                              minwidth=40, stretch=(col_id == "display_title"))

        # 滚动条
        vsb = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self._tree.yview)
        hsb = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

        # 行颜色标签
        self._tree.tag_configure("done",    background="#f0fff4", foreground="#22543d")
        self._tree.tag_configure("error",   background="#fff5f5", foreground="#c53030")
        self._tree.tag_configure("ai_done", background="#ebf8ff", foreground="#2b6cb0")
        self._tree.tag_configure("pending", background="white")

        self._tree.bind("<Double-1>", lambda e: self._view_selected_detail())
        self._tree.bind("<Button-3>", self._show_context_menu)

    def _build_statusbar(self):
        bar = ttk.Frame(self, style="Card.TFrame")
        bar.grid(row=2, column=0, sticky="ew")

        self._status_var = tk.StringVar(value="未导入数据")
        ttk.Label(
            bar,
            textvariable=self._status_var,
            style="Card.TLabel",
            foreground=COLORS["text_muted"],
        ).pack(side=tk.LEFT, padx=12, pady=6)

        # 快速统计
        self._stat_var = tk.StringVar(value="")
        ttk.Label(
            bar,
            textvariable=self._stat_var,
            style="Card.TLabel",
            foreground=COLORS["text_muted"],
        ).pack(side=tk.RIGHT, padx=12, pady=6)

    # ── 数据操作 ──────────────────────────────────────────────

    def _import_file(self):
        path = filedialog.askopenfilename(
            title="选择 CSV 或 Excel 文件",
            filetypes=[
                ("数据文件", "*.csv *.xlsx *.xls"),
                ("CSV 文件", "*.csv"),
                ("Excel 文件", "*.xlsx *.xls"),
                ("所有文件", "*.*"),
            ],
        )
        if not path:
            return

        self._status_var.set(f"正在解析: {Path(path).name} ...")
        self.update_idletasks()

        try:
            products = self._parser.parse(path)

            if self._aggregate_var.get() and products:
                products = ProductAggregator.aggregate(products)

            self._products = products
            self._refresh_table()

            if self._on_products_loaded:
                self._on_products_loaded(self._products)

            self._status_var.set(
                f"✅ 已加载: {Path(path).name}  |  {len(products)} 个商品"
            )
            self._update_stat_bar()

        except Exception as e:
            logger.error(f"导入失败: {e}", exc_info=True)
            messagebox.showerror("导入失败", f"文件解析出错：\n{e}")
            self._status_var.set("❌ 导入失败")

    def _reset_status(self):
        if not self._products:
            return
        for p in self._products:
            if p.status not in ("done",):
                p.status = "pending"
                p.error_msg = ""
        self._refresh_table()
        self._status_var.set(f"已重置 {len(self._products)} 个商品状态")

    def _clear_data(self):
        if self._products and not messagebox.askyesno("确认", "清空所有数据？"):
            return
        self._products = []
        self._refresh_table()
        self._status_var.set("数据已清空")
        self._stat_var.set("")

    # ── 表格刷新 ──────────────────────────────────────────────

    def _refresh_table(self, products: Optional[list[ProductItem]] = None):
        if products is not None:
            self._products = products
        self._tree.delete(*self._tree.get_children())
        for p in self._products:
            self._insert_row(p)
        self._update_stat_bar()

    def _insert_row(self, p: ProductItem):
        """插入一行商品数据"""
        # 价格显示
        if p.sku_list:
            prices = [s.price for s in p.sku_list if s.price > 0]
            if prices:
                if min(prices) == max(prices):
                    price_display = f"¥{prices[0]:.2f}"
                else:
                    price_display = f"¥{min(prices):.0f}~{max(prices):.0f}"
            else:
                price_display = f"¥{p.price:.2f}" if p.price > 0 else "-"
        else:
            price_display = f"¥{p.price:.2f}" if p.price > 0 else "-"

        # 库存显示
        if p.sku_list:
            total_stock = sum(s.stock for s in p.sku_list)
            stock_display = str(total_stock) if total_stock > 0 else str(p.stock)
        else:
            stock_display = str(p.stock) if p.stock > 0 else "-"

        # 规格摘要
        specs = p.ai_specs or p.specs
        spec_summary = " | ".join(
            f"{s.name}({len(s.values)})" for s in specs[:3]
        )
        if len(specs) > 3:
            spec_summary += f" +{len(specs) - 3}"

        # 属性摘要
        attr_summary = "；".join(
            f"{k}:{v}" for k, v in list(p.attributes.items())[:3]
        )

        values = (
            str(p.row_index + 1),
            self.STATUS_ICONS.get(p.status, "❓"),
            p.display_title[:40],
            p.category_id or "-",
            price_display,
            stock_display,
            str(len(p.main_images)),
            str(len(p.detail_images)),
            str(len(p.videos)),
            spec_summary or "-",
            attr_summary or "-",
            self.STATUS_TEXT.get(p.status, p.status),
        )

        tag = p.status if p.status in ("done", "error", "ai_done") else "pending"
        self._tree.insert("", tk.END, iid=str(p.row_index), values=values, tags=(tag,))

    def _update_stat_bar(self):
        if not self._products:
            self._stat_var.set("")
            return
        done    = sum(1 for p in self._products if p.status == "done")
        ai_done = sum(1 for p in self._products if p.status == "ai_done")
        errors  = sum(1 for p in self._products if p.status in ("error", "ai_error"))
        total   = len(self._products)
        self._stat_var.set(
            f"共 {total} 个  ✅ 完成 {done}  ✨ AI完成 {ai_done}  ❌ 失败 {errors}"
        )

    # ── 排序 ─────────────────────────────────────────────────

    def _sort_by(self, col_id: str):
        """点击表头排序"""
        items = [(self._tree.set(iid, col_id), iid)
                 for iid in self._tree.get_children("")]
        try:
            items.sort(key=lambda x: float(x[0].replace("¥", "").replace("-", "0")))
        except ValueError:
            items.sort(key=lambda x: x[0])

        for index, (_, iid) in enumerate(items):
            self._tree.move(iid, "", index)

    # ── 详情窗口 ──────────────────────────────────────────────

    def _view_selected_detail(self):
        selected = self._tree.selection()
        if not selected:
            messagebox.showinfo("提示", "请先选择一个商品")
            return
        row_index = int(selected[0])
        product = next((p for p in self._products if p.row_index == row_index), None)
        if product:
            ProductDetailWindow(self, product)

    # ── 右键菜单 ──────────────────────────────────────────────

    def _show_context_menu(self, event):
        iid = self._tree.identify_row(event.y)
        if not iid:
            return
        self._tree.selection_set(iid)

        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="👁️ 查看详情",  command=self._view_selected_detail)
        menu.add_command(label="🔄 重置状态",  command=self._reset_selected_status)
        menu.add_separator()
        menu.add_command(label="🗑️ 删除此行",  command=self._delete_selected)
        menu.post(event.x_root, event.y_root)

    def _reset_selected_status(self):
        for iid in self._tree.selection():
            row_index = int(iid)
            for p in self._products:
                if p.row_index == row_index:
                    p.status = "pending"
                    p.error_msg = ""
                    break
        self._refresh_table()

    def _delete_selected(self):
        selected_ids = {int(iid) for iid in self._tree.selection()}
        self._products = [p for p in self._products if p.row_index not in selected_ids]
        self._refresh_table()

    # ── 统计弹窗 ──────────────────────────────────────────────

    def _show_statistics(self):
        if not self._products:
            messagebox.showinfo("统计", "暂无数据")
            return

        total        = len(self._products)
        with_sku     = sum(1 for p in self._products if p.has_sku)
        with_imgs    = sum(1 for p in self._products if p.main_images)
        with_video   = sum(1 for p in self._products if p.videos)
        with_detail  = sum(1 for p in self._products if p.detail_images)
        total_imgs   = sum(len(p.main_images) for p in self._products)
        total_dets   = sum(len(p.detail_images) for p in self._products)
        total_vids   = sum(len(p.videos) for p in self._products)
        total_skus   = sum(len(p.sku_list) for p in self._products)
        with_attrs   = sum(1 for p in self._products if p.attributes)
        ai_done_cnt  = sum(1 for p in self._products if p.status == "ai_done")

        msg = (
            f"📊 数据统计\n\n"
            f"商品总数：{total}\n"
            f"有 SKU 规格：{with_sku}（共 {total_skus} 条SKU）\n"
            f"有主图：{with_imgs}（共 {total_imgs} 张）\n"
            f"有详情图：{with_detail}（共 {total_dets} 张）\n"
            f"有视频：{with_video}（共 {total_vids} 个）\n"
            f"有属性：{with_attrs}\n"
            f"AI 处理完成：{ai_done_cnt}\n"
        )
        messagebox.showinfo("数据统计", msg)

    # ── 公开接口 ──────────────────────────────────────────────

    def get_products(self) -> list[ProductItem]:
        return self._products

    def refresh(self, products: Optional[list[ProductItem]] = None):
        """外部刷新（publish_frame 回调用）"""
        self._refresh_table(products)


# ─────────────────────────────────────────────
#  商品详情弹窗
# ─────────────────────────────────────────────

class ProductDetailWindow(tk.Toplevel):
    """商品详情查看弹窗"""

    def __init__(self, parent, product: ProductItem):
        super().__init__(parent)
        self.title(f"商品详情 - {product.display_title[:30]}")
        self.geometry("700x600")
        self.resizable(True, True)
        self.grab_set()
        self._product = product
        # 获取系统可用字体
        self._default_font = get_default_font()
        self._build_ui()

    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # ── 基本信息 ──
        basic_frame = ttk.Frame(nb)
        nb.add(basic_frame, text="📋 基本信息")
        self._build_basic_tab(basic_frame)

        # ── 图片/视频 ──
        media_frame = ttk.Frame(nb)
        nb.add(media_frame, text="🖼️ 图片/视频")
        self._build_media_tab(media_frame)

        # ── 规格 SKU ──
        sku_frame = ttk.Frame(nb)
        nb.add(sku_frame, text="📦 规格 & SKU")
        self._build_sku_tab(sku_frame)

        # ── 描述 ──
        desc_frame = ttk.Frame(nb)
        nb.add(desc_frame, text="📝 描述")
        self._build_desc_tab(desc_frame)

        # ── 按钮栏 ──
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=8)
        
        ttk.Button(btn_frame, text="💾 保存AI优化结果", 
                  command=self._save_ai_results).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="关闭", command=self.destroy).pack(side=tk.LEFT, padx=5)

    def _build_basic_tab(self, parent):
        p = self._product
        canvas = tk.Canvas(parent, highlightthickness=0)
        sb = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>",
                   lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        rows = [
            ("商品标题",       p.title),
            ("AI 优化标题",    p.ai_title or "（未处理）"),
            ("类目 ID",        p.category_id or "未填写"),
            ("是否上架",       "是" if p.is_on_sale else "否"),
            ("一口价",         f"¥{p.price:.2f}" if p.price else "无"),
            ("库存",           str(p.stock) if p.stock else "无"),
            ("运费模板",       p.freight_template_id or "未填写"),
            ("图片分析",       p.ai_image_analysis or "（未分析）"),
            ("处理状态",       f"{p.status}  {p.error_msg or ''}"),
        ]
        # 属性
        if p.attributes:
            rows.append(("商品属性",
                         "\n".join(f"{k}: {v}" for k, v in p.attributes.items())))

        for i, (label, value) in enumerate(rows):
            ttk.Label(inner, text=label + "：",
                      font=(self._default_font, 9, "bold"),
                      width=12, anchor="ne").grid(
                row=i, column=0, sticky="ne", padx=(8, 4), pady=4)
            ttk.Label(inner, text=value,
                      wraplength=480, justify=tk.LEFT,
                      font=(self._default_font, 9)).grid(
                row=i, column=1, sticky="nw", padx=4, pady=4)

    def _build_media_tab(self, parent):
        p = self._product
        txt = tk.Text(parent, wrap=tk.WORD, font=(self._default_font, 9),
                      state=tk.NORMAL, padx=8, pady=8)
        sb = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        txt.pack(fill=tk.BOTH, expand=True)

        def _section(title: str, items: list[str]):
            txt.insert(tk.END, f"\n{'─'*40}\n{title}（{len(items)} 个）\n{'─'*40}\n")
            for i, item in enumerate(items, 1):
                txt.insert(tk.END, f"  {i:2d}. {item}\n")
            if not items:
                txt.insert(tk.END, "  （无）\n")

        _section("🖼️ 主图",   p.main_images)
        _section("📄 详情图", p.detail_images)
        _section("🎬 视频",   p.videos)
        txt.configure(state=tk.DISABLED)

    def _build_sku_tab(self, parent):
        p = self._product
        specs = p.ai_specs or p.specs

        # 规格维度
        dim_frame = ttk.LabelFrame(parent, text="规格维度")
        dim_frame.pack(fill=tk.X, padx=8, pady=(8, 4))

        if specs:
            for spec in specs:
                row = ttk.Frame(dim_frame)
                row.pack(fill=tk.X, padx=8, pady=2)
                ttk.Label(row, text=f"{spec.name}：",
                          font=(self._default_font, 9, "bold"), width=10).pack(side=tk.LEFT)
                ttk.Label(row, text=" | ".join(spec.values),
                          font=(self._default_font, 9)).pack(side=tk.LEFT)
        else:
            ttk.Label(dim_frame, text="无规格（单规格商品）",
                      foreground=COLORS["text_muted"]).pack(padx=8, pady=4)

        # SKU 表格
        sku_frame = ttk.LabelFrame(parent, text=f"SKU 列表（{len(p.sku_list)} 条）")
        sku_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        if p.sku_list:
            cols = ("combo", "price", "stock")
            tree = ttk.Treeview(sku_frame, columns=cols,
                                show="headings", height=8)
            tree.heading("combo", text="规格组合")
            tree.heading("price", text="价格")
            tree.heading("stock", text="库存")
            tree.column("combo", width=300, anchor="w")
            tree.column("price", width=100, anchor="center")
            tree.column("stock", width=100, anchor="center")

            sb2 = ttk.Scrollbar(sku_frame, orient=tk.VERTICAL,
                                command=tree.yview)
            tree.configure(yscrollcommand=sb2.set)
            sb2.pack(side=tk.RIGHT, fill=tk.Y)
            tree.pack(fill=tk.BOTH, expand=True)

            for sku in p.sku_list:
                tree.insert("", tk.END, values=(
                    sku.combo_str,
                    f"¥{sku.price:.2f}" if sku.price > 0 else "-",
                    str(sku.stock) if sku.stock > 0 else "-",
                ))
        else:
            ttk.Label(sku_frame, text="无 SKU 数据",
                      foreground=COLORS["text_muted"]).pack(padx=8, pady=8)

    def _build_desc_tab(self, parent):
        p = self._product
        nb2 = ttk.Notebook(parent)
        nb2.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        for tab_title, content in [
            ("原始描述", p.description),
            ("AI 优化描述", p.ai_description),
        ]:
            f = ttk.Frame(nb2)
            nb2.add(f, text=tab_title)
            txt = tk.Text(f, wrap=tk.WORD, font=(self._default_font, 9),
                          padx=8, pady=8, state=tk.NORMAL)
            sb = ttk.Scrollbar(f, orient=tk.VERTICAL, command=txt.yview)
            txt.configure(yscrollcommand=sb.set)
            sb.pack(side=tk.RIGHT, fill=tk.Y)
            txt.pack(fill=tk.BOTH, expand=True)
            txt.insert(tk.END, content or "（无内容）")
            txt.configure(state=tk.DISABLED)
    
    def _save_ai_results(self):
        """保存AI优化结果到文件"""
        from tkinter import filedialog, messagebox
        from datetime import datetime
        import os
        
        p = self._product
        
        # 如果没有AI处理结果，提示用户
        if not p.ai_title and not p.ai_description and not p.ai_specs:
            messagebox.showinfo("提示", "该商品暂无AI优化结果")
            return
        
        # 选择保存位置
        file_path = filedialog.asksaveasfilename(
            title="保存AI优化结果",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
            initialfile=f"AI优化_{p.title[:20]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(f"{'='*60}\n")
                f.write(f"商品AI优化结果\n")
                f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"{'='*60}\n\n")
                
                # 基本信息
                f.write(f"【基本信息】\n")
                f.write(f"原始标题: {p.title}\n")
                if p.ai_title:
                    f.write(f"AI优化标题: {p.ai_title}\n")
                f.write(f"类目: {p.category_id or '未填写'}\n")
                f.write(f"价格: ¥{p.price:.2f}\n")
                f.write(f"库存: {p.stock}\n")
                f.write(f"\n")
                
                # 描述
                f.write(f"【商品描述】\n")
                f.write(f"原始描述:\n{p.description or '无'}\n\n")
                if p.ai_description:
                    f.write(f"AI优化描述:\n{p.ai_description}\n\n")
                
                # 规格
                f.write(f"【规格信息】\n")
                if p.specs:
                    f.write(f"原始规格:\n")
                    for spec in p.specs:
                        f.write(f"  {spec.name}: {', '.join(spec.values)}\n")
                    f.write(f"\n")
                
                if p.ai_specs:
                    f.write(f"AI优化规格:\n")
                    for spec in p.ai_specs:
                        f.write(f"  {spec.name}: {', '.join(spec.values)}\n")
                    f.write(f"\n")
                
                # SKU
                if p.sku_list:
                    f.write(f"【SKU列表】\n")
                    for sku in p.sku_list:
                        f.write(f"  {sku.combo_str}: ¥{sku.price:.2f} (库存: {sku.stock})\n")
                    f.write(f"\n")
                
                # 属性
                if p.attributes:
                    f.write(f"【商品属性】\n")
                    for k, v in p.attributes.items():
                        f.write(f"  {k}: {v}\n")
                    f.write(f"\n")
                
                # 图片分析
                if p.ai_image_analysis:
                    f.write(f"【图片分析】\n")
                    f.write(f"{p.ai_image_analysis}\n\n")
                
                f.write(f"{'='*60}\n")
            
            messagebox.showinfo("成功", f"AI优化结果已保存到:\n{file_path}")
        except Exception as e:
            messagebox.showerror("错误", f"保存失败: {str(e)}")