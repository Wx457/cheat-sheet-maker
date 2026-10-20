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

## 开发约定

- **外部依赖踩坑记录**：开发中发现开源库的错误、非预期行为或可贡献给上游的改进点，一律记录到根目录 `REPO.md`（现象、最小复现、本项目的处理方式、是否值得提 issue / PR）。LLM 输出格式偏差及其清洗方式也记在这里。
- **同步更新升级计划**：每次改动代码后，检查是否需要更新 `UPGRADE_PLAN.md`（步骤状态、实现说明、已变更的接口 / 版本 / 文件路径），需要就在同一次改动中更新；同时检查本文件的目录结构与 Phase 状态表。

---

## 目录结构（含计划变更标注）

图例：`✅ 保留` · `🔨 大改` · `➕ 待新增` · `🗑 待删除`

```
cheat-sheet-maker/
│
├── backend/                              ✅ FastAPI 后端
│   ├── main.py                           🔨 ARQ / MongoDB 已移除 ✅，/health 检查 Qdrant；待移除 static 挂载
│   ├── requirements.txt                  🔨 arq、pymongo、bcrypt、PyJWT、email-validator 已移除 ✅；
│   │                                        待移除 boto3、playwright
│   ├── requirements-dev.txt              ✅
│   ├── pyproject.toml                    ✅
│   ├── Dockerfile                        🔨 移除 playwright install 步骤，去掉 worker 入口
│   │
│   ├── app/
│   │   ├── api/
│   │   │   ├── generate.py               ✅ SSE 流端点 + outline 端点（请求内同步返回 OutlineResponse，不走队列）
│   │   │   ├── rag.py                    ✅ ingest / search / clear
│   │   │   ├── cheat_sheets.py           ✅ 小抄 CRUD（POST/PUT/GET /api/cheat-sheets，Phase 3）
│   │   │   ├── plugin.py                 ✅ 已删除（旧 PDF / MongoDB projects 端点）
│   │   │   ├── task.py                   ✅ 已删除（ingest 本身同步，无任务可查）
│   │   │   └── auth.py                   ✅ 已删除（bcrypt/JWT 注册登录，无调用方；Phase 2 直接接 Clerk）
│   │   │
│   │   ├── core/
│   │   │   ├── config.py                 🔨 MONGODB_*、JWT_* 已移除 ✅；待移除 AWS_*、S3_BUCKET_NAME、PDF_GENERATION_HOST；
│   │   │   │                                QDRANT_HOST/PORT、COHERE_API_KEY（Phase 1）、
│   │   │   │                                SUPABASE_URL/SECRET_KEY（Phase 3）已加 ✅；CLERK_SECRET_KEY（Phase 2）待加
│   │   │   └── auth.py                   ➕ 旧 bcrypt/PyJWT 版已删除；Phase 2 新建为 Clerk JWT 验证
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
│   │   │   ├── db/supabase_store.py      ✅ Supabase：users / cheat_sheets / ingest_batches（Phase 3）
│   │   │   ├── llm/
│   │   │   │   ├── gemini_client.py      ✅ 含 generate_text_stream（SSE 流）
│   │   │   │   ├── openai_client.py      ✅ Embedding
│   │   │   │   └── retry_utils.py        ✅
│   │   │   ├── rag/
│   │   │   │   └── qdrant_store.py       ✅ 唯一的向量存储（Phase 1；MongoDB vector_store.py 已删除）
│   │   │   ├── llm/cohere_client.py      ➕ 新增，Cohere Rerank 客户端（Phase 1）
│   │   │   ├── cache/redis_cache.py      ➕ 新增，SSE 结果缓存（Phase 5）
│   │   │   ├── pdf/                      ✅ 已删除（Playwright 无头渲染）
│   │   │   └── storage/                  🗑 已无文件，只剩空目录，可删除
│   │   │
│   │   └── worker.py                     ✅ 已删除
│   │
│   ├── static/                           🗑 整目录删除（旧 React 构建产物，为 Playwright 服务）
│   │   ├── index.html
│   │   ├── render.html                   # Playwright PDF 渲染入口，随 pdf/ 一起退役
│   │   └── assets/
│   │
│   ├── scripts/
│   │   └── eval_retrieval_groundedness.py ✅ 已改用 Qdrant（migrate_mongo_to_qdrant.py 迁移完成后已删除）
│   │
│   └── tests/                            ✅ 全部可运行（无需排除任何文件）
│       ├── conftest.py
│       ├── test_domain_logic.py          ✅
│       ├── test_embedding_batch.py       ✅
│       ├── test_generate_api.py          ✅
│       ├── test_ingest_quota.py          ✅ 已改写为 QdrantVectorStore 配额 / 截断
│       ├── test_llm_retry.py             ✅
│       ├── test_rag_api.py               ✅
│       ├── test_stream_parsing.py        ✅ Gemini 输出形态解析（见 REPO.md）
│       ├── test_cheat_sheets_api.py      ✅
│       └── test_ingestion_service.py     ✅
│
├── cheat-sheet-web/                      ✅ Next.js Webapp（主前端，持续开发）
│   └── src/
│       ├── app/
│       │   ├── layout.tsx                ✅
│       │   ├── （无根 page.tsx）         ✅ "/" → /editor 由 next.config.ts redirects() 处理
│       │   └── editor/page.tsx           🔨 已有：sheetId 恢复 / 自动保存（Phase 3 ✅）；待做：Phase 7 格式预设、Phase 2 Clerk 接入
│       ├── components/
│       │   ├── CheatSheetCard.tsx        🔨 Phase 7 KaTeX 查看/编辑双态
│       │   ├── CardList.tsx              ✅ DnD Kit 拖拽列表
│       │   └── StreamingStatus.tsx       ✅
│       ├── lib/
│       │   ├── api.ts                    ✅ 含 /api/cheat-sheets 的 create / update / load、ApiError
│       │   └── streaming.ts              ✅
│       ├── stores/cheatSheetStore.ts     ✅ 含 sheetId / savedSnapshot / loadSheet（Phase 3 ✅）；
│       │                                    可选：Phase 6-6 persist 兜底首次保存前的状态
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
├── docker-compose.yml                    ✅ worker 服务已移除；qdrant 服务已新增
├── docker-compose.override.yml           ✅ worker 已移除
├── deploy-prod.sh                        🔨 移除 worker 部署步骤
└── .github/workflows/backend-tests.yml  🔨 随测试变动同步
```

