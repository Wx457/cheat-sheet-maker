# Cheat Sheet Maker 项目架构文档

## 📁 项目目录结构

```
cheat-sheet-maker/
│
├── backend/                          # 后端服务 (FastAPI)
│   ├── main.py                       # FastAPI 应用入口
│   │   ├── lifespan()                # 启停时创建/关闭 ARQ Redis 连接池
│   │   ├── setup_mongodb_ttl_indexes # 创建 MongoDB TTL 索引（projects/vectors）
│   │   └── health()                  # 健康检查
│   ├── requirements.txt              # Python 依赖包
│   ├── Dockerfile                    # 后端 Docker 镜像构建文件
│   │
│   ├── app/                          # 应用主目录
│   │   ├── __init__.py
│   │   │
│   │   ├── api/                      # API 路由层
│   │   │   ├── __init__.py
│   │   │   ├── generate.py           # 生成 Cheat Sheet 的 API (异步任务模式)
│   │   │   ├── plugin.py             # Chrome 插件相关 API (异步任务模式)
│   │   │   ├── rag.py                # RAG 知识库 API (摄入/搜索/清理)
│   │   │   └── task.py               # 任务状态查询 API
│   │   │
│   │   ├── core/                     # 核心配置
│   │   │   ├── __init__.py
│   │   │   └── config.py             # 应用配置 (MongoDB, API Keys)
│   │   │
│   │   ├── schemas/                  # 数据模型定义
│   │   │   ├── __init__.py
│   │   │   └── cheat_sheet.py        # Cheat Sheet 相关 Schema
│   │   │
│   │   ├── application/services/     # 用例级编排层（Application Layer）
│   │   │   ├── __init__.py
│   │   │   ├── ingestion_service.py
│   │   │   └── cheat_sheet_service.py
│   │   │
│   │   ├── domain/                   # 纯业务规则与提示（Domain Layer）
│   │   │   ├── rules/
│   │   │   │   └── budget.py
│   │   │   ├── prompts/
│   │   │   │   └── templates.py
│   │   │   └── utils/
│   │   │       ├── cleaner.py
│   │   │       └── math_formatter.py
│   │   │
│   │   ├── infrastructure/           # 底层客户端（Infrastructure Layer）
│   │   │   ├── llm/
│   │   │   │   ├── gemini_client.py
│   │   │   │   └── openai_client.py
│   │   │   ├── pdf/
│   │   │   │   └── renderer.py  # Playwright 渲染前端页面生成 PDF（使用 PDF_GENERATION_HOST 配置）
│   │   │   ├── rag/
│   │   │   │   └── vector_store.py
│   │   │   └── storage/
│   │   │       └── minio_client.py  # AWS S3 客户端封装（类名保持 MinIOClient 以保持兼容性）
│   │   │
│   │   └── worker.py                 # ARQ Worker 任务定义
│   │
│   ├── static/                       # 前端构建产物与 demo HTML（由 npm run deploy 生成）
│   │   ├── index.html                # 首页展示页（纯静态 HTML）
│   │   ├── render.html               # React 渲染器入口（供 Playwright 生成 PDF 使用）
│   │   ├── vite.svg
│   │   └── assets/                   # Vite 构建出的 js/css/font 等静态资源
│   ├── tipstxt/                      # 提示词文件
│   │   ├── bashOrder.txt
│   │   ├── cheat-sheet-maker.txt
│   │   ├── GPT_APIkey.txt
│   │   └── PromotionList.txt
│
├── frontend/                         # 前端应用 (React + TypeScript + Vite)
│   ├── package.json                  # Node.js 依赖与脚本
│   ├── package-lock.json             # 锁定依赖版本
│   ├── vite.config.ts                # Vite 配置
│   ├── eslint.config.js              # ESLint 配置
│   ├── tsconfig.json                 # TypeScript 基础配置
│   ├── tsconfig.app.json             # 应用构建 tsconfig
│   ├── tsconfig.node.json            # Node/Vite 相关 tsconfig
│   ├── index.html                    # 首页展示页（纯静态 HTML + Tailwind）
│   ├── render.html                   # React 渲染器入口（含 <div id="root"> 和 /src/main.tsx）
│   │
│   ├── src/                          # 源代码目录
│   │   ├── main.tsx                  # React 应用入口
│   │   ├── App.css                   # 主样式文件
│   │   ├── index.css                 # 全局样式
│   │   │
│   │   ├── components/               # 复用组件
│   │   │   └── Preview.tsx           # 预览组件（承载小抄内容）
│   │   │
│   │   ├── pages/                    # 页面级组件
│   │   │   └── PrintPage.tsx         # 打印 / 导出 页面
│   │   │
│   │   ├── types/                    # TypeScript 类型定义
│   │   │   └── index.ts
│   │   │
│   │   └── assets/                   # 静态资源
│   │       └── react.svg
│   │
│   ├── public/                       # 公共静态文件（开发/构建时拷贝）
│   │   └── vite.svg
│   │
│   └── dist/                         # 前端构建输出目录（由 npm run build/deploy 生成）
│       ├── index.html                # 打包后的首页展示页
│       ├── render.html               # 打包后的 React 渲染器入口
│       ├── vite.svg
│       └── assets/                   # 生产环境 js/css/font 等资源
│
├── chrome-extension/                 # Chrome 浏览器插件
│   ├── manifest.json                 # 插件配置文件
│   ├── background.js                 # 背景脚本（处理长连接、消息转发）
│   ├── content.js                    # 内容脚本（抓取网页内容）
│   ├── popup.html                    # 弹出窗口 HTML
│   ├── popup.js                      # 弹出窗口逻辑
│   ├── formPersistence.js            # 表单数据持久化逻辑
│   ├── icon16.png                    # 图标 (16x16)
│   ├── icon48.png                    # 图标 (48x48)
│   ├── icon120.png                   # 图标 (120x120)
│   └── README.md                     # 插件说明文档
│
└── docker-compose.yml                # Docker 编排配置
```

