# Cheat Sheet RAG Clipper / 速查表生成器 Chrome 扩展

**English** | [中文](#中文)

---

## English

### Overview

Chrome extension for Cheat Sheet Maker that enables knowledge base building through web page scanning, text pasting, and PDF upload. The extension integrates with the backend API to ingest content and generate personalized cheat sheets.

### Features

#### 1. **Multiple Knowledge Ingestion Methods**
- **Web Page Scanning**: Automatically scrolls and captures GPT web chat window content
- **Text Pasting**: Directly paste text content into the extension
- **PDF Upload**: Upload PDF files for knowledge extraction
- **Mixed Mode**: Combine all methods to build a comprehensive knowledge base

#### 2. **Intelligent Content Capture**
- **Auto-Scrolling**: Automatically scrolls through long conversations to capture all content
- **Content Deduplication**: Prevents duplicate content from being saved
- **Form Persistence**: Automatically saves and restores form data

#### 3. **Cheat Sheet Generation Workflow**
- **Outline Generation**: Analyzes knowledge base and extracts exam topics
- **Topic Selection**: Interactive topic selection interface
- **PDF Download**: Direct download of generated cheat sheets

### Installation

1. Open Chrome browser
2. Navigate to `chrome://extensions/`
3. Enable "Developer mode" (toggle in top right corner)
4. Click "Load unpacked"
5. Select the `chrome-extension` folder from this project

### Usage Guide

#### Step 1: Build Your Knowledge Base

**Method A: Scan Web Pages**
1. Open a GPT web chat window (e.g., ChatGPT, Claude, etc.)
2. Click the extension icon in the Chrome toolbar
3. The extension side panel will open
4. Click "Scan & Add to KB"
5. The extension will automatically:
   - Scroll through the conversation to capture all content
   - Extract text from all visible messages
   - Send the content to the backend for processing
6. **Important Notes**:
   - The extension is designed to work with GPT web chat windows
   - For long conversations, the sidebar should automatically scroll
   - If you don't see scrolling, refresh the page and try again
   - If page scanning fails, right-click on a blank area of the webpage, select "Print", save as PDF, and upload it using Method C

**Method B: Paste Text**
1. Click the extension icon
2. Paste your text into the "Paste Text" text area
3. Click "Paste & Add to KB"
4. The content will be sent to the backend for processing

**Method C: Upload PDF**
1. Click the extension icon
2. Click "Upload PDF"
3. Select your PDF file
4. The system will extract and process the content

**Tip**: You can switch between methods and scan multiple pages to build a comprehensive knowledge base!

#### Step 2: Generate Outline

1. Fill in the form:
   - **Course Name**: Name of your course/subject
   - **Syllabus** (optional): Exam syllabus or requirements
   - **Exam Type**: Quiz, Midterm, or Final
   - **Education Level**: Undergraduate or Graduate
2. Click "Generate Outline"
3. Wait for the system to analyze your knowledge base and extract topics
4. **Note**: Processing time increases with the amount of knowledge ingested - please be patient

#### Step 3: Select Topics & Generate Cheat Sheet

1. Review the generated topics in the checklist
2. Select the topics you want to include (or click "Select All")
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

#### Step 4: Download PDF

1. Once generation completes, click "Download PDF"
2. The PDF will open in a new tab
3. Save or print as needed

### Important Notes

- **Extension Compatibility**: The extension is designed to scan GPT web chat windows. For other websites, use text pasting or PDF upload methods.
- **Long Conversations**: For long chat windows, the sidebar should automatically scroll. If scrolling doesn't occur, refresh the page and try again.
- **Scanning Failures**: If page scanning fails, right-click on a blank area of the webpage, select "Print", save as PDF, and upload it through the extension.
- **Processing Time**: Both outline generation and cheat sheet generation take time. Processing time increases with:
  - The amount of knowledge ingested
  - The selected page limit
  - Please be patient and wait for the process to complete

### Technical Details

- **Manifest Version**: 3
- **Permissions**: 
  - `activeTab`: Access to the current active tab
  - `scripting`: Inject content scripts
  - `storage`: Store form data locally
  - `sidePanel`: Display extension UI in side panel
- **Content Script**: Automatically injected into all web pages to enable content scraping
- **Background Script**: Handles message passing between content script and extension UI
- **Form Persistence**: Automatically saves form data to Chrome storage for restoration

### Icon Files

The extension includes the following icon files:
- `icon16.png`, `icon32.png` (16x16, 32x32) - Toolbar icons
- `icon48.png` (48x48) - Extension management page
- `icon128.png` (128x128) - Chrome Web Store (if published)

---

## 中文

### 概述

速查表生成器的 Chrome 扩展，支持通过网页扫描、文本粘贴和 PDF 上传构建知识库。扩展与后端 API 集成，用于录入内容并生成个性化速查表。

### 功能

#### 1. **多种知识录入方式**
- **网页扫描**：自动滚动并捕获 GPT 网页聊天窗口内容
- **文本粘贴**：直接将文本内容粘贴到扩展中
- **PDF 上传**：上传 PDF 文件进行知识提取
- **混合模式**：结合所有方式构建全面的知识库

#### 2. **智能内容捕获**
- **自动滚动**：自动滚动长对话以捕获所有内容
- **内容去重**：防止重复内容被保存
- **表单持久化**：自动保存和恢复表单数据

#### 3. **速查表生成工作流**
- **大纲生成**：分析知识库并提取考试主题
- **主题选择**：交互式主题选择界面
- **PDF 下载**：直接下载生成的速查表

### 安装步骤

1. 打开 Chrome 浏览器
2. 访问 `chrome://extensions/`
3. 开启"开发者模式"（右上角开关）
4. 点击"加载已解压的扩展程序"
5. 选择项目中的 `chrome-extension` 文件夹

### 使用指南

#### 第一步：构建知识库

**方式 A：扫描网页**
1. 打开 GPT 网页聊天窗口（如 ChatGPT、Claude 等）
2. 点击 Chrome 工具栏中的扩展图标
3. 扩展侧边栏将打开
4. 点击"扫描并添加到知识库"
5. 扩展将自动：
   - 滚动对话窗口以捕获所有内容
   - 提取所有可见消息的文本
   - 将内容发送到后端进行处理
6. **重要提示**：
   - 扩展设计用于扫描 GPT 网页聊天窗口
   - 对于长对话窗口，侧边栏应该自动滚动
   - 如果没有观察到滚动，请刷新页面并重试
   - 如果页面扫描功能失效，可以在网页空白处鼠标右键选择"打印"，保存为 PDF，然后使用方法 C 上传

**方式 B：粘贴文本**
1. 点击扩展图标
2. 将文本粘贴到"粘贴文本"文本区域
3. 点击"粘贴并添加到知识库"
4. 内容将被发送到后端进行处理

**方式 C：上传 PDF**
1. 点击扩展图标
2. 点击"上传 PDF"
3. 选择您的 PDF 文件
4. 系统将提取并处理内容

**提示**：您可以在不同方式之间切换，多次扫描网页，构建全面的知识库！

#### 第二步：生成大纲

1. 填写表单：
   - **课程名称**：您的课程/科目名称
   - **考试大纲**（可选）：考试大纲或要求
   - **考试类型**：小测验、期中或期末
   - **教育水平**：本科或研究生
2. 点击"生成大纲"
3. 等待系统分析您的知识库并提取主题
4. **注意**：处理时间随录入知识量增加而增加 - 请耐心等待

#### 第三步：选择主题并生成速查表

1. 查看复选框列表中生成的主题
2. 选择要包含的主题（或点击"全选"）
3. 选择页数限制：
   - **1 面**：生存模式 - 仅核心公式
   - **1 页**：紧凑推导模式
   - **2 页**：综合模式
   - **无限制**：详细模式，包含示例
4. 点击"生成速查表"
5. **重要提示**：生成时间随以下因素增加：
   - 知识库中的知识量
   - 选择的页数限制
   - 请耐心等待，此过程可能需要几分钟

#### 第四步：下载 PDF

1. 生成完成后，点击"下载 PDF"
2. PDF 将在新标签页中打开
3. 根据需要保存或打印

### 重要提示

- **扩展兼容性**：扩展设计用于扫描 GPT 网页聊天窗口。对于其他网站，请使用文本粘贴或 PDF 上传方式。
- **长对话**：对于长聊天窗口，侧边栏应该自动滚动。如果没有观察到滚动，请刷新页面并重试。
- **扫描失败**：如果页面扫描功能失效，可以在网页空白处鼠标右键选择"打印"，保存为 PDF，然后通过扩展上传。
- **处理时间**：大纲生成和速查表生成都需要时间。处理时间随以下因素增加：
  - 录入的知识量
  - 选择的页数限制
  - 请耐心等待过程完成

### 技术细节

- **清单版本**：3
- **权限**：
  - `activeTab`：访问当前活动标签页
  - `scripting`：注入内容脚本
  - `storage`：本地存储表单数据
  - `sidePanel`：在侧边栏显示扩展 UI
- **内容脚本**：自动注入到所有网页以启用内容抓取
- **后台脚本**：处理内容脚本和扩展 UI 之间的消息传递
- **表单持久化**：自动将表单数据保存到 Chrome 存储以便恢复

### 图标文件

扩展包含以下图标文件：
- `icon16.png`、`icon32.png` (16x16, 32x32) - 工具栏图标
- `icon48.png` (48x48) - 扩展管理页面
- `icon128.png` (128x128) - Chrome 网上应用店（如果发布）
