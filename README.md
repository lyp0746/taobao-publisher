# 🛍️ 淘宝商品 AI 智能发布软件

> 自动化商品发布 + AI 优化标题/详情/规格，解放运营双手

---

## ✨ 核心功能

| 功能 | 说明 |
|------|------|
| 📦 CSV 批量导入 | 支持 CSV / Excel 格式，自动识别编码 |
| 🤖 AI 内容优化 | 调用火山云/OpenAI 优化标题、详情、规格 |
| 🖼️ 图片分析 | AI 分析主图，辅助生成更精准的文案 |
| 🌐 浏览器自动化 | Playwright 模拟人工操作，自动填写表单 |
| 📤 批量发布 | 支持批量上架或保存草稿，可配置间隔 |
| 📋 实时日志 | 全程显示操作日志，掌握发布进度 |
| 🔒 资源管理 | 优化的内存管理，避免内存泄漏和闪退 |

---

## 🚀 快速开始

### 1. 安装 uv（如未安装）

```bash  
pip install uv  
# 或 Windows  
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  
```

### 2. 克隆并安装依赖

```bash  
git clone <repo_url>  
cd taobao-publisher  
uv sync  
```

### 3. 安装 Playwright 浏览器

```bash  
uv run playwright install chromium  
```

### 4. 配置 AI

```bash  
cp .env.example .env  
# 编辑 .env，填入 API Key  
```

### 5. 启动软件

```bash  
uv run taobao-publisher  
# 或  
uv run python -m taobao_publisher.main  
```

---

## 📋 CSV 数据包格式

| 列名 | 说明 | 示例 |
|------|------|------|
| 标题 | 商品标题（必填） | 夏季女士连衣裙 |
| 价格 | 售价（必填） | 89.00 |
| 分类 | 商品类目 | 服装>女装 |
| 库存 | 库存数量 | 100 |
| 主图 | 本地图片路径 | D:/imgs/main.jpg |
| 描述 | 商品详情 | 这款连衣裙... |
| spec_颜色 | 颜色规格 | 红色,蓝色,黑色 |
| spec_尺寸 | 尺寸规格 | S,M,L,XL |
| attr_品牌 | 品牌属性 | 自有品牌 |

---

## 🤖 AI 提供商配置

### 火山云（推荐）

1. 登录 [火山引擎控制台](https://console.volcengine.com/)
2. 进入「方舟」→「模型接入点」，创建接入点
3. 复制 `API Key` 和 `Endpoint ID`（即模型 ID，格式：`ep-xxx`）

```env  
AI_PROVIDER=volcano  
VOLCANO_API_KEY=your_key  
VOLCANO_MODEL=ep-xxxxxxxx-xxxxx  
```

### OpenAI

```env  
AI_PROVIDER=openai  
OPENAI_API_KEY=sk-xxx  
OPENAI_MODEL=gpt-4o  
```

---

## 📁 项目结构

```  
taobao-publisher/  
├── pyproject.toml          # 项目配置  
├── .env.example            # 环境变量模板  
├── config.json             # 运行时配置（自动生成）  
├── logs/                   # 日志目录（自动生成）  
├── assets/  
│   └── icon.ico  
└── src/  
    └── taobao_publisher/  
        ├── main.py         # 程序入口  
        ├── ui/             # 界面层  
        │   ├── main_window.py  
        │   ├── styles.py  
        │   └── frames/  
        │       ├── csv_frame.py  
        │       ├── ai_settings_frame.py  
        │       ├── publish_frame.py  
        │       └── log_frame.py  
        ├── core/           # 业务层  
        │   ├── browser_manager.py  
        │   ├── taobao_publisher.py  
        │   ├── csv_parser.py  
        │   └── ai_processor.py  
        └── utils/          # 工具层  
            ├── config.py  
            └── logger.py  
```

---

## ⚠️ 注意事项

1. **淘宝反爬**：软件已内置反检测措施，但仍建议设置合理的操作延迟（500ms+）
2. **登录安全**：每次使用需手动扫码/登录，软件不存储账号密码
3. **类目选择**：自动类目匹配可能不准确，建议先手动选好类目模板
4. **API 费用**：AI 调用会产生费用，请关注 API 用量
5. **草稿模式**：建议先用「保存草稿」模式测试，确认无误后再正式发布

---

## 🔧 常见问题

**Q: 浏览器启动失败？**  
A: 运行 `uv run playwright install chromium` 重新安装

**Q: AI 连接失败？**  
A: 检查 API Key 和 Base URL 是否正确，可在「AI设置」页面点击「测试连接」

**Q: CSV 中文乱码？**  
A: 软件支持自动检测编码，如仍有问题请将 CSV 另存为 UTF-8 编码

**Q: 发布时找不到输入框？**  
A: 淘宝页面结构可能因类目不同而有差异，可适当增大操作延迟

# 1. 创建项目并进入
mkdir taobao-publisher && cd taobao-publisher

# 2. 初始化 uv 项目（将上述文件按结构创建好后）
uv sync

# 3. 安装 Playwright 浏览器
uv run playwright install chromium

# 4. 复制并配置环境变量
cp .env.example .env
# 编辑 .env，填入火山云 API Key

# 5. 运行软件
uv run taobao-publisher