## 🏗️ 系统架构

### 生产者-消费者架构模式 (Producer-Consumer)

```
┌─────────────────────────────────────────────────────────┐
│                     前端层 (Frontend)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ React + TS   │  │ Chrome插件   │  │ 用户界面     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │ HTTP/REST API
                          ▼
┌─────────────────────────────────────────────────────────┐
│              API Server (生产者/Producer)                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ generate │  │   rag    │  │  plugin  │  │  task   │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │
│                                                          │
│  职责：接收请求 → 推送到 ARQ 队列 → 立即返回 task_id      │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼ 推送任务
┌─────────────────────────────────────────────────────────┐
│                  Redis 队列 (ARQ)                         │
│                  任务队列管理                             │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼ 消费任务
┌─────────────────────────────────────────────────────────┐
│              Worker 进程 (消费者/Consumer)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  LLM Service │  │ PDF Service  │  │ Storage      │ │
│  │  (Gemini)    │  │ (Playwright) │  │ (AWS S3)     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                          │
│  职责：从队列取任务 → 执行耗时操作 → 存储结果               │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                   数据存储层 (Data Layer)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ MongoDB Atlas│  │ Vector Store │  │ AWS S3       │ │
│  │ (文档存储)    │  │ (1536维向量) │  │ (PDF 文件)   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## 🔌 API 端点架构

### 1. 生成 API (`/api/generate`) - 异步任务模式
- **路由**: `generate_router`
- **功能**: 生成 Cheat Sheet（异步任务）
- **主要端点**:
  - `POST /api/outline` - 生成大纲（返回 task_id）
  - `POST /api/generate` - 生成 Cheat Sheet（返回 task_id）

### 2. RAG API (`/api/rag`)
- **路由**: `rag_router`
- **功能**: RAG 知识库管理（同步）
- **主要端点**:
  - `POST /api/rag/ingest` - 文本摄入
  - `POST /api/rag/ingest/file` - PDF 文件摄入
  - `POST /api/rag/search` - 向量搜索
  - `POST /api/rag/clear` - 清理旧向量数据

### 3. 插件 API (`/api/plugin`) - 异步任务模式
- **路由**: `plugin_router`
- **功能**: Chrome 插件集成
- **主要端点**:
  - `POST /api/plugin/analyze` - 分析网页内容（返回 task_id）
  - `POST /api/plugin/generate-final` - 生成最终 Cheat Sheet（返回 task_id）
  - `GET /api/plugin/project/{project_id}` - 获取项目数据
  - `GET /api/plugin/download-cheat-sheet/{project_id}` - 下载 PDF

### 4. 任务状态查询 API (`/api/task`)
- **路由**: `task_router`
- **功能**: 查询异步任务状态和结果
- **主要端点**:
  - `GET /api/task/{task_id}` - 查询任务状态（返回状态、结果、download_url）

## 🔄 数据流

### 文本摄入流程
```
用户输入/PDF文件
    │
    ▼
