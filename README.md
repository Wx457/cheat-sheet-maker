# Cheat Sheet Maker / 速查表生成器

**English** | [中文](#中文)

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

### 📖 User Guide

#### Step 1: Install Chrome Extension

1. Open Chrome browser
2. Navigate to `chrome://extensions/`
3. Enable "Developer mode" (toggle in top right)
4. Click "Load unpacked"
5. Select the `chrome-extension` folder

#### Step 2: Build Your Knowledge Base

You can use any combination of the following methods:

**Method A: Scan Web Pages**
1. Open a GPT web chat window
2. Click the extension icon
3. Click "Scan & Add to KB"
4. The extension will automatically scroll through the conversation to capture all content
5. **Important Notes**:
   - The extension is designed to work with GPT web chat windows
   - For long conversations, the sidebar should automatically scroll - if you don't see scrolling, refresh the page and try again
   - If page scanning fails, you can right-click on a blank area of the webpage, select "Print", save as PDF, and upload it using Method C

**Method B: Paste Text**
1. Click the extension icon
2. Paste your text into the text area
3. Click "Paste & Add to KB"

**Method C: Upload PDF**
1. Click the extension icon
2. Click "Upload PDF"
3. Select your PDF file
4. The system will extract and process the content

**Tip**: You can switch between methods and scan multiple pages to build a comprehensive knowledge base!

#### Step 3: Generate Outline

1. Fill in the form:
   - **Course Name**: Name of your course/subject
   - **Syllabus** (optional): Exam syllabus or requirements
   - **Exam Type**: Quiz, Midterm, or Final
   - **Education Level**: Undergraduate or Graduate
2. Click "Generate Outline"
3. Wait for the system to analyze your knowledge base and extract topics
4. **Note**: Processing time increases with the amount of knowledge ingested - please be patient

#### Step 4: Select Topics & Generate Cheat Sheet

1. Review the generated topics
2. Select the topics you want to include (or select all)
3. Choose your page limit:
   - **1 Side**: Survival mode - core formulas only
   - **1 Page**: Compact derivation mode
   - **2 Pages**: Comprehensive mode
   - **Unlimited**: Detailed mode with examples
4. Click "Generate Cheat Sheet"
5. **Important**: Generation time increases with:
   - The amount of knowledge in your knowledge base
   - The selected page limit
   - Please be patient, as this process may take several minutes

#### Step 5: Download PDF

1. Once generation completes, click "Download PDF"
2. The PDF will open in a new tab
3. Save or print as needed

### ⚠️ Important Notes

- **Extension Compatibility**: The extension is designed to scan GPT web chat windows. For other websites, use text pasting or PDF upload methods.
- **Long Conversations**: For long chat windows, the sidebar should automatically scroll. If scrolling doesn't occur, refresh the page and try again.
- **Scanning Failures**: If page scanning fails, right-click on a blank area of the webpage, select "Print", save as PDF, and upload it through the extension.
- **Processing Time**: Both outline generation and cheat sheet generation take time. Processing time increases with:
  - The amount of knowledge ingested
  - The selected page limit
  - Please be patient and wait for the process to complete

### 🔄 Workflow Summary

```
1. Build Knowledge Base
   ├── Scan GPT web chat windows (multiple times)
   ├── Paste text content
   └── Upload PDF files
   
2. Generate Outline
   └── System extracts topics from knowledge base
   
3. Select Topics & Generate
   └── System creates personalized cheat sheet
   
4. Download PDF
   └── Get your study material!
```

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

### 📖 使用指南

#### 第一步：安装 Chrome 插件

1. 打开 Chrome 浏览器
2. 访问 `chrome://extensions/`
3. 开启"开发者模式"（右上角开关）
4. 点击"加载已解压的扩展程序"
5. 选择 `chrome-extension` 文件夹

#### 第二步：构建知识库

您可以使用以下任意组合方式：

**方式 A：扫描网页**
1. 打开 GPT 网页聊天窗口
2. 点击插件图标
3. 点击"扫描并添加到知识库"
4. 插件会自动滚动对话窗口以捕获所有内容
5. **重要提示**：
   - 插件设计用于扫描 GPT 网页聊天窗口
   - 对于长对话窗口，侧边栏应该自动滚动 - 如果没有观察到滚动，请刷新页面并重试
   - 如果扫描页面功能失效，可以在网页空白处鼠标右键选择"打印"，保存为 PDF，然后使用方法 C 上传

**方式 B：粘贴文本**
1. 点击插件图标
2. 将文本粘贴到文本区域
3. 点击"粘贴并添加到知识库"

**方式 C：上传 PDF**
1. 点击插件图标
2. 点击"上传 PDF"
3. 选择您的 PDF 文件
4. 系统将提取并处理内容

**提示**：您可以在不同方式之间切换，多次扫描网页，构建全面的知识库！

#### 第三步：生成大纲

1. 填写表单：
   - **课程名称**：您的课程/科目名称
   - **考试大纲**（可选）：考试大纲或要求
   - **考试类型**：小测验、期中或期末
   - **教育水平**：本科或研究生
2. 点击"生成大纲"
3. 等待系统分析您的知识库并提取主题

#### 第四步：选择主题并生成速查表

1. 查看生成的主题
2. 选择要包含的主题（或全选）
3. 选择页数限制：
   - **1 面**：生存模式 - 仅核心公式
   - **1 页**：紧凑推导模式
   - **2 页**：综合模式
   - **无限制**：详细模式，包含示例
4. 点击"生成速查表"

#### 第五步：下载 PDF

1. 生成完成后，点击"下载 PDF"
2. PDF 将在新标签页中打开
3. 根据需要保存或打印

### ⚠️ 重要提示

- **插件兼容性**：插件设计用于扫描 GPT 网页聊天窗口。对于其他网站，请使用文本粘贴或 PDF 上传方式。
- **长对话**：对于长聊天窗口，侧边栏应该在单击"Scan & Add to KB"按钮后自动滚动。如果没有观察到滚动，请刷新页面并重试。
- **扫描失败**：如果页面扫描功能失效，可以在网页空白处鼠标右键选择"打印"，保存为 PDF，然后通过PDF选项卡上传。
- **处理时间**：大纲生成和速查表生成都需要时间。处理时间随以下因素增加：
  - 录入的知识量
  - 选择的页数限制
  **请耐心等待过程完成**

### 🔄 工作流程总结

```
1. 构建知识库
   ├── 扫描 GPT 网页聊天窗口（多次）
   ├── 粘贴文本内容
   └── 上传 PDF 文件
   
2. 生成大纲
   └── 系统从知识库提取主题
   
3. 选择主题并生成
   └── 系统创建个性化速查表
   
4. 下载 PDF
   └── 获得您的学习材料！
```

---

## 🛠️ Technical Documentation / 技术文档

### Architecture Highlights

#### 1. **Producer-Consumer Pattern**
- **API Server (Producer)**: Receives HTTP requests, pushes tasks to Redis queue, returns `task_id` immediately
- **Worker Process (Consumer)**: Independent process consumes tasks from Redis queue, executes time-consuming operations (LLM, PDF, AWS S3 upload)
- **Benefits**: Fast API response, non-blocking, supports task retry and concurrency control, easy horizontal scaling

#### 2. **RAG (Retrieval-Augmented Generation)**
- **Vector Storage**: MongoDB Atlas Vector Search with 1536-dimensional embeddings (OpenAI `text-embedding-3-small`)
- **Retrieval Algorithms**:
  - Similarity Search: For outline generation
  - MMR (Maximal Marginal Relevance): For cheat sheet generation, reduces redundancy
- **Parallel Processing**: Uses `asyncio.gather` to parallelize multi-topic searches
- **Content Deduplication**: Hash-based fingerprinting to avoid duplicate content

#### 3. **Async Task Processing**
- **Task Queue**: ARQ (Async Redis Queue)
- **Workflow**: Client submits task → Gets `task_id` → Polls `/api/task/{task_id}` → Gets result and presigned download URL
- **Benefits**: Non-blocking API, supports long-running operations, easy to monitor and retry

#### 4. **PDF Generation**
- **Technology**: Playwright (Headless Chrome) renders React frontend
- **Process**: Worker process accesses FastAPI server → Renders React page → Generates PDF → Uploads to AWS S3
- **Configuration**: Uses `PDF_GENERATION_HOST` environment variable for flexible deployment

### Technology Stack

#### Backend
- **Framework**: FastAPI
- **Language**: Python 3.10+
- **Task Queue**: ARQ (Async Redis Queue)
- **Database**: MongoDB Atlas (Vector Search + Document Storage)
- **Object Storage**: AWS S3
- **Embedding**: OpenAI `text-embedding-3-small` (1536 dimensions)
- **LLM**: Google Gemini 2.5 Flash
- **PDF Processing**: Playwright
- **Text Processing**: LangChain

#### Frontend
- **Framework**: React 18.3
- **Language**: TypeScript 5.9
- **Build Tool**: Vite 7.2
- **Math Rendering**: KaTeX + react-latex-next

#### Chrome Extension
- **Manifest**: Version 3
- **Permissions**: activeTab, scripting
- **Features**: Web page content scraping, automatic scrolling for long conversations

### Performance Optimizations

1. **Parallel MMR Retrieval**: Multiple topic searches execute in parallel using `asyncio.gather`
2. **Content Deduplication**: Hash-based fingerprinting reduces redundant content
3. **MMR Algorithm**: Maximizes diversity while maintaining relevance
4. **Async Processing**: Non-blocking API with background task execution

### Key Design Decisions

1. **Separation of Concerns**: Clear layer separation (API → Application → Domain → Infrastructure)
2. **Scalability**: Producer-consumer pattern allows horizontal scaling of workers
3. **Flexibility**: Multiple knowledge ingestion methods support various use cases
4. **User Experience**: Async task processing prevents UI blocking, provides real-time status updates

For detailed architecture documentation, see [PROJECT_ARCHITECTURE.md](./PROJECT_ARCHITECTURE.md).

