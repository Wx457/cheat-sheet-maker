# Cheat Sheet Maker 项目架构文档

## 📁 项目目录结构

```
cheat-sheet-maker/
│
├── backend/                          # 后端服务 (FastAPI)
│   ├── main.py                       # FastAPI 应用入口
│   ├── requirements.txt              # Python 依赖包
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
│   │   ├── services/                 # 业务逻辑层
│   │   │   ├── cleaner.py            # 文本清理服务
│   │   │   ├── embedding_service.py  # OpenAI Embedding 服务
│   │   │   ├── llm.py                # Gemini LLM 服务
│   │   │   ├── parser.py             # 解析服务
│   │   │   ├── pdf_service.py        # PDF 处理服务
│   │   │   ├── rag_service.py        # RAG 服务 (向量存储/检索)
│   │   │   └── storage.py            # MinIO/S3 存储服务
│   │   │
│   │   └── utils/                     # 工具函数
│   │       ├── __init__.py
│   │       └── html_generator.py     # HTML 生成器
│   │
│   ├── worker.py                     # ARQ Worker 进程 (独立运行)
│   ├── tipstxt/                      # 提示词文件
│   │   ├── bashOrder.txt
│   │   ├── cheat-sheet-maker.txt
│   │   ├── GPT_APIkey.txt
│   │   └── PromotionList.txt
│   │
│   └── venv/                         # Python 虚拟环境
│
├── frontend/                         # 前端应用 (React + TypeScript + Vite)
│   ├── package.json                  # Node.js 依赖
│   ├── vite.config.ts                # Vite 配置
│   ├── tsconfig.json                 # TypeScript 配置
│   │
│   ├── src/                          # 源代码目录
│   │   ├── main.tsx                  # React 应用入口
│   │   ├── App.tsx                   # 主应用组件
│   │   ├── App.css                   # 主样式文件
│   │   ├── index.css                 # 全局样式
│   │   │
│   │   ├── components/               # React 组件
│   │   │   ├── IngestPanel.tsx       # 内容摄入面板
│   │   │   ├── InputArea.tsx         # 输入区域组件
│   │   │   ├── Preview.tsx           # 预览组件
│   │   │   ├── PreviewPage.tsx       # 预览页面
│   │   │   ├── SetupForm.tsx         # 设置表单
│   │   │   └── TopicSelector.tsx     # 主题选择器
│   │   │
│   │   ├── types/                    # TypeScript 类型定义
│   │   │   └── index.ts
│   │   │
│   │   └── assets/                   # 静态资源
│   │       └── react.svg
│   │
│   └── public/                       # 公共静态文件
│       └── vite.svg
│
├── chrome-extension/                 # Chrome 浏览器插件
│   ├── manifest.json                 # 插件配置文件
│   ├── popup.html                    # 弹出窗口 HTML
│   ├── popup.js                      # 弹出窗口逻辑
│   ├── content.js                    # 内容脚本
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
│  │  (Gemini)    │  │ (Playwright) │  │ (MinIO/S3)   │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                          │
│  职责：从队列取任务 → 执行耗时操作 → 存储结果               │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                   数据存储层 (Data Layer)                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ MongoDB Atlas│  │ Vector Store │  │ MinIO/S3     │ │
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
[返回相关文档片段]
```

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
    ├──→ [RAG 上下文检索] (MongoDB Atlas Vector Search)
    │
    ▼
[LLM 生成内容] (Gemini API)
    │
    ▼
[保存到数据库] (MongoDB projects 集合，如果包含 metadata)
    │
    ▼
[生成 HTML] (html_generator.py)
    │
    ▼
[生成 PDF] (pdf_service.py + Playwright)
    │
    ▼
[上传到 MinIO] (storage.py)
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
- **对象存储**: MinIO (S3 兼容)
- **Embedding**: OpenAI `text-embedding-3-small` (1536维)
- **LLM**: Google Gemini 2.5 Flash
- **向量存储**: MongoDB Atlas Vector Search
- **PDF 处理**: Playwright (Headless Chrome) + PyPDF
- **文本处理**: LangChain
- **S3 客户端**: boto3

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
  - `search_context()` - 向量搜索
  - `clear_vector_data()` - 清理旧数据

