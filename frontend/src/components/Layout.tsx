import { useState } from 'react'
import { Outlet, NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Server,
  Layers,
  ScrollText,
  Zap,
  Menu,
  X
} from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { to: '/dashboard', icon: LayoutDashboard, label: '仪表盘' },
  { to: '/providers', icon: Server, label: '服务商' },
  { to: '/pools', icon: Layers, label: '模型池' },
  { to: '/logs', icon: ScrollText, label: '日志' },
]

export default function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex h-screen bg-surface-50 dark:bg-surface-900">
      {/* 移动端遮罩 */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* 侧边栏 */}
      <aside className={clsx(
        'fixed lg:static inset-y-0 left-0 z-50 w-64 bg-white dark:bg-surface-800 border-r border-surface-200 dark:border-surface-700 flex flex-col transform transition-transform duration-200 ease-in-out',
        sidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'
      )}>
        {/* Logo */}
        <div className="h-14 flex items-center justify-between px-4 border-b border-surface-200 dark:border-surface-700">
          <div className="flex items-center">
            <Zap className="w-7 h-7 text-primary-500" />
            <span className="ml-2 text-base font-semibold text-surface-900 dark:text-white">
              Pool Gateway
            </span>
          </div>
          <button
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden p-2 hover:bg-surface-100 dark:hover:bg-surface-700 rounded-lg"
          >
            <X className="w-5 h-5 text-surface-500" />
          </button>
        </div>

        {/* 导航 */}
        <nav className="flex-1 px-3 py-4 space-y-1">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              onClick={() => setSidebarOpen(false)}
              className={({ isActive }) => clsx(
                'flex items-center px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-primary-50 text-primary-700 dark:bg-primary-900/20 dark:text-primary-400'
                  : 'text-surface-600 hover:bg-surface-100 dark:text-surface-400 dark:hover:bg-surface-700'
              )}
            >
              <Icon className="w-5 h-5 mr-3" />
              {label}
            </NavLink>
          ))}
        </nav>

        {/* 底部信息 */}
        <div className="px-4 py-3 border-t border-surface-200 dark:border-surface-700">
          <p className="text-xs text-surface-500">
            API Pool Gateway v1.0
          </p>
        </div>
      </aside>

      {/* 主内容区 */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* 移动端顶部导航 */}
        <header className="lg:hidden h-14 bg-white dark:bg-surface-800 border-b border-surface-200 dark:border-surface-700 flex items-center px-4">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 -ml-2 hover:bg-surface-100 dark:hover:bg-surface-700 rounded-lg"
          >
            <Menu className="w-5 h-5 text-surface-600 dark:text-surface-400" />
          </button>
          <div className="flex items-center ml-3">
            <Zap className="w-6 h-6 text-primary-500" />
            <span className="ml-2 font-semibold text-surface-900 dark:text-white">
              Pool Gateway
            </span>
          </div>
        </header>

        {/* 页面内容 */}
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
