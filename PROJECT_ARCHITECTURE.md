# Cheat Sheet Maker - Project Architecture

## 📁 Project Structure

```
cheat-sheet-maker/
│
├── backend/                          # Backend Service (FastAPI)
│   ├── main.py                       # FastAPI application entry
│   │   ├── lifespan()                # Create/close ARQ Redis connection pool on startup/shutdown
│   │   ├── setup_mongodb_ttl_indexes() # Create MongoDB TTL indexes (projects/vectors)
│   │   └── health()                  # Health check endpoint
│   ├── requirements.txt              # Python dependencies
│   ├── Dockerfile                    # Backend Docker image build file
│   │
│   ├── app/                          # Application main directory
│   │   ├── api/                      # API routing layer
│   │   │   ├── generate.py           # Cheat Sheet generation API (async task mode)
│   │   │   │   ├── generate_outline() # Enqueue generate_outline_task
│   │   │   │   └── generate_cheat_sheet() # Enqueue generate_cheat_sheet_task
│   │   │   ├── plugin.py             # Chrome extension API (async task mode)
│   │   │   │   ├── plugin_analyze()  # Extension scrape → RAG ingest → enqueue outline task
│   │   │   │   ├── plugin_generate_final() # Extension topic selection → enqueue cheat sheet task
│   │   │   │   ├── download_cheat_sheet() # Read project → PDF render download
│   │   │   │   └── reset_knowledge_base() # Delete current user vector data
│   │   │   ├── rag.py                # RAG knowledge base API (ingest/search/clear)
│   │   │   │   ├── ingest_text()     # Text ingestion to vector store
│   │   │   │   ├── ingest_file()     # PDF ingestion to vector store
│   │   │   │   ├── search_context()  # RAG retrieval
│   │   │   │   └── clear_vector_data() # Clear vector collection
│   │   │   └── task.py               # Task status query API
│   │   │       └── get_task_status() # Query ARQ task status/result/presigned download URL
│   │   │
│   │   ├── core/                     # Core configuration
│   │   │   └── config.py             # Application configuration (MongoDB, API Keys)
│   │   │
│   │   ├── schemas/                  # Data model definitions
│   │   │   └── cheat_sheet.py        # Cheat Sheet related schemas
│   │   │
│   │   ├── application/services/     # Use case orchestration layer (Application Layer)
│   │   │   ├── ingestion_service.py
│   │   │   │   ├── IngestionService.process_text() # Clean → vectorize → write
│   │   │   │   └── IngestionService.process_file() # Validate PDF → parse → write
│   │   │   └── cheat_sheet_service.py
│   │   │       ├── CheatSheetService.generate_outline() # Call Gemini to generate outline
│   │   │       └── CheatSheetService.create_cheat_sheet_flow() # RAG → budget → LLM → clean → PDF → upload to AWS S3 → save to DB
│   │   │
│   │   ├── domain/                   # Pure business rules and prompts (Domain Layer)
│   │   │   ├── rules/budget.py
│   │   │   │   └── BudgetRule.calculate() # Allocate item budget by page count/relevance
│   │   │   ├── prompts/templates.py
│   │   │   │   ├── CheatSheetPrompts.render_outline_prompt() # Outline prompt
│   │   │   │   └── CheatSheetPrompts.render_cheatsheet_prompt() # Cheat sheet prompt
│   │   │   └── utils/
│   │   │       ├── cleaner.py
│   │   │       │   ├── clean_raw_text() # Input cleaning (remove zero-width chars/whitespace compression/strip HTML)
│   │   │       │   └── repair_json_string() # LLM JSON repair
│   │   │       └── math_formatter.py
│   │   │           └── normalize_equation() # Normalize formula to $$...$$ wrapped LaTeX
│   │   │
│   │   ├── infrastructure/           # Low-level clients (Infrastructure Layer)
│   │   │   ├── llm/
│   │   │   │   ├── gemini_client.py
│   │   │   │   │   └── GeminiClient.generate_text()/generate_json() # Gemini call with retry
│   │   │   │   └── openai_client.py
│   │   │   │       └── OpenAIClient.embed_documents()/embed_query() # OpenAI Embedding
│   │   │   ├── pdf/renderer.py
│   │   │   │   └── generate_pdf_via_browser() # Playwright render frontend static page to generate PDF (uses PDF_GENERATION_HOST config to access FastAPI)
│   │   │   ├── rag/vector_store.py
│   │   │   │   ├── VectorStore.ingest_text()/ingest_pdf() # Chunk → vectorize → MongoDB
│   │   │   │   ├── search_context_mmr()/search_context() # user_id-based retrieval/MMR deduplication
│   │   │   │   ├── delete_user_data()/clear_vector_data() # User/full vector cleanup
│   │   │   │   └── get_vector_store() # Singleton get VectorStore
│   │   │   └── storage/minio_client.py
│   │   │       ├── MinIOClient.ensure_bucket() # Create/check AWS S3 Bucket (handles LocationConstraint based on AWS_REGION)
│   │   │       ├── upload_file() # Upload file to AWS S3
│   │   │       ├── get_presigned_url() # Generate presigned URL
│   │   │       └── get_minio_client() # Singleton get MinIOClient (class name kept for compatibility)
│   │   │
│   │   └── worker.py                 # ARQ Worker task definitions
│   │       ├── generate_outline_task() # Call CheatSheetService.generate_outline
│   │       ├── generate_cheat_sheet_task() # Call CheatSheetService.create_cheat_sheet_flow
│   │       └── WorkerSettings        # ARQ configuration/task list
│   │
│   ├── static/                       # Frontend build artifacts (generated by npm run deploy)
│   │   ├── index.html                # Homepage display page (pure static HTML)
│   │   ├── render.html               # React renderer entry (for Playwright PDF generation)
│   │   └── assets/                   # Vite-built js/css/font static resources
│   │
├── frontend/                         # Frontend Application (React + TypeScript + Vite)
│   ├── index.html                    # Homepage display page (pure static HTML + Tailwind)
│   ├── render.html                   # React renderer entry (contains <div id="root"> and /src/main.tsx)
│   ├── src/
│   │   ├── main.tsx                  # React application entry
│   │   ├── components/Preview.tsx    # Preview component (renders cheat sheet content)
│   │   └── pages/PrintPage.tsx       # Print/export page
│   └── dist/                         # Frontend build output (generated by npm run build/deploy)
│
├── chrome-extension/                 # Chrome Browser Extension
│   ├── manifest.json                 # Extension configuration file
│   ├── background.js                 # Background script (handles long connections, message forwarding)
│   ├── content.js                    # Content script (scrapes web page content)
│   ├── popup.html                    # Popup window HTML
│   ├── popup.js                      # Popup window logic
│   └── formPersistence.js            # Form data persistence logic
│
└── docker-compose.yml                # Docker orchestration configuration
```

