# 工作经历挖掘

> 英文仓库名建议：**work-experience-miner**  
> 把实习/项目经历从「做过什么」整理成**岗位听得懂、有证据、可量化**的简历表述。

面向**工科 / 管理学**等方向学生的**本地化**工具：录入多条工作经历，结合岗位知识库做检索增强（RAG），通过对话引导与改稿规范协助表达，并导出固定叙事模板（**发现问题 → 推进问题 → 解决问题 → 可量化成果**）。

**隐私默认在本机**：向量索引、就业参考与知识库 Markdown 本地读写；不配置大模型 API 时，可不向云端发送业务对话（首次运行会从 Hugging Face 拉取开源嵌入/重排模型，可事先缓存）。

---

## 目录

- [能解决什么问题](#能解决什么问题)
- [核心功能](#核心功能)
- [快速开始](#快速开始)
- [DeepSeek API（可选）](#deepseek-api可选)
- [工作原理](#工作原理)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [索引维护与常见问题](#索引维护与常见问题)
- [说明与边界](#说明与边界)

---

## 能解决什么问题

| 痛点 | 本工具的做法 |
|------|----------------|
| 经历像流水账，不知道岗位看重什么 | 按岗位方向从知识库检索**差异化评价指标、典型产出、常见证据** |
| 想写成果导向表述，但缺少结构 | 内置**对话引导**与**改稿规范**（System），导出固定 Markdown 骨架 |
| 担心简历/对话数据上云 | 默认本地 Streamlit + Chroma；仅在你配置并点击调用时走 DeepSeek API |
| PDF 简历难拆成多条经历 | 支持 PDF 抽字/OCR、去隐私、多段拆分并填入字段 |

---

## 核心功能

### 经历录入（左侧）

- 多条工作经历卡片（支持 ➕ / ➖）
- **上传 PDF**：自动抽字或 OCR、去隐私、按段拆分填入字段
- **粘贴原文**：可点「从描述识别并填入」抽取公司 / 岗位 / 时间（有 API 时优先用大模型，否则走规则）
- 侧栏：**API Key**、**对话历史**（会话快照与 trace 同 ID）；页头右上 **简历导入** / **导出**

### 查阅与检索（右侧）

- **就业参考**：`工科与管理学-实习就业岗位参考.md` 按标题分块阅读
- **RAG 面板**：展示查询改写、子查询、rerank 主查询串与命中条文；可下载拼好的 User 消息 `.txt`
- **可选对话**：配置 DeepSeek 后，在检索结果基础上进行经历挖掘与改稿（回复不会自动写入表单字段）

### 导出

- `export_template.py` 按固定 Markdown 模板导出，便于复制到 Word 或简历文档

---

## 快速开始

### 环境要求

- Python 3.10+（建议 3.10 或 3.11）
- 磁盘空间：首次检索约需数百 MB（句向量 + Cross-Encoder 模型缓存）

### 安装与启动

```bash
cd 项目根目录
pip install -r requirements.txt
python -m streamlit run app.py
```

浏览器打开终端提示的本地地址即可。首次使用请在侧栏点击 **「构建 / 重建向量索引」**。

### 首次运行会下载的模型

| 用途 | 模型 ID |
|------|---------|
| 句向量（双塔召回） | `paraphrase-multilingual-MiniLM-L12-v2` |
| 精排（Cross-Encoder） | `cross-encoder/ms-marco-multilingual-MiniLM-L12-v2` |

下载一次后由 Hugging Face 缓存在本机。若需**完全离线**，请先在有网环境完成一次检索或建索引，再断网使用。

### PDF / OCR

**默认：PaddleOCR**

1. 先安装 **paddlepaddle**（CPU 版即可）：<https://www.paddlepaddle.org.cn/install/quick>
2. 再执行 `pip install -r requirements.txt`（含 `paddleocr`）。首次 OCR 会下载 Paddle 模型。

**可选回退：Tesseract**

1. 安装 [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) 并加入 `PATH`，建议语言包 **chi_sim**
2. 设置环境变量 `OCR_ENGINE=tesseract`（或在 `.env` 中配置）

逻辑说明：优先读取 PDF 文本层；文本不足时对页面截图做 OCR（默认 Paddle，可切 Tesseract）。

---

## DeepSeek API（可选）

通过 **OpenAI 官方 Python SDK**（`openai` 包）调用 DeepSeek **Chat Completions** 兼容接口，用于：对话式经历挖掘、改稿，以及「从描述识别」等能力增强。

### 配置

推荐复制示例文件后填写密钥：

```powershell
copy .env.example .env
# 编辑 .env：填入 DEEPSEEK_API_KEY；可按需修改 DEEPSEEK_MODEL、OCR_ENGINE 等
```

或在启动前临时设置（PowerShell）：

```powershell
$env:DEEPSEEK_API_KEY = "你的密钥"
$env:DEEPSEEK_MODEL = "deepseek-v4-flash"   # 亦可 deepseek-v4-pro 等，以官方文档为准
python -m streamlit run app.py
```

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | DeepSeek 开放平台 API Key；未配置时无法调用大模型对话 |
| `DEEPSEEK_API_BASE` | 可选，默认 `https://api.deepseek.com` |
| `DEEPSEEK_MODEL` | 可选，默认 `deepseek-v4-flash` |
| `OCR_ENGINE` | 可选，`paddle`（默认）或 `tesseract` |

`.env` 须与 `app.py` 同处**项目根目录**。应用启动时会用 `python-dotenv` 加载；页面会提示是否检测到密钥。

> **上传 PDF 自动拆分/填字段**强烈建议配置 `DEEPSEEK_API_KEY`，识别与分段效果更好。

### 推荐使用流程

1. 在左侧录入或导入经历，在对话中描述本轮事实（**用户原话**会优先参与检索改写）。
2. 在 **RAG** 区域执行「检索」，生成带知识条文的 User 拼装内容。
3. 点击 **「调用 DeepSeek 生成回复」**：System = 对话引导 + 改稿规范；User = 你的回答 + RAG 条文。
4. 核对模型回复后，自行填入经历字段或导出模板。

**隐私提示**：配置密钥并点击调用后，对话与拼装内容会发往 **DeepSeek 服务器**。若仅希望本地处理，请勿配置密钥，也不要点击调用按钮。

### 本地对话 trace（可选）

可在 `.env` 中开启（见 `.env.example`）：

- `CHAT_TRACE_ENABLED`：写入 `local_chat_traces/trace_<会话ID>.json`（含完整 system、多轮上下文、经历原文）
- 对话历史 JSON 默认目录：`local_chat_histories/`（已在 `.gitignore` 中排除，勿提交仓库）

---

## 工作原理

### 知识分工

| 类型 | 文件示例 | 用途 |
|------|-----------|------|
| **System（不入向量库）** | `经历挖掘-对话引导.md`、`经历表达-模板与改稿规范.md` | 控制「怎么问、怎么改稿」；由 `rag/dialogue_guide.py` 按序拼接 |
| **RAG 语料** | `01-软件开发与交付.md`、`02-数据-算法-AI.md`、`03-质量保障与基础设施.md`、`07-人力与会计学.md` 等 | 行业**特殊评价指标**、典型产出、证据表述；按 `###`（否则 `##`）切块入库 |
| **就业参考（非 RAG）** | `工科与管理学-实习就业岗位参考.md` | 粗粒度岗位方向阅读，不参与向量检索 |

索引**刻意排除**对话引导、改稿规范与本 README，避免与行业条文混检。

### 检索管道

```text
用户原话 user_answer（优先）
        ↓
   查询改写（多路子查询；可合并补充关键词 / 岗位 / 经历摘要）
        ↓
   各子查询 → 双塔向量检索（Chroma，余弦相似度）
        ↓
   RRF 融合 → 宽召回候选池
        ↓
   Cross-Encoder 精排（主查询 ≈ 用户原话 + 岗位 + 改写主句 + 专业尾缀）
        ↓
   Top-K 条文 → 写入 User 消息，供大模型引用
```

### 界面布局（Streamlit）

- **侧栏**：API Key、对话历史（随侧栏整体滚动）
- **主区**：经历卡片、对话；页头右上简历导入与导出

---

## 技术栈

| 层级 | 选型 | 说明 |
|------|------|------|
| 界面 | Streamlit | 双栏布局；`.streamlit/config.toml` 可调整主题等 |
| 就业参考 | Markdown + 分章节解析 | `knowledge.py` 按标题切块展示 |
| 知识库分块 | Markdown | `rag/chunking.py`；`load_rag_chunks` 排除 System 类文档 |
| 向量库 | Chroma（持久化目录 `.chroma_job_kb/`） | 集合名 `job_kb_v2` |
| 嵌入 | Sentence-Transformers 双塔 | 多语言 MiniLM |
| 查询扩展 | 规则/模板多查询 | 优先 `user_answer`，结合岗位、公司、方向、摘要 |
| 融合 | RRF（倒数排名融合） | 多路子查询结果合并 |
| 精排 | Cross-Encoder | MS MARCO 多语言 MiniLM 系 |
| 大模型 | DeepSeek（OpenAI 兼容） | `deepseek_api.py`；密钥仅环境变量 / `.env` |
| PDF | PyMuPDF + PaddleOCR | 可回退 Tesseract |

---

## 项目结构

```text
工作经历挖掘/
├── app.py                          # Streamlit 入口
├── knowledge.py                    # 就业参考 Markdown 分块展示
├── resume_pipeline.py              # PDF 提取、OCR、去噪、多段拆分
├── paddle_ocr_util.py              # PaddleOCR 封装
├── experience_extract.py           # 经历字段抽取（规则 / API）
├── export_template.py              # 固定叙事模板导出
├── deepseek_api.py                 # DeepSeek 调用封装
├── chat_history.py / chat_trace.py # 对话历史与 trace
├── .env.example                    # 环境变量示例（复制为 .env，勿提交）
├── requirements.txt
├── 工科与管理学-实习就业岗位参考.md
├── rag/
│   ├── chunking.py                 # 分块与 RAG 语料加载
│   ├── dialogue_guide.py           # System / User 消息拼装
│   ├── query_rewrite.py            # 查询改写
│   ├── embed_store.py              # 编码与 Chroma
│   ├── rerank.py                   # Cross-Encoder 重排
│   └── retrieve.py                 # RRF + rerank 编排
├── 工作岗位知识库/
│   ├── 00-通用底座与条目模板.md
│   ├── 01-软件开发与交付.md        # RAG 语料（另含 02、03、07）
│   ├── 经历挖掘-对话引导.md        # → System only
│   └── 经历表达-模板与改稿规范.md  # → System only
├── .chroma_job_kb/                 # 本地向量库（建索引后生成，已 gitignore）
├── local_chat_traces/              # 可选 trace（已 gitignore）
└── local_chat_histories/           # 对话历史 JSON（已 gitignore）
```

---

## 索引维护与常见问题

- 修改 `工作岗位知识库/` 下参与 RAG 的 Markdown 后，请在侧栏 **「构建 / 重建向量索引」**。
- 索引条数**少于**「目录下所有 md 文件总数」是预期行为：对话引导、改稿规范、README 等不参与向量库。
- 若报错 Chroma「Collection … does not exist」：多为重建索引时客户端实例不一致。当前版本会在同一缓存实例上重建；仍异常时可退出 Streamlit，删除 `.chroma_job_kb/` 后重新建索引。

---

## 说明与边界

- RAG 用于对齐**岗位特殊评价维度与证据表述**，**不替代**用人单位或面试官的最终判断。
- 模板与引导要求**不虚构指标**；缺少数据处应标注「待补充」。
- 向 GitHub 等平台推送代码前，请确认 `.env`、`local_chat_traces/`、`local_chat_histories/`、`.chroma_job_kb/` 未被提交（见 `.gitignore`）。

---

## 许可证

尚未在仓库中声明开源许可证；若你计划公开仓库，请自行添加 `LICENSE` 文件并在此注明。