### 3. LLM Service (`llm.py`)
- **功能**: Gemini LLM 服务
- **主要函数**:
  - `generate_outline()` - 生成大纲
  - `generate_cheat_sheet()` - 生成 Cheat Sheet

### 4. HTML Generator (`html_generator.py`)
- **功能**: 将 Cheat Sheet 数据转换为 HTML
- **主要函数**:
  - `generate_cheat_sheet_html()` - 生成完整 HTML
  - `clean_latex_content()` - 清洗和转换 LaTeX 公式（防止 XSS 注入）

### 5. Storage Service (`storage.py`)
- **功能**: MinIO/S3 对象存储服务
- **主要方法**:
  - `ensure_bucket()` - 检查并创建 Bucket
  - `upload_file()` - 上传文件到 MinIO，返回 file_key
  - `get_presigned_url()` - 生成预签名下载链接（1小时有效）

### 6. Worker 进程 (`worker.py`)
- **功能**: ARQ Worker，执行耗时任务
- **任务函数**:
  - `generate_outline_task` - 生成大纲
  - `generate_cheat_sheet_task` - 生成小抄（全流程：LLM → HTML → PDF → MinIO）
  - `generate_pdf_task` - 生成 PDF 并上传到 MinIO
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
- `AWS_ACCESS_KEY_ID` - MinIO/S3 访问密钥
- `AWS_SECRET_ACCESS_KEY` - MinIO/S3 秘密密钥
- `S3_BUCKET_NAME` - S3 Bucket 名称 (默认: `cheat-sheets`)
- `S3_ENDPOINT_URL` - MinIO/S3 端点 URL (默认: `http://localhost:9000`)

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
│  MongoDB    │   │  MinIO/S3   │ │  OpenAI API │
│  Atlas      │   │  (PDF存储)   │ │  Gemini API │
│             │   │             │ │             │
│ - 向量索引  │   │ - PDF文件   │ │ - LLM调用   │
│ - 项目数据  │   │ - 预签名URL │ │ - Embedding │
└─────────────┘   └─────────────┘ └─────────────┘
```

## 📝 关键文件说明

### 后端入口
- `backend/main.py` - FastAPI 应用启动入口，配置 CORS、路由和 ARQ 连接池
- `backend/app/worker.py` - ARQ Worker 进程入口（独立运行）

### 前端入口
- `frontend/src/main.tsx` - React 应用入口
- `frontend/src/App.tsx` - 主应用组件

### 配置文件
- `backend/app/core/config.py` - 应用配置管理（MongoDB、Redis、MinIO、API Keys）
- `backend/requirements.txt` - Python 依赖
- `frontend/package.json` - Node.js 依赖

### 启动方式
- **API Server**: `python main.py` 或 `uvicorn main:app`
- **Worker**: `arq app.worker.WorkerSettings` 或 `python -m app.worker`

## 🔄 版本信息

- **Embedding 模型**: OpenAI `text-embedding-3-small` (1536维)
- **LLM 模型**: Google Gemini 2.5 Flash
- **向量存储**: MongoDB Atlas Vector Search
- **任务队列**: ARQ 0.26.3
- **对象存储**: MinIO (S3 兼容)
- **FastAPI**: 0.128.0
- **React**: 18.3.1
- **TypeScript**: 5.9.3
- **boto3**: 1.35.0

## 🔧 架构特点

### 生产者-消费者模式
- **API Server (生产者)**: 接收 HTTP 请求，将任务推送到 Redis 队列，立即返回 `task_id`
- **Worker (消费者)**: 独立进程，从 Redis 队列消费任务，执行耗时操作（LLM、PDF、MinIO 上传）
- **优势**: 
  - API 响应速度快，不阻塞
  - 支持任务重试和并发控制
  - 易于横向扩展 Worker

### 异步任务流程
1. 客户端提交任务 → 获得 `task_id`
2. Worker 异步处理任务
3. 客户端轮询 `/api/task/{task_id}` 查询状态
4. 任务完成后，获得结果和预签名下载链接

### 文件存储
- PDF 文件存储在 MinIO 对象存储中
- 使用预签名 URL 提供临时访问（1小时有效）
- 文件按日期组织：`YYYYMMDD/{uuid}_{filename}.pdf`

---

*最后更新: 2025年*