## 🏗️ System Architecture

### Producer-Consumer Pattern

```
┌─────────────────────────────────────────────────────────┐
│                  Frontend Layer                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ React + TS   │  │ Chrome Ext   │  │ User UI     │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │ HTTP/REST API
                          ▼
┌─────────────────────────────────────────────────────────┐
│          API Server (Producer)                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ generate │  │   rag    │  │  plugin  │  │  task  │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │
│                                                         │
│  Role: Receive request → Push to ARQ queue → Return task_id │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼ Push task
┌─────────────────────────────────────────────────────────┐
│                  Redis Queue (ARQ)                       │
│                  Task queue management                    │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼ Consume task
┌─────────────────────────────────────────────────────────┐
│          Worker Process (Consumer)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │  LLM Service │  │ PDF Service  │  │ Storage      │ │
│  │  (Gemini)    │  │ (Playwright) │  │ (AWS S3)     │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
│                                                         │
│  Role: Get task from queue → Execute time-consuming ops → Store result │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                Data Storage Layer                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ MongoDB Atlas│  │ Vector Store │  │ AWS S3       │ │
│  │ (Doc Storage) │  │ (1536-dim)   │  │ (PDF Files)  │ │
│  └──────────────┘  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## 🔄 Data Flow

### Text Ingestion Flow
```
User Input/PDF File
    │
    ▼
