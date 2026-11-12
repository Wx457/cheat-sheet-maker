'use client'

import Link from 'next/link'
import { SignIn, useAuth, useUser } from '@clerk/nextjs'

// 未登录 → Clerk 登录框；已登录 → 显示当前账号，可去编辑器或退出（插件的 "Sign in" 打开此页时不再困惑）
// 用客户端 hook 判断：@clerk/nextjs 7 移除了 <SignedIn>/<SignedOut>，服务端 <Show> 会读请求头，
// 在 cacheComponents 下让整页变成动态渲染
export default function SignInGate() {
  const { isLoaded, isSignedIn } = useAuth()
  const { user } = useUser()

  if (!isLoaded) return null
  if (!isSignedIn) return <SignIn />

  const email = user?.primaryEmailAddress?.emailAddress
  return (
    <div className="w-full max-w-sm rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-6 shadow-sm">
      <p className="text-sm text-zinc-500 dark:text-zinc-400">You are signed in as</p>
      <p className="mt-1 truncate text-base font-medium text-zinc-900 dark:text-zinc-50">
        {email || 'your account'}
      </p>
      <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
        The Chrome extension picks up this session automatically — reopen its side panel.
      </p>
      <div className="mt-5 flex gap-2">
        <Link href="/editor"
          className="flex-1 rounded-lg bg-zinc-900 dark:bg-zinc-50 px-3 py-2 text-center text-sm font-medium text-white dark:text-zinc-900 hover:bg-zinc-700 dark:hover:bg-zinc-200 transition-colors">
          Go to editor
        </Link>
        <Link href="/sign-out"
          className="flex-1 rounded-lg border border-zinc-300 dark:border-zinc-700 px-3 py-2 text-center text-sm text-zinc-700 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors">
          Sign out
        </Link>
      </div>
    </div>
  )
}
