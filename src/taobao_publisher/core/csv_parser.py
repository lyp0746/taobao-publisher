"""
CSV 商品数据包解析器
支持动态多图、多视频、多规格SKU、属性字段
表头格式：
  商品标题,类目ID,是否上架,一口价,库存,运费模板ID,
  主图1..N, 视频1..N, 商品描述, 详情图1..N,
  规格名1,规格值1,规格名2,规格值2,...,规格价格,规格库存,
  属性
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import chardet
import pandas as pd
from loguru import logger


# ─────────────────────────────────────────────
#  数据模型
# ─────────────────────────────────────────────

@dataclass
class SkuItem:
    """单条 SKU 记录（规格组合 + 价格 + 库存）"""
    spec_combo: dict[str, str]   # {"颜色": "金色", "尺寸": "20cm"}
    price: float = 0.0
    stock: int = 0

    @property
    def combo_str(self) -> str:
        return ";".join(f"{k}:{v}" for k, v in self.spec_combo.items())


@dataclass
class ProductSpec:
    """规格维度"""
    name: str           # 规格名称，如"颜色"
    values: list[str]   # 所有可选值，如["金色","银色"]


@dataclass
class ProductItem:
    """单个商品完整数据"""
    # ── 基本信息 ──
    title: str = ""
    category_id: str = ""           # 类目ID
    is_on_sale: bool = True         # 是否上架
    price: float = 0.0              # 一口价（单规格）
    stock: int = 0                  # 库存（单规格）
    freight_template_id: str = ""   # 运费模板ID

    # ── 图片 ──
    main_images: list[str] = field(default_factory=list)    # 主图列表（主图1~N）
    detail_images: list[str] = field(default_factory=list)  # 详情图列表
    videos: list[str] = field(default_factory=list)         # 视频列表

    # ── 描述 ──
    description: str = ""

    # ── 规格 & SKU ──
    specs: list[ProductSpec] = field(default_factory=list)  # 规格维度
    sku_list: list[SkuItem] = field(default_factory=list)   # SKU 明细列表

    # ── 属性 ──
    attributes: dict[str, str] = field(default_factory=dict)  # {"材质":"树脂",...}

    # ── AI 结果 ──
    ai_title: str = ""
    ai_description: str = ""
    ai_specs: list[ProductSpec] = field(default_factory=list)
    ai_image_analysis: str = ""     # 主图 AI 分析文本

    # ── 状态 ──
    status: str = "pending"
    error_msg: str = ""
    row_index: int = 0

    # ── 便捷属性 ──
    @property
    def display_title(self) -> str:
        return self.ai_title or self.title

    @property
    def display_description(self) -> str:
        return self.ai_description or self.description

    @property
    def main_image(self) -> str:
        """第一张主图"""
        return self.main_images[0] if self.main_images else ""

    @property
    def has_sku(self) -> bool:
        return len(self.specs) > 0

    @property
    def is_url(self) -> bool:
        return self.main_image.startswith("http")


# ─────────────────────────────────────────────
#  解析器
# ─────────────────────────────────────────────

class CSVParser:
    """
    淘宝上架 CSV 解析器
    支持动态列：主图N / 详情图N / 视频N / 规格名N+规格值N
    """

    # 固定列名映射（中文 → 字段名）
    FIXED_COLUMNS = {
        "title":               ["商品标题", "标题", "title", "name"],
        "category_id":         ["类目ID", "类目id", "类目", "category_id", "category"],
        "is_on_sale":          ["是否上架", "上架", "is_on_sale"],
        "price":               ["一口价", "价格", "售价", "price"],
        "stock":               ["库存", "stock", "inventory"],
        "freight_template_id": ["运费模板ID", "运费模板id", "运费模板", "freight_template_id"],
        "description":         ["商品描述", "描述", "详情", "description"],
        "sku_price":           ["规格价格", "sku价格", "sku_price"],
        "sku_stock":           ["规格库存", "sku库存", "sku_stock"],
        "attributes":          ["属性", "attributes"],
    }

    def __init__(self):
        self._products: list[ProductItem] = []

    # ── 公开接口 ──────────────────────────────

    def parse(self, file_path: str) -> list[ProductItem]:
        """解析 CSV / Excel 文件，返回 ProductItem 列表"""
        path = Path(file_path)
        logger.info(f"开始解析: {path.name}")

        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        try:
            df = self._read_file(path)
            df = df.fillna("").astype(str)
            df.columns = [c.strip() for c in df.columns]
            logger.info(f"读取到 {len(df)} 行，{len(df.columns)} 列")

            col_map = self._build_column_map(list(df.columns))
            self._log_column_map(col_map, list(df.columns))

            self._products = []
            for idx, row in df.iterrows():
                try:
                    product = self._parse_row(row, col_map, int(str(idx)))
                    if product.title.strip():
                        self._products.append(product)
                except Exception as e:
                    logger.warning(f"第 {int(str(idx)) + 2} 行解析失败: {e}")

            logger.success(f"解析完成，共 {len(self._products)} 个有效商品")
            return self._products

        except Exception as e:
            logger.error(f"文件解析失败: {e}")
            raise

    @property
    def products(self) -> list[ProductItem]:
        return self._products

    # ── 私有：文件读取 ─────────────────────────

    def _read_file(self, path: Path) -> pd.DataFrame:
        if path.suffix.lower() in (".xlsx", ".xls"):
            return pd.read_excel(path, dtype=str)
        else:
            enc = self._detect_encoding(str(path))
            return pd.read_csv(path, encoding=enc, dtype=str)

    def _detect_encoding(self, file_path: str) -> str:
        with open(file_path, "rb") as f:
            raw = f.read(20000)
        result = chardet.detect(raw)
        enc = result.get("encoding") or "utf-8"
        if enc.lower() in ("gb2312", "gbk", "gb18030"):
            enc = "gbk"
        logger.debug(f"检测编码: {enc}（置信度 {result.get('confidence', 0):.2f}）")
        return enc

    # ── 私有：列名映射 ─────────────────────────

    def _build_column_map(self, columns: list[str]) -> dict:
        """
        构建列名映射字典，包含：
          fixed_map:   固定字段 → 列名
          main_imgs:   [主图1列名, 主图2列名, ...]（有序）
          detail_imgs: [详情图1列名, ...]
          videos:      [视频1列名, ...]
          spec_pairs:  [(规格名1列, 规格值1列), (规格名2列, 规格值2列), ...]
        """
        lower_cols = {c.lower(): c for c in columns}

        # 固定列
        fixed_map: dict[str, str] = {}
        for field_name, aliases in self.FIXED_COLUMNS.items():
            for alias in aliases:
                if alias.lower() in lower_cols:
                    fixed_map[field_name] = lower_cols[alias.lower()]
                    break

        # 动态图片 / 视频列（按数字索引排序）
        main_imgs   = self._find_indexed_cols(columns, r"^主图(\d+)$")
        detail_imgs = self._find_indexed_cols(columns, r"^详情图(\d+)$")
        videos      = self._find_indexed_cols(columns, r"^视频(\d+)$")

        # 规格对：(规格名N, 规格值N)
        spec_name_cols  = self._find_indexed_cols(columns, r"^规格名(\d+)$")
        spec_value_cols = self._find_indexed_cols(columns, r"^规格值(\d+)$")
        # 按索引匹配 name-value 对
        spec_pairs = self._pair_spec_cols(columns, spec_name_cols, spec_value_cols)

        return {
            "fixed":       fixed_map,
            "main_imgs":   main_imgs,
            "detail_imgs": detail_imgs,
            "videos":      videos,
            "spec_pairs":  spec_pairs,
        }

    def _find_indexed_cols(self, columns: list[str], pattern: str) -> list[str]:
        """找到所有匹配 pattern 的列，按数字索引升序返回"""
        matched: list[tuple[int, str]] = []
        for col in columns:
            m = re.match(pattern, col.strip())
            if m:
                matched.append((int(m.group(1)), col))
        matched.sort(key=lambda x: x[0])
        return [col for _, col in matched]

    def _pair_spec_cols(
        self,
        columns: list[str],
        name_cols: list[str],
        value_cols: list[str],
    ) -> list[tuple[str, str]]:
        """将规格名N和规格值N按序号配对"""
        col_set = set(columns)
        pairs: list[tuple[str, str]] = []

        for nc in name_cols:
            m = re.match(r"^规格名(\d+)$", nc.strip())
            if not m:
                continue
            idx = m.group(1)
            vc = f"规格值{idx}"
            if vc in col_set:
                pairs.append((nc, vc))
            else:
                # 尝试找最近的 value col
                for v in value_cols:
                    mv = re.match(r"^规格值(\d+)$", v.strip())
                    if mv and mv.group(1) == idx:
                        pairs.append((nc, v))
                        break

        return pairs

    def _log_column_map(self, col_map: dict, all_cols: list[str]):
        logger.debug(f"固定列映射: {col_map['fixed']}")
        logger.debug(f"主图列: {col_map['main_imgs']}")
        logger.debug(f"详情图列: {col_map['detail_imgs']}")
        logger.debug(f"视频列: {col_map['videos']}")
        logger.debug(f"规格对: {col_map['spec_pairs']}")

    # ── 私有：行解析 ───────────────────────────

    def _parse_row(self, row: pd.Series, col_map: dict, idx: int) -> ProductItem:
        fm = col_map["fixed"]
        product = ProductItem(row_index=idx)

        # ── 基本字段 ──
        product.title = self._get(row, fm, "title")
        product.category_id = self._get(row, fm, "category_id")
        product.description = self._get(row, fm, "description")
        product.freight_template_id = self._get(row, fm, "freight_template_id")

        # 是否上架（默认 True）
        on_sale_str = self._get(row, fm, "is_on_sale").strip().lower()
        product.is_on_sale = on_sale_str not in ("0", "false", "否", "no", "下架")

        # 一口价
        product.price = self._parse_float(self._get(row, fm, "price"))
        # 库存
        product.stock = self._parse_int(self._get(row, fm, "stock"))

        # ── 动态图片 / 视频 ──
        product.main_images = self._collect_nonempty(row, col_map["main_imgs"])
        product.detail_images = self._collect_nonempty(row, col_map["detail_imgs"])
        product.videos = self._collect_nonempty(row, col_map["videos"])

        # ── 规格 & SKU ──
        product.specs, product.sku_list = self._parse_specs_and_sku(
            row, col_map["spec_pairs"],
            sku_price_str=self._get(row, fm, "sku_price"),
            sku_stock_str=self._get(row, fm, "sku_stock"),
        )

        # ── 属性 ──
        product.attributes = self._parse_attributes(self._get(row, fm, "attributes"))

        return product

    # ── 私有：字段解析辅助 ────────────────────

    def _get(self, row: pd.Series, fixed_map: dict, field_name: str,
             default: str = "") -> str:
        col = fixed_map.get(field_name)
        if col and col in row.index:
            return str(row[col]).strip()
        return default

    def _collect_nonempty(self, row: pd.Series, col_names: list[str]) -> list[str]:
        """按顺序收集不为空的列值"""
        result = []
        for col in col_names:
            if col in row.index:
                val = str(row[col]).strip()
                if val and val.lower() not in ("nan", "none", ""):
                    result.append(val)
        return result

    def _parse_float(self, s: str) -> float:
        try:
            return float(re.sub(r"[^\d.]", "", s))
        except (ValueError, TypeError):
            return 0.0

    def _parse_int(self, s: str) -> int:
        try:
            return int(float(re.sub(r"[^\d.]", "", s)))
        except (ValueError, TypeError):
            return 0

    def _parse_specs_and_sku(
        self,
        row: pd.Series,
        spec_pairs: list[tuple[str, str]],
        sku_price_str: str,
        sku_stock_str: str,
    ) -> tuple[list[ProductSpec], list[SkuItem]]:
        """
        解析规格维度和 SKU。
        每行 CSV 代表一条 SKU 记录（特定规格组合）。
        调用方需在合并同商品多行时聚合，这里仅解析单行。
        """
        specs: list[ProductSpec] = []
        combo: dict[str, str] = {}

        for name_col, value_col in spec_pairs:
            spec_name = ""
            if name_col in row.index:
                spec_name = str(row[name_col]).strip()
            spec_value = ""
            if value_col in row.index:
                spec_value = str(row[value_col]).strip()

            if not spec_name or not spec_value:
                continue

            # 构建 ProductSpec（单行只有一个值）
            specs.append(ProductSpec(name=spec_name, values=[spec_value]))
            combo[spec_name] = spec_value

        # SKU 价格 & 库存
        sku_price = self._parse_float(sku_price_str)
        sku_stock = self._parse_int(sku_stock_str)

        sku_list: list[SkuItem] = []
        if combo:
            sku_list.append(SkuItem(
                spec_combo=combo,
                price=sku_price,
                stock=sku_stock,
            ))

        return specs, sku_list

    def _parse_attributes(self, attr_str: str) -> dict[str, str]:
        """
        解析属性字符串：
          "材质:树脂;风格:国潮;适用场景:家居摆件"
          → {"材质": "树脂", "风格": "国潮", "适用场景": "家居摆件"}
        """
        result: dict[str, str] = {}
        if not attr_str.strip():
            return result

        # 支持 ; 或 ； 或 | 分隔
        parts = re.split(r"[;；|]", attr_str)
        for part in parts:
            # 支持 : 或 ：
            kv = re.split(r"[:：]", part, maxsplit=1)
            if len(kv) == 2:
                k, v = kv[0].strip(), kv[1].strip()
                if k and v:
                    result[k] = v

        return result


# ─────────────────────────────────────────────
#  多行 SKU 聚合器（同商品有多行时使用）
# ─────────────────────────────────────────────

class ProductAggregator:
    """
    将多行（同标题）的 SKU 记录聚合为一个 ProductItem。
    用法：在 CSVParser.parse() 之后调用 aggregate()。
    """

    @staticmethod
    def aggregate(products: list[ProductItem]) -> list[ProductItem]:
        """
        按商品标题聚合：相同标题的多行 → 合并为一个 ProductItem，
        specs 合并去重，sku_list 追加。
        """
        from collections import OrderedDict

        groups: OrderedDict[str, list[ProductItem]] = OrderedDict()
        for p in products:
            key = p.title.strip()
            groups.setdefault(key, []).append(p)

        result: list[ProductItem] = []
        for title, items in groups.items():
            if len(items) == 1:
                result.append(items[0])
            else:
                merged = ProductAggregator._merge(items)
                result.append(merged)
                logger.debug(f"聚合商品 [{title[:20]}]: {len(items)} 行 → "
                             f"{len(merged.specs)} 规格维度, "
                             f"{len(merged.sku_list)} 个 SKU")

        logger.info(f"聚合完成: {len(products)} 行 → {len(result)} 个商品")
        return result

    @staticmethod
    def _merge(items: list[ProductItem]) -> ProductItem:
        base = items[0]
        merged_specs: dict[str, set[str]] = {}

        for item in items:
            # 合并规格维度
            for spec in item.specs:
                merged_specs.setdefault(spec.name, set()).update(spec.values)
            # 合并 SKU 列表
            for sku in item.sku_list:
                if sku not in base.sku_list:
                    base.sku_list.append(sku)

        # 重建规格（保持顺序）
        base.specs = [
            ProductSpec(name=name, values=sorted(values))
            for name, values in merged_specs.items()
        ]

        return base