[Text Cleaning] (cleaner.py)
    │
    ▼
[Text Chunking] (RecursiveCharacterTextSplitter)
    │
    ▼
[Generate Vectors] (OpenAI Embedding API)
    │
    ▼
[Store to MongoDB] (MongoDBAtlasVectorSearch)
```

### RAG Retrieval Flow

#### Similarity Search (for Outline generation)
```
User Query
    │
    ▼
[Generate Query Vector] (OpenAI Embedding API)
    │
    ▼
[Vector Similarity Search] (MongoDB Atlas Vector Search)
    │
    ▼
[Return Relevant Document Fragments] (with similarity scores)
```

#### MMR Retrieval (for Cheat Sheet generation)
```
User Query
    │
    ▼
[Generate Query Vector] (OpenAI Embedding API)
    │
    ▼
[MMR Retrieval] (Maximal Marginal Relevance algorithm)
    │    ├──→ Fetch fetch_k candidate documents
    │    └──→ Select k most relevant and diverse documents
    │
    ▼
[Content Deduplication] (using hash fingerprints)
    │
    ▼
[Return Deduplicated Document Fragments]
```

**Note**: 
- When multiple topics exist, system uses `asyncio.gather` to parallelize all topic searches, significantly improving performance
- Cheat Sheet generation uses MMR retrieval + deduplication to reduce redundancy and lower context length

### Cheat Sheet Generation Flow (Async Task Mode)
```
User Request
    │
    ▼
[API Server Receive] → Push task to ARQ queue → Return task_id immediately
    │
    ▼
[Worker Process Consume Task]
    │
    ├──→ [RAG Context Retrieval] (Parallel MMR retrieval + deduplication)
    │    ├──→ Parallel execute all topic MMR retrievals (asyncio.gather)
    │    ├──→ MongoDB Atlas Vector Search (MMR algorithm)
    │    └──→ Content deduplication (hash fingerprints)
    │
    ▼
[LLM Generate Content] (Gemini API)
    │
    ▼
[Save to Database] (MongoDB projects collection, if metadata included)
    │
    ▼
[Clean Data] (clean equation format)
    │
    ▼
[Generate PDF] (renderer.py + Playwright)
    │    └──→ Access {PDF_GENERATION_HOST}/static/render.html#/print
    │
    ▼
[Upload to AWS S3] (minio_client.py)
    │
    ▼
[Return Result] {file_key, project_id, ...}
    │
    ▼
[Client Poll /api/task/{task_id}]
    │
    ▼
