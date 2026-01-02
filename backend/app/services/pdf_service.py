"""
PDF 生成服务
使用 Playwright 调用 Headless Chrome 将网页转换为 PDF
"""
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from typing import Optional


class PDFService:
    """PDF 生成服务类"""
    
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
        # 确保浏览器已启动
        await self._ensure_browser()
        
        # 为每个请求创建新的 context，确保并发安全
        context: BrowserContext = await self._browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            device_scale_factor=1,
        )
        
        try:
            # 创建新页面
            page: Page = await context.new_page()
            
            try:
                # 访问 URL 并等待页面加载完成
                await page.goto(url, wait_until="networkidle", timeout=30000)
                
                # 等待一小段时间，确保所有动态内容都已渲染
                await page.wait_for_timeout(1000)
                
                # 生成 PDF
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
                # 关闭页面
                await page.close()
                
        finally:
            # 关闭 context（重要：确保资源释放）
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

