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
│   │   │   ├── generate.py           # 生成 Cheat Sheet 的 API
│   │   │   ├── plugin.py             # Chrome 插件相关 API
│   │   │   └── rag.py                # RAG 知识库 API (摄入/搜索/清理)
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
│   │   │   └── rag_service.py        # RAG 服务 (向量存储/检索)
│   │   │
│   │   └── utils/                     # 工具函数
│   │       ├── __init__.py
│   │       └── html_generator.py     # HTML 生成器
│   │
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

### 三层架构模式

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
│                    API 路由层 (API Layer)                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ generate │  │   rag    │  │  plugin  │              │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                  业务逻辑层 (Service Layer)                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  LLM Service │  │ RAG Service  │  │ Embedding    │ │
│  │  (Gemini)    │  │ (MongoDB)    │  │ (OpenAI)     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ PDF Service  │  │  Parser      │  │  Cleaner     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                   数据存储层 (Data Layer)                  │
│  ┌──────────────┐  ┌──────────────┐                    │
│  │ MongoDB Atlas│  │ Vector Store │                    │
│  │ (文档存储)    │  │ (1536维向量) │                    │
│  └──────────────┘  └──────────────┘                    │
└─────────────────────────────────────────────────────────┘
```

## 🔌 API 端点架构

### 1. 生成 API (`/api/generate`)
- **路由**: `generate_router`
- **功能**: 生成 Cheat Sheet
- **主要端点**:
  - `POST /generate` - 生成 Cheat Sheet

### 2. RAG API (`/api/rag`)
- **路由**: `rag_router`
- **功能**: RAG 知识库管理
- **主要端点**:
  - `POST /api/rag/ingest` - 文本摄入
  - `POST /api/rag/ingest/file` - PDF 文件摄入
  - `POST /api/rag/search` - 向量搜索
  - `POST /api/rag/clear` - 清理旧向量数据

### 3. 插件 API (`/api/plugin`)
- **路由**: `plugin_router`
- **功能**: Chrome 插件集成
- **主要端点**:
  - `POST /api/plugin/analyze` - 分析网页内容
  - `POST /api/plugin/generate/final` - 生成最终 Cheat Sheet

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

### 生成 Cheat Sheet 流程
```
用户请求 + RAG 上下文
    │
    ▼
[LLM 生成大纲] (Gemini API)
    │
    ▼
[LLM 生成内容] (Gemini API)
    │
    ▼
[HTML 渲染] (html_generator.py)
    │
    ▼
[返回 Cheat Sheet]
```

## 🛠️ 技术栈

### 后端
- **框架**: FastAPI
- **语言**: Python 3.10+
- **数据库**: MongoDB Atlas (向量搜索)
- **Embedding**: OpenAI `text-embedding-3-small` (1536维)
- **LLM**: Google Gemini 2.5 Flash
- **向量存储**: MongoDB Atlas Vector Search
- **PDF 处理**: PyPDF
- **文本处理**: LangChain

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

## 🔐 配置管理

### 环境变量 (`.env`)
- `MONGODB_URI` - MongoDB 连接字符串
- `DB_NAME` - 数据库名称 (默认: `cheat_sheet_db`)
- `COLLECTION_NAME` - 集合名称 (默认: `knowledge_base`)
- `GOOGLE_API_KEY` - Google Gemini API Key
- `OPENAI_API_KEY` - OpenAI API Key

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
         │  Backend API │
         │  (FastAPI)   │
         └──────┬───────┘
                │
       ┌────────┴────────┐
       │                 │
       ▼                 ▼
┌─────────────┐   ┌─────────────┐
│  MongoDB    │   │  OpenAI API │
│  Atlas      │   │  Gemini API │
└─────────────┘   └─────────────┘
```

## 📝 关键文件说明

### 后端入口
- `backend/main.py` - FastAPI 应用启动入口，配置 CORS 和路由

### 前端入口
- `frontend/src/main.tsx` - React 应用入口
- `frontend/src/App.tsx` - 主应用组件

### 配置文件
- `backend/app/core/config.py` - 应用配置管理
- `backend/requirements.txt` - Python 依赖
- `frontend/package.json` - Node.js 依赖

## 🔄 版本信息

- **Embedding 模型**: OpenAI `text-embedding-3-small` (1536维)
- **LLM 模型**: Google Gemini 2.5 Flash
- **向量存储**: MongoDB Atlas Vector Search
- **FastAPI**: 最新版本
- **React**: 18.3.1
- **TypeScript**: 5.9.3

---

*最后更新: 2025年*

