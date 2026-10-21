/**
 * Next.js 16 Proxy（原 middleware.ts）— Clerk 鉴权（Phase 2）
 *
 * /editor 需要登录：未登录时重定向到 /sign-in，登录后回到原 URL（插件传入的参数保留）。
 * 插件与 webapp 共用同一个 Clerk 应用：插件通过 syncHost 读取这里建立的登录态。
 *
 * createRouteMatcher 已被 Clerk 标记为 deprecated，这里直接判断路径。
 */

import { clerkMiddleware } from '@clerk/nextjs/server'

export default clerkMiddleware(async (auth, req) => {
  if (req.nextUrl.pathname.startsWith('/editor')) {
    await auth.protect()
  }
})

export const config = {
  matcher: [
    // Skip Next.js internals and all static files, unless found in search params
    '/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)',
    // Always run for API routes
    '/(api|trpc)(.*)',
  ],
}