[Get Presigned Download URL] (download_url)
```

## 🛠️ Technology Stack

### Backend
- **Framework**: FastAPI
- **Language**: Python 3.10+
- **Task Queue**: ARQ (Async Redis Queue)
- **Message Queue**: Redis
- **Database**: MongoDB Atlas (Vector Search + Document Storage)
- **Object Storage**: AWS S3
- **Embedding**: OpenAI `text-embedding-3-small` (1536 dimensions)
- **LLM**: Google Gemini 2.5 Flash
- **Vector Storage**: MongoDB Atlas Vector Search
- **Retrieval Algorithms**: 
  - Similarity Search - for Outline generation
  - MMR (Maximal Marginal Relevance) - for Cheat Sheet generation, reduces redundancy
- **PDF Processing**: Playwright (Headless Chrome)
- **Text Processing**: LangChain
- **S3 Client**: boto3
- **Async Concurrency**: asyncio (for parallel RAG retrieval)

### Frontend
- **Framework**: React 18.3
- **Language**: TypeScript 5.9
- **Build Tool**: Vite 7.2
- **Routing**: React Router DOM 7.11
- **Math Formulas**: KaTeX + react-latex-next
- **HTTP Client**: Axios

### Chrome Extension
- **Manifest**: Version 3
- **Permissions**: activeTab, scripting
- **Functionality**: Web page content scraping and sending

## ⚡ Performance Optimizations

### 1. Parallel MMR Retrieval + Deduplication
- **Location**: `backend/app/application/services/cheat_sheet_service.py` - `create_cheat_sheet_flow()` function
- **Before**: Sequential serial retrieval
  - Each topic waits for previous to complete
  - Total time = N × T (N topics, each takes T)
  - Uses similarity search, may return duplicate content
- **After**: Parallel MMR retrieval + deduplication
  - **Parallel Execution**: All topics search simultaneously (using `asyncio.gather`)
  - **MMR Algorithm**: Uses `search_context_mmr(k=3, fetch_k=10)` to reduce redundancy
  - **Content Deduplication**: Uses content hash fingerprints to avoid duplicate content
  - Total time ≈ T (slowest single search time)
- **Performance Improvement**: 
  - **Speed**: Theoretically N times faster (N = number of topics)
  - **Quality**: MMR reduces redundancy, deduplication further optimizes
  - **Cost**: Reduces context length, lowers LLM token consumption

## 🔐 Configuration

### Environment Variables (`.env`)

#### Required
- `MONGODB_URI` - MongoDB connection string
- `GOOGLE_API_KEY` - Google Gemini API Key
- `OPENAI_API_KEY` - OpenAI API Key (for Embedding)

#### AWS S3 Configuration
- `AWS_ACCESS_KEY_ID` - AWS S3 access key
- `AWS_SECRET_ACCESS_KEY` - AWS S3 secret key
- `AWS_REGION` - AWS region (e.g., `us-east-2`)
- `S3_BUCKET_NAME` - S3 Bucket name (default: `cheat-sheets`)

#### PDF Generation Configuration
- `PDF_GENERATION_HOST` - Address for Worker process to access FastAPI server
  - Local development: `http://localhost:8000`
  - Docker Compose: `http://backend:8000` (using service name)
  - Other environments: Configure according to actual network setup

#### Optional
- `DB_NAME` - Database name (default: `cheat_sheet_db`)
- `COLLECTION_NAME` - Collection name (default: `knowledge_base`)
- `REDIS_HOST` - Redis host (default: `localhost`)
- `REDIS_PORT` - Redis port (default: `6379`)
- `REDIS_DB` - Redis database number (default: `0`)
- `REDIS_PASSWORD` - Redis password (optional)

## 📋 Key Files

### Backend Entry Points
- `backend/main.py` - FastAPI application startup entry, configures CORS, routes, ARQ connection pool, and static resource mounting
  - Mount directory: `backend/static` (populated by frontend build artifacts)
  - Access paths: `/static` (HTML) and `/assets` (JS/CSS resources)
- `backend/app/worker.py` - ARQ Worker process entry (runs independently)

### Frontend Entry Points
- `frontend/src/main.tsx` - React application entry
- `frontend/src/pages/PrintPage.tsx` - Print/export page

### Configuration Files
- `backend/app/core/config.py` - Application configuration management (MongoDB, Redis, AWS S3, PDF generation, API Keys)
- `backend/requirements.txt` - Python dependencies
- `frontend/package.json` - Node.js dependencies and build/deploy scripts
  - `npm run deploy`: Build frontend → Copy `dist/*` to `backend/static/` for FastAPI static serving and PDF rendering

### Startup Methods
- **API Server**: `python main.py` or `uvicorn main:app`
- **Worker**: `arq app.worker.WorkerSettings` or `python -m app.worker`
