# Cheat Sheet Maker — CLAUDE.md

## 产品职责边界

```
Chrome Extension                    Web App (cheat-sheet-web, Next.js)
────────────────                    ──────────────────────────────────
✅ 扫描网页，构建 RAG 知识库           ✅ 接收 SSE 流，渲染卡片
✅ outline 编辑（增删改 topics）       ✅ 拖拽 / 编辑 / 删除 section
✅ 参数配置，打开 webapp 并传参        ✅ 客户端 PDF 导出（window.print）
❌ 不渲染最终结果，不下载 PDF          ❌ 不负责数据入口
```

无头浏览器（Playwright）和 S3 已从架构中移除。不再有 ARQ worker 进程。

---

## 目录结构（含计划变更标注）

图例：`✅ 保留` · `🔨 大改` · `➕ 待新增` · `🗑 待删除`

```
cheat-sheet-maker/
│
├── backend/                              ✅ FastAPI 后端
│   ├── main.py                           🔨 移除 ARQ lifespan、static 挂载、S3/Playwright 初始化
│   ├── requirements.txt                  🔨 移除 boto3、arq、playwright、bcrypt、PyJWT；
│   │                                        新增 qdrant-client、cohere、supabase（随对应 Phase）
│   ├── requirements-dev.txt              ✅
│   ├── pyproject.toml                    ✅
│   ├── Dockerfile                        🔨 移除 playwright install 步骤，去掉 worker 入口
│   │
│   ├── app/
│   │   ├── api/
│   │   │   ├── generate.py               🔨 保留 SSE 流端点 + outline 端点；
│   │   │   │                                移除 ARQ enqueue 的 generate_cheat_sheet 端点
│   │   │   ├── plugin.py                 🔨 移除 S3 下载、download_cheat_sheet、
│   │   │   │                                plugin_generate_final 等 PDF/S3 相关端点
│   │   │   ├── rag.py                    ✅ ingest / search / clear
│   │   │   ├── task.py                   🔨 仅保留 ingest 进度轮询；
│   │   │   │                                移除 cheat sheet 生成任务查询
│   │   │   └── auth.py                   🗑 login / register 端点（→ Clerk，Phase 2）
│   │   │
│   │   ├── core/
│   │   │   ├── config.py                 🔨 移除 AWS_*、S3_BUCKET_NAME、PDF_GENERATION_HOST；
│   │   │   │                                新增 QDRANT_HOST/PORT、COHERE_API_KEY（Phase 1）、
│   │   │   │                                SUPABASE_URL/KEY（Phase 3）、CLERK_SECRET_KEY（Phase 2）
│   │   │   └── auth.py                   🔨 现为 bcrypt/PyJWT 过渡方案 → 替换为 Clerk JWT 验证（Phase 2）
│   │   │
│   │   ├── schemas/
│   │   │   └── cheat_sheet.py            🔨 移除 PDF/S3 相关 schema 字段
│   │   │
│   │   ├── application/services/
│   │   │   ├── cheat_sheet_service.py    🔨 移除 PDF 生成、S3 上传流程；
│   │   │   │                                加入 Cohere Rerank（Phase 1）；
│   │   │   │                                持久化目标改为 Supabase（Phase 3）
│   │   │   └── ingestion_service.py      🔨 向量写入目标改为 Qdrant（Phase 1）
│   │   │
│   │   ├── domain/                       ✅ 纯业务逻辑，不受基础设施替换影响
│   │   │   ├── rules/budget.py           ✅
│   │   │   ├── prompts/templates.py      ✅
│   │   │   └── utils/
│   │   │       ├── cleaner.py            ✅
│   │   │       └── math_formatter.py     ✅
│   │   │
│   │   ├── infrastructure/
│   │   │   ├── llm/
│   │   │   │   ├── gemini_client.py      ✅ 含 generate_text_stream（SSE 流）
│   │   │   │   ├── openai_client.py      ✅ Embedding
│   │   │   │   └── retry_utils.py        ✅
│   │   │   ├── rag/
│   │   │   │   ├── vector_store.py       🗑 MongoDB Atlas Vector Search → 整体替换（Phase 1）
│   │   │   │   └── qdrant_store.py       ➕ 新增，替换 vector_store.py（Phase 1）
│   │   │   ├── llm/cohere_client.py      ➕ 新增，Cohere Rerank 客户端（Phase 1）
│   │   │   ├── cache/redis_cache.py      ➕ 新增，SSE 结果缓存（Phase 5）
│   │   │   ├── pdf/                      🗑 整目录删除（renderer.py，Playwright 无头渲染）
│   │   │   └── storage/                  🗑 整目录删除（minio_client.py，AWS S3）
│   │   │
│   │   └── worker.py                     🗑 ARQ Worker 进程（无头渲染/S3移除后整体删除）
│   │
│   ├── static/                           🗑 整目录删除（旧 React 构建产物，为 Playwright 服务）
│   │   ├── index.html
│   │   ├── render.html                   # Playwright PDF 渲染入口，随 pdf/ 一起退役
│   │   └── assets/
│   │
│   ├── scripts/
│   │   ├── eval_retrieval_groundedness.py ✅
│   │   └── migrate_mongo_to_qdrant.py    ➕ 一次性迁移脚本（Phase 1）
│   │
│   └── tests/                            🔨 随 vector_store / worker / auth 改动同步更新测试
│       ├── conftest.py
│       ├── test_domain_logic.py          ✅
│       ├── test_embedding_batch.py       ✅
│       ├── test_generate_api.py          🔨
│       ├── test_indexing_resilience.py   🔨 MongoDB 换 Qdrant 后重写
│       ├── test_ingest_quota.py          🔨
│       ├── test_llm_retry.py             ✅
│       ├── test_rag_api.py               🔨
│       └── test_task_api.py              🔨
│
├── cheat-sheet-web/                      ✅ Next.js Webapp（主前端，持续开发）
│   └── src/
│       ├── app/
│       │   ├── layout.tsx                ✅
│       │   ├── page.tsx                  ✅ 重定向到 /editor
│       │   └── editor/page.tsx           🔨 Phase 7 KaTeX + 格式预设；Phase 2 Clerk 接入
│       ├── components/
│       │   ├── CheatSheetCard.tsx        🔨 Phase 7 KaTeX 查看/编辑双态
│       │   ├── CardList.tsx              ✅ DnD Kit 拖拽列表
│       │   └── StreamingStatus.tsx       ✅
│       ├── lib/
│       │   ├── api.ts                    ✅
│       │   └── streaming.ts              ✅
│       ├── stores/cheatSheetStore.ts     🔨 Phase 6-6 persist 中间件（防刷新丢失）；
│       │                                    Phase 3 接入 Supabase 持久化
│       └── types/index.ts               ✅
│
├── chrome-extension/                     🔨 重构中：移除旧 PDF 下载流程
│   ├── manifest.json                     ✅
│   ├── background.js                     ✅
│   ├── content.js                        ✅ 网页内容抓取
│   ├── popup.html                        🔨
│   ├── popup.js                          🔨 主流程改为：扫描→ingest→立即打开 webapp
│   ├── api-config.js                     🔨 移除 S3/PDF 相关配置
│   ├── config.js                         🔨
│   └── formPersistence.js                ✅
│
├── frontend/                             🗑 整目录删除（旧 Vite+React，已被 cheat-sheet-web 取代）
│
├── docker-compose.yml                    🔨 移除 worker 服务；新增 qdrant 服务（Phase 1）
├── docker-compose.override.yml           🔨 同步调整
├── deploy-prod.sh                        🔨 移除 worker 部署步骤
└── .github/workflows/backend-tests.yml  🔨 随测试变动同步
```

---

## 各 Phase 待完成状态

| Phase | 内容 | 状态 |
|-------|------|------|
| 6-6 | 刷新丢失卡片状态（zustand persist） | ⏳ |
| 7 | KaTeX 渲染 + 格式预设（多栏/字号/纸张） | ⏳ |
| 1 | Qdrant 替换 MongoDB Vector Search + Cohere Rerank | ⏳ |
| 3 | Supabase 持久化（用户/小抄历史） | ⏳ |
| 2 | Clerk 鉴权（替换 bcrypt/PyJWT，插件↔webapp 无感互通） | ⏳ |
| 5 | Redis Cache Layer（SSE 结果缓存） | ⏳ |
| 4 | Stripe 支付 | ⏳ |

依赖顺序：Phase 7 → Phase 1 → Phase 3 → Phase 2 → Phase 5 → Phase 4
