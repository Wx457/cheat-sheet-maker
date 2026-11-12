import { Suspense } from 'react'
import { SignUp } from '@clerk/nextjs'

// 同 sign-in：<SignUp /> 内部调用 usePathname()，cacheComponents 下需要 Suspense 边界
export default function SignUpPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-50 dark:bg-zinc-950 px-4">
      <Suspense fallback={null}>
        <SignUp />
      </Suspense>
    </main>
  )
}
