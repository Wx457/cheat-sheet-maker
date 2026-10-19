import { redirect } from 'next/navigation'

/**
 * 根路径 "/" 直接重定向到编辑器页面。
 * redirect() 在 Server Component 中执行，不产生客户端 JS。
 */
export default function Home() {
  redirect('/editor')
}
