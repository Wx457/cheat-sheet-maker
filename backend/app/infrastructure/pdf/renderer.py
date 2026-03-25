"""
PDF 渲染（Infra）
使用 Playwright 访问 React 静态页面并注入数据生成 PDF。
"""

import json
from typing import Any, Dict

from playwright.async_api import async_playwright

from app.core.config import settings

# 前端 URL 配置（使用 HashRouter，所以是 #/print）
# 现在使用 Vite 多入口构建：
# - /static/index.html  -> 纯静态展示页
# - /static/render.html -> React 渲染器（给 Playwright 使用）
# 从配置读取后端服务器地址，Worker 进程需要能够访问到 FastAPI 服务器
FRONTEND_URL = f"{settings.PDF_GENERATION_HOST}/static/render.html#/print"


async def generate_pdf_via_browser(data_json: Dict[str, Any]) -> bytes:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--disable-gpu",
            ],
        )

        try:
            page = await browser.new_page(
                viewport={"width": 1920, "height": 1080}, device_scale_factor=1
            )

            await page.goto(FRONTEND_URL, wait_until="networkidle", timeout=30000)

            await page.evaluate(
                f"window.CHEAT_SHEET_DATA = {json.dumps(data_json, ensure_ascii=False)}"
            )

            try:
                await page.wait_for_selector("#render-complete", state="attached", timeout=10000)
            except Exception as exc:  # noqa: PERF203
                print(
                    f"⚠️ Warning: Render completion marker (#render-complete) not detected, continuing PDF generation: {exc}"
                )

            await page.wait_for_timeout(1000)

            pdf_bytes = await page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "0mm", "right": "0mm", "bottom": "0mm", "left": "0mm"},
            )
            return pdf_bytes
        finally:
            await browser.close()