[文本清理] (cleaner.py)
    │
    ▼
[文本分割] (RecursiveCharacterTextSplitter)
    │
    ▼
[生成向量] (OpenAI Embedding API)
    │
    ▼
[存储到 MongoDB] (MongoDBAtlasVectorSearch)
```

### 搜索流程

#### 相似度搜索（用于 Outline 生成等场景）
```
用户查询
    │
    ▼
[生成查询向量] (OpenAI Embedding API)
    │
    ▼
[向量相似度搜索] (MongoDB Atlas Vector Search)
    │
    ▼
[返回相关文档片段] (包含相似度分数)
```

#### MMR 检索（用于 Cheat Sheet 生成）
```
用户查询
    │
    ▼
[生成查询向量] (OpenAI Embedding API)
    │
    ▼
[MMR 检索] (最大边界相关算法)
    │    ├──→ 获取 fetch_k 个候选文档
    │    └──→ 选择 k 个最相关且多样化的文档
    │
    ▼
[内容去重] (使用 hash 指纹)
    │
    ▼
[返回去重后的文档片段]
```

**注意**: 
- 当有多个主题时，系统使用 `asyncio.gather` 并行执行所有主题的搜索，显著提升性能
- Cheat Sheet 生成使用 MMR 检索 + 去重，减少冗余内容，降低上下文长度

### 生成 Cheat Sheet 流程（异步任务模式）
```
用户请求
    │
    ▼
[API Server 接收] → 推送任务到 ARQ 队列 → 立即返回 task_id
    │
    ▼
[Worker 进程消费任务]
    │
    ├──→ [RAG 上下文检索] (并行 MMR 检索 + 去重)
    │    ├──→ 并行执行所有主题的 MMR 检索 (asyncio.gather)
    │    ├──→ MongoDB Atlas Vector Search (MMR 算法)
    │    └──→ 内容去重 (hash 指纹)
    │
    ▼
[LLM 生成内容] (Gemini API)
    │
    ▼
[保存到数据库] (MongoDB projects 集合，如果包含 metadata)
    │
    ▼
[清洗数据] (清洗公式格式)
    │
    ▼
[生成 PDF] (renderer.py + Playwright)
    │    └──→ 访问 {PDF_GENERATION_HOST}/static/render.html#/print
    │
    ▼
[上传到 AWS S3] (minio_client.py)
    │
    ▼
[返回结果] {file_key, project_id, ...}
    │
    ▼
[客户端轮询 /api/task/{task_id}]
    │
    ▼
