'use client'

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'
import { useAuth } from '@clerk/nextjs'

// 打开即登出，然后回到 /sign-in。插件 side panel 的 "Sign out" 按钮打开此页（登录 / 登出都只在 webapp 发生）
export default function SignOutPage() {
  const { isLoaded, isSignedIn, signOut } = useAuth()
  const router = useRouter()
  const started = useRef(false)

  useEffect(() => {
    if (!isLoaded || started.current) return
    started.current = true
    if (isSignedIn) {
      void signOut({ redirectUrl: '/sign-in' })
    } else {
      router.replace('/sign-in')
    }
  }, [isLoaded, isSignedIn, signOut, router])

  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-950 px-4">
      <p className="text-sm text-zinc-500 dark:text-zinc-400">Signing out…</p>
    </main>
  )
}
