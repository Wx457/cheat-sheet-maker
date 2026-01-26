# Backend 文件架构与关键函数一览

参考 `PROJECT_ARCHITECTURE.md` 的目录风格，聚焦后端（backend）重要脚本及其主要类/方法/函数，便于定位业务逻辑与编排入口。

```
backend/
├── main.py
│   ├── lifespan()                  # 启停时创建/关闭 ARQ Redis 连接池
│   ├── setup_mongodb_ttl_indexes() # 创建 MongoDB TTL 索引
│   └── health()                    # 健康检查
│
├── app/
│   ├── api/                        # API 路由层
│   │   ├── generate.py
│   │   │   ├── generate_outline()  # 入队 generate_outline_task
│   │   │   └── generate_cheat_sheet() # 入队 generate_cheat_sheet_task
│   │   ├── plugin.py
│   │   │   ├── plugin_analyze()        # 插件抓取→RAG摄入→入队大纲任务
│   │   │   ├── plugin_generate_final() # 插件选题→入队小抄任务
│   │   │   ├── download_cheat_sheet()  # 读取项目→PDF渲染下载
│   │   │   └── reset_knowledge_base()  # 删除当前用户向量数据
│   │   ├── rag.py
│   │   │   ├── ingest_text()       # 文本摄入向量库
│   │   │   ├── ingest_file()       # PDF 摄入向量库
│   │   │   ├── search_context()    # RAG 检索
│   │   │   └── clear_vector_data() # 清空向量集合
│   │   └── task.py
│   │       └── get_task_status()   # 查询 ARQ 任务状态/结果/预签名下载链接
│   │
│   ├── application/services/       # 用例级编排层
│   │   ├── ingestion_service.py
│   │   │   ├── IngestionService.process_text() # 清洗→向量化写入
│   │   │   └── IngestionService.process_file() # 校验PDF→解析→写入
│   │   └── cheat_sheet_service.py
│   │       ├── CheatSheetService.generate_outline()      # 调用 Gemini 生成大纲
│   │       └── CheatSheetService.create_cheat_sheet_flow() # RAG→预算→LLM→清洗→PDF→上传到AWS S3→入库
│   │
│   ├── domain/                     # 纯业务规则与提示
│   │   ├── rules/budget.py
│   │   │   └── BudgetRule.calculate()     # 按页数/相关性分配条目预算
│   │   ├── prompts/templates.py
│   │   │   ├── CheatSheetPrompts.render_outline_prompt()  # 大纲提示词
│   │   │   └── CheatSheetPrompts.render_cheatsheet_prompt() # 小抄提示词
│   │   └── utils/
│   │       ├── cleaner.py
│   │       │   ├── clean_raw_text()        # 输入清洗（去零宽字符/空白压缩/剥离 HTML）
│   │       │   └── repair_json_string()    # LLM JSON 修复
│   │       └── math_formatter.py
│   │           └── normalize_equation()      # 公式统一 $$ 包裹
│   │
│   ├── infrastructure/             # 底层客户端
│   │   ├── llm/
│   │   │   ├── gemini_client.py
│   │   │   │   └── GeminiClient.generate_text()/generate_json() # 带重试的 Gemini 调用
│   │   │   └── openai_client.py
│   │   │       └── OpenAIClient.embed_documents()/embed_query() # OpenAI Embedding
│   │   ├── pdf/renderer.py
│   │   │   └── generate_pdf_via_browser() # Playwright 渲染前端静态页生成 PDF（使用 PDF_GENERATION_HOST 配置访问 FastAPI）
│   │   ├── rag/vector_store.py
│   │   │   ├── VectorStore.ingest_text()/ingest_pdf() # 切片→向量化→MongoDB
│   │   │   ├── search_context_mmr()/search_context() # 基于 user_id 的检索/MMR 去重
│   │   │   ├── delete_user_data()/clear_vector_data() # 用户/全量向量清理
│   │   │   └── get_vector_store()   # 单例获取 VectorStore
│   │   └── storage/minio_client.py
│   │       ├── MinIOClient.ensure_bucket()    # 创建/检查 AWS S3 Bucket（根据 AWS_REGION 处理 LocationConstraint）
│   │       ├── upload_file()                  # 上传文件到 AWS S3
│   │       ├── get_presigned_url()            # 生成预签名 URL
│   │       └── get_minio_client()             # 单例获取 MinIOClient（类名保持兼容性）
│   │
│   └── worker.py                    # ARQ 任务注册（委托 Application）
│       ├── generate_outline_task()      # 调用 CheatSheetService.generate_outline
│       ├── generate_cheat_sheet_task()  # 调用 CheatSheetService.create_cheat_sheet_flow
│       └── WorkerSettings            # ARQ 配置/任务列表
│
└── docker-compose.yml               # 编排配置
```

