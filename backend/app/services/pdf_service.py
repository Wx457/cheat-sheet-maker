"""
PDF 生成服务
使用 Playwright 访问 React 静态页面并注入数据生成 PDF
"""
import json
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
    async with async_playwright() as p:
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
        try:
            page = await browser.new_page(
                viewport={'width': 1920, 'height': 1080},
                device_scale_factor=1,
            )
            
            # Step 1: 访问前端页面
            print(f"📄 访问前端页面: {FRONTEND_URL}")
            await page.goto(FRONTEND_URL, wait_until="networkidle", timeout=30000)
            
            # Step 2: 注入数据到 window.CHEAT_SHEET_DATA
            print(f"💉 注入数据到 window.CHEAT_SHEET_DATA")
            # 使用 evaluate 直接注入对象（Playwright 会自动序列化）
            await page.evaluate(f"window.CHEAT_SHEET_DATA = {json.dumps(data_json, ensure_ascii=False)}")
            
            # Step 3: 等待渲染完成（等待 #render-complete 标记出现）
            print("⏳ 等待页面渲染完成...")
            try:
                await page.wait_for_selector("#render-complete", timeout=10000)
                print("✅ 页面渲染完成标记已检测到")
            except Exception as e:
                print(f"⚠️ 警告: 未检测到渲染完成标记 (#render-complete)，继续生成 PDF: {e}")
            
            # Step 4: 额外等待一小段时间，确保 KaTeX 等动态内容完全渲染
            await page.wait_for_timeout(1000)
            
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
            print(f"✅ PDF 生成完成，大小: {len(pdf_bytes)} bytes")
            return pdf_bytes
            
        finally:
            await browser.close()


# 保留旧函数以保持向后兼容（如果还有其他地方调用）
async def generate_pdf_from_html(html_content: str) -> bytes:
    """
    从 HTML 内容直接生成 PDF（已废弃，建议使用 generate_pdf_via_browser）
    
    Args:
        html_content: 完整的 HTML 字符串
        
    Returns:
        PDF 文件的二进制数据
        
    Deprecated:
        此方法已废弃，请使用 generate_pdf_via_browser 方法
    """
    print("⚠️ 警告: generate_pdf_from_html 已废弃，请使用 generate_pdf_via_browser")
    
    async with async_playwright() as p:
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
        try:
            page = await browser.new_page()
            await page.set_content(html_content, wait_until="networkidle")
            
            try:
                await page.wait_for_selector('.katex', timeout=2000)
            except:
                print("⚠️ 警告: 页面中未检测到已渲染的 KaTeX 公式")
            
            await page.wait_for_timeout(1000)

            pdf_bytes = await page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"}
            )
            return pdf_bytes
        finally:
            await browser.close()


class PDFService:
    """PDF 生成服务类（已废弃，建议直接使用 generate_pdf_via_browser 函数）"""
    
    def __init__(self):
        """初始化 PDF 服务"""
        self._browser: Optional[Browser] = None
        self._playwright = None
    
    async def _ensure_browser(self):
        """确保浏览器已启动（单例模式）"""
        if self._browser is None or not self._browser.is_connected():
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    '--no-sandbox',
                    '--disable-setuid-sandbox',
                    '--disable-dev-shm-usage',
                    '--disable-accelerated-2d-canvas',
                    '--disable-gpu',
                ]
            )
    
    async def generate_pdf_from_url(self, url: str) -> bytes:
        """
        从 URL 生成 PDF
        
        Args:
            url: 要转换为 PDF 的网页 URL
            
        Returns:
            PDF 文件的二进制数据
            
        Note:
            每次请求都会创建一个新的 context，确保并发安全
        """
        await self._ensure_browser()
        
        context: BrowserContext = await self._browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            device_scale_factor=1,
        )
        
        try:
            page: Page = await context.new_page()
            
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
                await page.wait_for_timeout(1000)
                
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
                
                return pdf_bytes
                
            finally:
                await page.close()
                
        finally:
            await context.close()
    
    async def close(self):
        """关闭浏览器实例"""
        if self._browser:
            await self._browser.close()
            self._browser = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


# 全局单例实例
_pdf_service: Optional[PDFService] = None


def get_pdf_service() -> PDFService:
    """获取 PDF 服务单例"""
    global _pdf_service
    if _pdf_service is None:
        _pdf_service = PDFService()
    return _pdf_service
