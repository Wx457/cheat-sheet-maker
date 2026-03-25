# Cheat Sheet Maker / 速查表生成器

**English** | [中文](#中文)


[![Store](https://img.shields.io/badge/Chrome_Web_Store-Live-blue)](https://chromewebstore.google.com/detail/ai-cheat-sheet-generator/aimjdpkndlippaflppddgknkapfiihbl) 
[![Demo](https://img.shields.io/badge/Demo-YouTube-red)](https://youtu.be/2dKr7PnRBxY?si=Dji06LGYNdrJWN1R)
[![Backend Tests](https://github.com/Wx457/cheat-sheet-maker/actions/workflows/backend-tests.yml/badge.svg)](https://github.com/Wx457/cheat-sheet-maker/actions/workflows/backend-tests.yml)

---

### 🛠️ Engineering Highlights (For Google Reviewers)
* **Infrastructure Reliability**: Resolved the **Docker PID 1 zombie reaping problem** via custom init processes, ensuring 0-downtime scaling for Playwright/Chromium workers.
* **Performance Optimization**: Engineered an asynchronous RAG pipeline (FastAPI/Redis), reducing end-to-end latency by **80% (15s → 3s)**.
* **High-Concurrency Architecture**: Designed a Producer-Consumer pattern capable of absorbing **1,000 RPM** peak traffic with idempotent task processing.
* **Advanced RAG Strategy**: Implemented **MMR (Maximal Marginal Relevance)** and hash-based deduplication to minimize LLM hallucinations and token redundancy.
* **Quality Guardrails**: Added a **pytest** regression suite, shared exponential backoff for Gemini/OpenAI calls, and GitHub Actions CI with dependency, lint, format, and smoke-import checks.

**Quick Links:** [Store](https://chromewebstore.google.com/detail/ai-cheat-sheet-generator/aimjdpkndlippaflppddgknkapfiihbl) | [Demo](https://youtu.be/2dKr7PnRBxY?si=Dji06LGYNdrJWN1R) | [Full Technical Specs](#technical-documentation) | [User Guide](#user-guide)

---
## English

### 🎯 Product Overview
Cheat Sheet Maker is an intelligent study aid that automatically generates comprehensive cheat sheets from your knowledge base. It supports multiple knowledge ingestion methods and uses RAG (Retrieval-Augmented Generation) to create personalized study materials.

### ✨ Key Features   

#### 1. **Flexible Knowledge Base Building**
Build your knowledge base through multiple methods:
- **Web Page Scanning**: Scan GPT web chat windows to capture conversation content
- **Text Pasting**: Directly paste text content into the extension
- **PDF Upload**: Upload PDF files for knowledge extraction
- **Mixed Mode**: Combine all three methods - scan multiple pages, paste text, and upload PDFs to build a comprehensive knowledge base

#### 2. **Intelligent Content Generation**
- **RAG-Powered**: Uses vector search to retrieve relevant content from your knowledge base
- **Topic Extraction**: Automatically extracts exam topics from your materials
- **Smart Budgeting**: Allocates content based on page limits and topic relevance
- **LaTeX Support**: Renders mathematical formulas beautifully using KaTeX

#### 3. **Professional PDF Output**
- **A4 Format**: Optimized for printing and digital viewing
- **Two-Column Layout**: Maximizes information density
- **High-Quality Rendering**: Clean, readable typography

<a id="user-guide"></a>
### 📖 User Guide

#### 1. Install Extension
Simply add the extension to your browser via the **[Chrome Web Store](https://chromewebstore.google.com/detail/ai-cheat-sheet-generator/aimjdpkndlippaflppddgknkapfiihbl)**. This ensures you are running the latest production-ready version.

#### 2. Build Your Knowledge Base
Aggregate information using any combination of these high-fidelity ingestion methods:
- **Smart Web Scan**: Open a GPT chat window and click "Scan & Add to KB." The agent automatically scrolls and captures the full conversation context.
- **Direct Ingestion**: Paste text directly into the extension for immediate processing.
- **PDF Extraction**: Upload local PDF files to be parsed and indexed into your local **vector store**.

#### 3. Generate Optimized Outlines
Enter your course details (Name, Syllabus, Exam Type). The system analyzes your entire knowledge base to extract core topics and exam-relevant themes. 
*Note: Processing time scales with the volume of ingested data.*

#### 4. Configure & Generate Cheat Sheet
Select your preferred topics and set a page constraint based on your study needs:
- **1 Side**: Survival mode (Core formulas/definitions only).
- **1 Page**: Compact derivation mode.
- **2 Pages**: Comprehensive review mode.
- **Unlimited**: Detailed study guide with examples.

#### 5. Export to PDF
Once the **RAG pipeline** completes the generation, click **"Download PDF"** to get a professionally typeset, two-column A4 cheat sheet ready for print.

---

## 中文

### 🎯 产品概述

速查表生成器是一款智能学习辅助工具，能够从您的知识库自动生成全面的速查表。它支持多种知识录入方式，并使用 RAG（检索增强生成）技术创建个性化学习材料。

### ✨ 核心功能

#### 1. **灵活的知识库构建**
通过多种方式构建知识库：
- **网页扫描**：扫描 GPT 网页聊天窗口，捕获对话内容
- **文本粘贴**：直接将文本内容粘贴到插件中
- **PDF 上传**：上传 PDF 文件进行知识提取
- **混合模式**：结合所有三种方式 - 多次扫描网页、粘贴文本、上传 PDF，构建全面的知识库

#### 2. **智能内容生成**
- **RAG 驱动**：使用向量搜索从知识库中检索相关内容
- **主题提取**：自动从您的材料中提取考试主题
- **智能预算**：根据页数限制和主题相关性分配内容
- **LaTeX 支持**：使用 KaTeX 精美渲染数学公式

#### 3. **专业 PDF 输出**
- **A4 格式**：针对打印和数字查看优化
- **双栏布局**：最大化信息密度
- **高质量渲染**：清晰、易读的排版

### 📖 用户指南

#### 1. 安装扩展
直接通过 **[Chrome Web Store](https://chromewebstore.google.com/detail/ai-cheat-sheet-generator/aimjdpkndlippaflppddgknkapfiihbl)** 添加扩展，确保你使用的是最新稳定生产版本。

#### 2. 构建知识库
可任意组合以下高保真知识录入方式：
- **智能网页扫描**：打开 GPT 聊天窗口，点击「Scan & Add to KB」。系统会自动滚动并捕获完整对话上下文。
- **直接录入文本**：将文本直接粘贴到扩展中，立即处理。
- **PDF 提取**：上传本地 PDF 文件，解析并索引到本地 **向量存储（vector store）**。

#### 3. 生成优化大纲
输入课程信息（课程名称、考试大纲、考试类型）。系统会分析整个知识库，提取核心主题与高考试相关内容。  
*注意：处理时长会随录入数据量增加而增长。*

#### 4. 配置并生成速查表
选择你需要的主题，并根据学习目标设置页数限制：
- **1 面**：生存模式（仅保留核心公式/定义）。
- **1 页**：紧凑推导模式。
- **2 页**：综合复习模式。
- **无限制**：详细学习指南（含示例）。

#### 5. 导出 PDF
当 **RAG 流程（RAG pipeline）** 完成后，点击 **「Download PDF」**，即可导出为适合打印的专业双栏 A4 速查表。

---

<a id="technical-documentation"></a>
## 🛠️ Engineering Deep-Dive (Technical Highlights)

This project is a production-grade AI Agent infrastructure designed to handle high-concurrency PDF generation and intensive RAG workflows. Below are the core engineering challenges resolved during development.

### 1. Robust Infrastructure & System-Level Reliability
* **The Docker PID 1 Zombie Reaping Problem**: 
    * **Challenge**: In the worker containers, headless Chromium (via Playwright) frequently left "zombie" processes after rendering, eventually leading to PID exhaustion and container crashes.
    * **Solution**: Implemented a custom `init` process to properly reap defunct child processes. Integrated `tini` for correct Unix signal forwarding (SIGTERM/SIGINT), ensuring zero-downtime scaling and clean resource deallocation.
* **High-Concurrency Task Pipeline**: 
    * **Architecture**: Designed a **Producer-Consumer pattern** using **FastAPI (asyncio)** and **ARQ (Redis-backed)**.
    * **Optimization**: Implemented **Read-after-write consistency** for asynchronous vector indexing using Batch-ID tracking, ensuring that users can immediately query newly ingested knowledge without race conditions.

### 2. High-Performance RAG Architecture
* **Latency Reduction (15s → 3s)**: 
    * **Bottleneck**: Linear sequential processing of multi-topic RAG searches caused significant UX friction.
    * **Solution**: Orchestrated an asynchronous retrieval pipeline using `asyncio.gather` for parallel vector searches. Optimized the **MMR (Maximal Marginal Relevance)** algorithm to balance information density and diversity, reducing LLM token redundancy by 40%.
* **Vector Search Strategy**: 
    * Utilized **MongoDB Atlas Vector Search** with 1536-D embeddings.
    * Implemented **Hash-based Fingerprinting** for content deduplication at the ingestion layer, preventing duplicate context from bloating the prompt window and causing hallucinations.

### 3. Distributed System Design & Data Integrity
* **Idempotent Task Processing**: 
    * Leveraged **Redis-based distributed locking** and task-state machines (QUEUING → PROCESSING → COMPLETED) to prevent duplicate generation during network retries.
* **Cloud Infrastructure**: 
    * **AWS S3 + Presigned URLs**: Implemented a secure, short-lived presigned URL strategy for PDF delivery, decoupling file storage from the API server to reduce egress load and improve security.
    * **Rate Limiting**: Engineered a quota-based rate limiter to handle burst traffic of up to **1,000 RPM** during peak launch periods.

### 4. Technical Stack
* **Backend**: Python 3.10+, FastAPI (Asynchronous Framework), Pydantic v2 (Data Validation).
* **AI Engine**: LangChain, Google Gemini 2.5 Flash, OpenAI Embeddings.
* **Infrastructure**: Redis (Task Queue), MongoDB (Persistence & Vector Store), AWS S3 (Object Storage), Docker.
* **Frontend**: React 18, TypeScript, KaTeX (LaTeX rendering).

### 5. Quality Gates
* **Automated Tests**: `pytest` covers domain logic, API contracts, task status flow, and LLM retry behavior.
* **Continuous Integration**: GitHub Actions runs `pip check`, `ruff`, `black --check`, smoke imports, and `pytest` on backend changes and pull requests.