[获取预签名下载链接] (download_url)
```

## 🛠️ 技术栈

### 后端
- **框架**: FastAPI
- **语言**: Python 3.10+
- **任务队列**: ARQ (Async Redis Queue)
- **消息队列**: Redis
- **数据库**: MongoDB Atlas (向量搜索 + 文档存储)
- **对象存储**: AWS S3
- **Embedding**: OpenAI `text-embedding-3-small` (1536维)
- **LLM**: Google Gemini 2.5 Flash
- **向量存储**: MongoDB Atlas Vector Search
- **检索算法**: 
  - 相似度搜索 (Similarity Search) - 用于 Outline 生成
  - MMR (Maximal Marginal Relevance) - 用于 Cheat Sheet 生成，减少冗余
- **PDF 处理**: Playwright (Headless Chrome) + PyPDF
- **文本处理**: LangChain
- **S3 客户端**: boto3
- **异步并发**: asyncio (用于并行 RAG 检索)

### 前端
- **框架**: React 18.3
- **语言**: TypeScript 5.9
- **构建工具**: Vite 7.2
- **路由**: React Router DOM 7.11
- **数学公式**: KaTeX + react-latex-next
- **HTTP 客户端**: Axios

### Chrome 插件
- **Manifest**: Version 3
- **权限**: activeTab, scripting
- **功能**: 网页内容抓取与发送

## 📦 核心模块说明

### 1. Embedding Service (`embedding_service.py`)
- **功能**: OpenAI Embedding 服务封装
- **主要函数**:
  - `get_embedding(text: str) -> list[float]` - 单个文本向量化
  - `get_embeddings(texts: list[str]) -> list[list[float]]` - 批量向量化
  - `compute_similarity(vec1, vec2) -> float` - 余弦相似度计算
- **类**:
  - `OpenAIEmbeddings` - LangChain Embeddings 适配器

### 2. RAG Service (`rag_service.py`)
- **功能**: RAG 知识库管理
- **主要方法**:
  - `ingest_text()` - 文本摄入
  - `ingest_pdf()` - PDF 摄入
  - `search_context()` - 向量搜索（相似度搜索，返回 score）
  - `search_context_mmr()` - MMR 检索（最大边界相关算法，减少冗余）
  - `clear_vector_data()` - 清理旧数据
- **检索策略**:
  - **相似度搜索** (`search_context`): 返回最相关的 k 个结果，包含相似度分数
  - **MMR 检索** (`search_context_mmr`): 在保证相关性的同时最大化多样性，减少冗余内容
    - 参数: `k=3`（最终结果数），`fetch_k=10`（初始候选集）
    - 返回格式: 与 `search_context` 兼容（`score` 固定为 0.0 以保持向后兼容）

### 3. LLM Service (`llm.py`)
- **功能**: Gemini LLM 服务
- **主要函数**:
  - `generate_outline()` - 生成大纲
  - `generate_cheat_sheet()` - 生成 Cheat Sheet
- **性能优化**:
  - **并行 MMR 检索**: 使用 `asyncio.gather` 并行执行多个主题的 MMR 检索，而非顺序串行
    - 每个主题使用 `search_context_mmr(k=3, fetch_k=10)` 进行检索
    - 性能提升: N 个主题时，检索耗时从 N × T 降低到 ≈ T（T 为单个搜索耗时）
  - **内容去重**: 使用内容 hash 值作为指纹，避免重复内容传入 LLM
    - 实现: 使用 `set` 存储已见过的内容 hash，跳过重复内容
    - 效果: 减少上下文长度，降低 LLM token 消耗

### 4. HTML Generator (`html_generator.py`)
- **功能**: 将 Cheat Sheet 数据转换为 HTML
- **主要函数**:
  - `generate_cheat_sheet_html()` - 生成完整 HTML
  - `clean_latex_content()` - 清洗和转换 LaTeX 公式（防止 XSS 注入）

### 5. Storage Service (`minio_client.py`)
- **功能**: AWS S3 对象存储服务（类名保持 MinIOClient 以保持兼容性）
- **主要方法**:
  - `ensure_bucket()` - 检查并创建 Bucket（根据 AWS_REGION 自动处理 LocationConstraint）
  - `upload_file()` - 上传文件到 AWS S3，返回 file_key
  - `get_presigned_url()` - 生成预签名下载链接（1小时有效）

### 6. Worker 进程 (`worker.py`)
- **功能**: ARQ Worker，执行耗时任务
- **任务函数**:
  - `generate_outline_task` - 生成大纲
  - `generate_cheat_sheet_task` - 生成小抄（全流程：LLM → HTML → PDF → AWS S3）
  - `generate_pdf_task` - 生成 PDF 并上传到 AWS S3（已弃用，统一使用 create_cheat_sheet_flow）
- **启动方式**: `arq app.worker.WorkerSettings`

## 🔐 配置管理

### 环境变量 (`.env`)
- `MONGODB_URI` - MongoDB 连接字符串
- `DB_NAME` - 数据库名称 (默认: `cheat_sheet_db`)
- `COLLECTION_NAME` - 集合名称 (默认: `knowledge_base`)
- `GOOGLE_API_KEY` - Google Gemini API Key
- `OPENAI_API_KEY` - OpenAI API Key
- `REDIS_HOST` - Redis 主机 (默认: `localhost`)
- `REDIS_PORT` - Redis 端口 (默认: `6379`)
- `REDIS_DB` - Redis 数据库编号 (默认: `0`)
- `REDIS_PASSWORD` - Redis 密码 (可选)
- `AWS_ACCESS_KEY_ID` - AWS S3 访问密钥
- `AWS_SECRET_ACCESS_KEY` - AWS S3 秘密密钥
- `AWS_REGION` - AWS 区域 (默认: `us-east-1`，建议设置为实际使用的区域如 `us-east-2`)
- `S3_BUCKET_NAME` - S3 Bucket 名称 (默认: `cheat-sheets`)
- `PDF_GENERATION_HOST` - PDF 生成服务地址 (默认: `http://localhost:8000`，Worker 进程访问 FastAPI 服务器的地址)

## 🚀 部署架构

