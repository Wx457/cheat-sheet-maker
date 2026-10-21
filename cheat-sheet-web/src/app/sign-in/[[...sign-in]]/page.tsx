import { SignIn } from '@clerk/nextjs'

// 插件的 "Sign in" 按钮打开此页；登录后插件经 syncHost 自动取得同一会话
export default function SignInPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-950 px-4">
      <SignIn />
    </main>
  )
}
