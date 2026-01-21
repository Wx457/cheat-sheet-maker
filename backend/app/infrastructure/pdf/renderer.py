"""
PDF 渲染（Infra）
使用 Playwright 访问 React 静态页面并注入数据生成 PDF。
"""

import json
import time
from typing import Any, Dict

from playwright.async_api import async_playwright


# 前端 URL 配置（使用 HashRouter，所以是 #/print）
FRONTEND_URL = "http://localhost:8000/static/index.html#/print"


async def generate_pdf_via_browser(data_json: Dict[str, Any]) -> bytes:
    pdf_start_time = time.time()

    async with async_playwright() as p:
        browser_start_time = time.time()
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
        print(f"⏱️ [性能监控] generate_pdf_via_browser - 启动浏览器耗时: {time.time() - browser_start_time:.2f} 秒")

        try:
            page = await browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)

            navigate_start_time = time.time()
            print(f"📄 访问前端页面: {FRONTEND_URL}")
            await page.goto(FRONTEND_URL, wait_until="networkidle", timeout=30000)
            print(f"⏱️ [性能监控] generate_pdf_via_browser - 页面导航耗时: {time.time() - navigate_start_time:.2f} 秒")

            print("💉 注入数据到 window.CHEAT_SHEET_DATA")
            await page.evaluate(f"window.CHEAT_SHEET_DATA = {json.dumps(data_json, ensure_ascii=False)}")

            render_start_time = time.time()
            print("⏳ 等待页面渲染完成...")
            try:
                await page.wait_for_selector("#render-complete", state="attached", timeout=10000)
                print("✅ 页面渲染完成标记已检测到")
            except Exception as exc:  # noqa: PERF203
                print(f"⚠️ 警告: 未检测到渲染完成标记 (#render-complete)，继续生成 PDF: {exc}")

            await page.wait_for_timeout(1000)
            print(f"⏱️ [性能监控] generate_pdf_via_browser - 页面渲染耗时: {time.time() - render_start_time:.2f} 秒")

            pdf_gen_start_time = time.time()
            print("📄 开始生成 PDF...")
            pdf_bytes = await page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "0mm", "right": "0mm", "bottom": "0mm", "left": "0mm"},
            )
            print(
                f"⏱️ [性能监控] generate_pdf_via_browser - PDF 生成耗时: {time.time() - pdf_gen_start_time:.2f} 秒，大小: {len(pdf_bytes)} bytes"
            )
            print(f"⏱️ [性能监控] generate_pdf_via_browser - 总耗时: {time.time() - pdf_start_time:.2f} 秒")
            return pdf_bytes
        finally:
            await browser.close()