```
┌─────────────┐
│  用户浏览器  │
│  (Chrome)   │
└──────┬──────┘
       │
       ├─────────────────┐
       │                 │
       ▼                 ▼
┌─────────────┐   ┌─────────────┐
│  Frontend   │   │Chrome Plugin│
│  (React)    │   │             │
└──────┬──────┘   └──────┬───────┘
       │                │
       └────────┬───────┘
                │ HTTP/REST
                ▼
         ┌──────────────┐
         │  API Server  │
         │  (FastAPI)   │
         └──────┬───────┘
                │
                │ ARQ 任务队列
                ▼
         ┌──────────────┐
         │    Redis     │
         │  (消息队列)   │
         └──────┬───────┘
                │
                │ 消费任务
                ▼
         ┌──────────────┐
         │Worker 进程   │
         │  (ARQ)       │
         └──────┬───────┘
                │
       ┌────────┴────────┬──────────┐
       │                 │          │
       ▼                 ▼          ▼
┌─────────────┐   ┌─────────────┐ ┌─────────────┐
│  MongoDB    │   │  AWS S3     │ │  OpenAI API │
│  Atlas      │   │  (PDF存储)   │ │  Gemini API │
│             │   │             │ │             │
│ - 向量索引  │   │ - PDF文件   │ │ - LLM调用   │
│ - 项目数据  │   │ - 预签名URL │ │ - Embedding │
└─────────────┘   └─────────────┘ └─────────────┘
```

## 📝 关键文件说明

### 后端入口
- `backend/main.py` - FastAPI 应用启动入口，配置 CORS、路由、ARQ 连接池与静态资源挂载
  - 挂载目录：`backend/static`（由前端构建产物填充）
  - 访问路径：`/static`（HTML） 与 `/assets`（JS/CSS 等资源）
- `backend/app/worker.py` - ARQ Worker 进程入口（独立运行）

### 前端入口
- `frontend/src/main.tsx` - React 应用入口
- `frontend/src/App.tsx` - 主应用组件

### 配置文件
- `backend/app/core/config.py` - 应用配置管理（MongoDB、Redis、AWS S3、PDF 生成、API Keys）
- `backend/requirements.txt` - Python 依赖
- `frontend/package.json` - Node.js 依赖与构建/部署脚本
  - `npm run deploy`：构建前端 → 将 `dist/*` 拷贝到 `backend/static/`，供 FastAPI 静态服务与 PDF 渲染使用

### 启动方式
- **API Server**: `python main.py` 或 `uvicorn main:app`
- **Worker**: `arq app.worker.WorkerSettings` 或 `python -m app.worker`

## 🔄 版本信息

- **Embedding 模型**: OpenAI `text-embedding-3-small` (1536维)
- **LLM 模型**: Google Gemini 2.5 Flash
- **向量存储**: MongoDB Atlas Vector Search
- **任务队列**: ARQ 0.26.3
- **对象存储**: AWS S3
- **FastAPI**: 0.128.0
- **React**: 18.3.1
- **TypeScript**: 5.9.3
- **boto3**: 1.35.0

## 🔧 架构特点

### 生产者-消费者模式
- **API Server (生产者)**: 接收 HTTP 请求，将任务推送到 Redis 队列，立即返回 `task_id`
- **Worker (消费者)**: 独立进程，从 Redis 队列消费任务，执行耗时操作（LLM、PDF、AWS S3 上传）
- **优势**: 
  - API 响应速度快，不阻塞
  - 支持任务重试和并发控制
  - 易于横向扩展 Worker

### 异步任务流程
1. 客户端提交任务 → 获得 `task_id`
2. Worker 异步处理任务
3. 客户端轮询 `/api/task/{task_id}` 查询状态
4. 任务完成后，获得结果和预签名下载链接

### 并行处理优化
- **并行 MMR 检索**: 多个主题的向量搜索使用 `asyncio.gather` 并行执行
- **MMR 算法**: 使用最大边界相关算法，在保证相关性的同时最大化多样性，减少冗余内容
- **内容去重**: 使用内容 hash 指纹避免重复内容传入 LLM
- **性能提升**: 
  - 并行执行：显著减少多主题场景下的检索耗时
  - MMR 优化：减少上下文长度，降低 LLM token 消耗
  - 去重逻辑：进一步减少冗余，提升生成质量
- **实现位置**: `backend/app/services/llm.py` - `generate_cheat_sheet()` 函数