---

## 各 Phase 待完成状态

| Phase | 内容 | 状态 |
|-------|------|------|
| 6 | SSE 流式渲染 | ✅ 2026-10-20 修复：生产者线程不再阻塞到生成结束，section 逐个推送 |
| 6-6 | 刷新丢失卡片状态（zustand persist） | 🟡 生成完成后的刷新已由 Phase 3 解决；生成中 / 首次保存前的兜底可选 |
| 7 | KaTeX 渲染 + 格式预设（多栏/字号/纸张） | 🟡 7-1 KaTeX 查看/编辑双态已完成；7-2~7-4 预设/多栏/字号待做 |
| 1 | Qdrant 替换 MongoDB Vector Search + Cohere Rerank | ✅ 2026-10-20：Qdrant 版本已对齐（server v1.19.2 / client 1.19.1）；MongoDB 整体退役（vector_store、auth、plugin、健康检查、pymongo 均已移除） |
| 清理 | 移除 ARQ/worker、pdf/、storage/、static/、frontend/、AWS 配置及依赖 | 🟡 已移除 ARQ/worker/task.py、pdf/、plugin.py、MongoDB；剩余：static/ 及其挂载、frontend/、空的 storage/、boto3/playwright 依赖与 Dockerfile 里的 playwright install、AWS_*/PDF_GENERATION_HOST 配置 |
| 3 | Supabase 持久化（用户/小抄历史） | ✅ 2026-10-20：后端 supabase_store.py、/api/cheat-sheets CRUD、ingest_batches 同步；前端生成后自动保存、URL sheetId 刷新恢复、编辑防抖 PUT（3-4-c 浏览器端流程待手动验证） |
| 2 | Clerk 鉴权（插件↔webapp 无感互通） | ⏳ 旧 bcrypt/PyJWT 已提前删除（2-5 后端部分完成）；目前无鉴权，仅靠匿名 X-User-ID |
| 5 | Redis Cache Layer（SSE 结果缓存） | ⏳ |
| 4 | Stripe 支付 | ⏳ |

依赖顺序：Phase 7 → Phase 1 → Phase 3 → Phase 2 → Phase 5 → Phase 4
