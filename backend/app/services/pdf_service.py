"""
PDF 生成服务
使用 Playwright 访问 React 静态页面并注入数据生成 PDF
"""
import json
import time
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from typing import Optional, Dict, Any

from app.core.config import settings


# 前端 URL 配置（使用 HashRouter，所以是 #/print）
FRONTEND_URL = "http://localhost:8000/static/index.html#/print"


async def generate_pdf_via_browser(data_json: Dict[str, Any]) -> bytes:
    """
    通过访问 React 静态页面并注入数据生成 PDF
    
    Args:
        data_json: CheatSheet 数据的字典（包含 title, sections 等）
        
    Returns:
        PDF 文件的二进制数据
        
    Note:
        1. 访问本地托管的 React 应用
        2. 将数据注入到 window.CHEAT_SHEET_DATA
        3. 等待页面渲染完成（通过 #render-complete 标记）
        4. 生成 PDF
    """
    # ========== [性能监控 - 可删除] ==========
    pdf_start_time = time.time()
    # ========== [性能监控 - 可删除] ==========
    
    async with async_playwright() as p:
        # ========== [性能监控 - 可删除] ==========
        browser_start_time = time.time()
        # ========== [性能监控 - 可删除] ==========
        
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--disable-gpu',
            ]
        )
        
        # ========== [性能监控 - 可删除] ==========
        browser_elapsed = time.time() - browser_start_time
        print(f"⏱️ [性能监控] generate_pdf_via_browser - 启动浏览器耗时: {browser_elapsed:.2f} 秒")
        # ========== [性能监控 - 可删除] ==========
        
        try:
            page = await browser.new_page(
                viewport={'width': 1920, 'height': 1080},
                device_scale_factor=1,
            )
            
            # ========== [性能监控 - 可删除] ==========
            navigate_start_time = time.time()
            # ========== [性能监控 - 可删除] ==========
            
            # Step 1: 访问前端页面
            print(f"📄 访问前端页面: {FRONTEND_URL}")
            await page.goto(FRONTEND_URL, wait_until="networkidle", timeout=30000)
            
            # ========== [性能监控 - 可删除] ==========
            navigate_elapsed = time.time() - navigate_start_time
            print(f"⏱️ [性能监控] generate_pdf_via_browser - 页面导航耗时: {navigate_elapsed:.2f} 秒")
            # ========== [性能监控 - 可删除] ==========
            
            # Step 2: 注入数据到 window.CHEAT_SHEET_DATA
            print(f"💉 注入数据到 window.CHEAT_SHEET_DATA")
            # 使用 evaluate 直接注入对象（Playwright 会自动序列化）
            await page.evaluate(f"window.CHEAT_SHEET_DATA = {json.dumps(data_json, ensure_ascii=False)}")
            
            # ========== [性能监控 - 可删除] ==========
            render_start_time = time.time()
            # ========== [性能监控 - 可删除] ==========
            
            # Step 3: 等待渲染完成（等待 #render-complete 标记出现）
            print("⏳ 等待页面渲染完成...")
            try:
                await page.wait_for_selector("#render-complete", state="attached", timeout=10000)
                print("✅ 页面渲染完成标记已检测到")
            except Exception as e:
                print(f"⚠️ 警告: 未检测到渲染完成标记 (#render-complete)，继续生成 PDF: {e}")
            
            # Step 4: 额外等待一小段时间，确保 KaTeX 等动态内容完全渲染
            await page.wait_for_timeout(1000)
            
            # ========== [性能监控 - 可删除] ==========
            render_elapsed = time.time() - render_start_time
            print(f"⏱️ [性能监控] generate_pdf_via_browser - 页面渲染耗时: {render_elapsed:.2f} 秒")
            # ========== [性能监控 - 可删除] ==========
            
            # ========== [性能监控 - 可删除] ==========
            pdf_gen_start_time = time.time()
            # ========== [性能监控 - 可删除] ==========
            
            # Step 5: 生成 PDF
            print("📄 开始生成 PDF...")
            pdf_bytes = await page.pdf(
                format="A4",
                print_background=True,
                margin={
                    'top': '0mm',
                    'right': '0mm',
                    'bottom': '0mm',
                    'left': '0mm',
                }
            )
            
            # ========== [性能监控 - 可删除] ==========
            pdf_gen_elapsed = time.time() - pdf_gen_start_time
            print(f"⏱️ [性能监控] generate_pdf_via_browser - PDF 生成耗时: {pdf_gen_elapsed:.2f} 秒，大小: {len(pdf_bytes)} bytes")
            # ========== [性能监控 - 可删除] ==========
            
            # ========== [性能监控 - 可删除] ==========
            total_elapsed = time.time() - pdf_start_time
            print(f"⏱️ [性能监控] generate_pdf_via_browser - 总耗时: {total_elapsed:.2f} 秒")
            # ========== [性能监控 - 可删除] ==========
            
            print(f"✅ PDF 生成完成，大小: {len(pdf_bytes)} bytes")
            return pdf_bytes
            
        finally:
            await browser.close()
