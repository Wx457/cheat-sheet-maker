import { Suspense } from 'react'
import SignInGate from './SignInGate'

// 插件的 "Sign in" 按钮打开此页；登录后插件经 syncHost 自动取得同一会话
// <SignIn /> 内部调用 usePathname()：cacheComponents 下必须包在 Suspense 里，否则登出跳转到此页时报错（见 REPO.md）
export default function SignInPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-950 px-4">
      <Suspense fallback={null}>
        <SignInGate />
      </Suspense>
    </main>
  )
}