### 文件存储
- PDF 文件存储在 AWS S3 对象存储中
- 使用预签名 URL 提供临时访问（1小时有效）
- 文件按日期组织：`YYYYMMDD/{uuid}_{filename}.pdf`
- Bucket 创建时根据 `AWS_REGION` 自动设置 LocationConstraint（`us-east-1` 除外）

### PDF 生成配置
- Worker 进程使用 Playwright 访问前端渲染页面生成 PDF
- 通过 `PDF_GENERATION_HOST` 环境变量配置 FastAPI 服务器地址
- 默认访问路径：`{PDF_GENERATION_HOST}/static/render.html#/print`
- 部署时需确保 Worker 进程能够访问到 FastAPI 服务器（Docker 环境建议使用服务名）

## ⚡ 性能优化与监控

### 性能优化策略

#### 1. 并行 MMR 检索 + 去重
- **位置**: `backend/app/services/llm.py` - `generate_cheat_sheet()` 函数
- **优化前**: 顺序串行检索（Sequential Serial Retrieval）
  - 每个主题依次等待前一个完成
  - 总耗时 = N × T（N 个主题，每个耗时 T）
  - 使用相似度搜索，可能返回重复内容
- **优化后**: 并行 MMR 检索 + 去重
  - **并行执行**: 所有主题同时检索（使用 `asyncio.gather`）
  - **MMR 算法**: 使用 `search_context_mmr(k=3, fetch_k=10)` 减少冗余
  - **内容去重**: 使用内容 hash 指纹避免重复内容
  - 总耗时 ≈ T（最慢的单个搜索耗时）
- **性能提升**: 
  - **速度**: 理论上可提升 N 倍（N 为主题数量）
  - **质量**: MMR 减少冗余，去重进一步优化
  - **成本**: 减少上下文长度，降低 LLM token 消耗
- **示例**: 5 个主题，每个搜索 0.5 秒
  - 优化前: 5 × 0.5 = 2.5 秒，可能包含重复内容
  - 优化后: ≈ 0.5 秒（提升约 5 倍），内容更精简、多样化

#### 2. 性能监控系统
- **功能**: 全流程性能监控，记录各步骤耗时
- **实现**: 使用醒目标记 `[性能监控 - 可删除]` 包裹所有监控代码
- **监控范围**:
  - **Worker 任务**: `generate_outline_task`, `generate_cheat_sheet_task`, `generate_pdf_task`
  - **LLM 服务**: API 调用、JSON 解析、并行 MMR 检索耗时
  - **RAG 服务**: 文本切分、向量化、相似度搜索、MMR 搜索耗时
  - **PDF 服务**: 浏览器启动、页面导航、渲染、PDF 生成耗时
  - **存储服务**: 文件上传、预签名 URL 生成耗时
  - **API 端点**: 各 API 的总耗时和步骤耗时
- **输出格式**: `⏱️ [性能监控] <步骤名称> 耗时: X.XX 秒`
- **维护**: 所有监控代码使用统一标记，便于后续批量删除

---

*最后更新: 2026年1月*

## 📋 环境变量配置清单

### 必需配置
- `MONGODB_URI` - MongoDB 连接字符串
- `GOOGLE_API_KEY` - Google Gemini API Key
- `OPENAI_API_KEY` - OpenAI API Key（用于 Embedding）

### AWS S3 配置
- `AWS_ACCESS_KEY_ID` - AWS S3 访问密钥
- `AWS_SECRET_ACCESS_KEY` - AWS S3 秘密密钥
- `AWS_REGION` - AWS 区域（如 `us-east-2`）
- `S3_BUCKET_NAME` - S3 Bucket 名称（默认: `cheat-sheets`）

### PDF 生成配置
- `PDF_GENERATION_HOST` - Worker 进程访问 FastAPI 服务器的地址
  - 本地开发: `http://localhost:8000`
  - Docker Compose: `http://backend:8000`（使用服务名）
  - 其他环境: 根据实际网络配置

### 可选配置
- `DB_NAME` - 数据库名称（默认: `cheat_sheet_db`）
- `COLLECTION_NAME` - 集合名称（默认: `knowledge_base`）
- `REDIS_HOST` - Redis 主机（默认: `localhost`）
- `REDIS_PORT` - Redis 端口（默认: `6379`）
- `REDIS_DB` - Redis 数据库编号（默认: `0`）
- `REDIS_PASSWORD` - Redis 密码（可选）

