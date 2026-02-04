import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  Server,
  Layers,
  CheckCircle
} from 'lucide-react'
import { fetchStats, fetchPools } from '../api/client'
import clsx from 'clsx'

export default function Dashboard() {
  const { data: stats, isLoading: statsLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: fetchStats,
    refetchInterval: 5000,
  })

  const { data: pools } = useQuery({
    queryKey: ['pools'],
    queryFn: fetchPools,
    refetchInterval: 5000,
  })

  if (statsLoading) {
    return (
      <div className="p-8 flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-6 animate-fadeIn">
      {/* 页面标题 */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-surface-900 dark:text-white">
          仪表盘
        </h1>
        <p className="mt-1 text-sm text-surface-500">
          实时监控 API 池状态和请求统计
        </p>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 lg:gap-6">
        <StatCard
          title="服务商"
          value={`${stats?.enabled_providers ?? 0} / ${stats?.total_providers ?? 0}`}
          subtitle="启用 / 总数"
          icon={Server}
          color="blue"
        />
        <StatCard
          title="模型端点"
          value={`${stats?.healthy_endpoints ?? 0} / ${stats?.total_endpoints ?? 0}`}
          subtitle={`${stats?.cooling_endpoints ?? 0} 个冷却中`}
          icon={Layers}
          color="green"
        />
        <StatCard
          title="总请求数"
          value={stats?.total_requests?.toLocaleString() ?? '0'}
          subtitle={`成功率 ${stats?.success_rate ?? 0}%`}
          icon={Activity}
          color="purple"
        />
        <StatCard
          title="请求状态"
          value={stats?.success_requests?.toLocaleString() ?? '0'}
          subtitle={`失败 ${stats?.error_requests?.toLocaleString() ?? '0'}`}
          icon={CheckCircle}
          color="emerald"
        />
      </div>

      {/* 池状态 */}
      <div>
        <h2 className="text-base sm:text-lg font-semibold text-surface-900 dark:text-white mb-3 sm:mb-4">
          模型池状态
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4 lg:gap-6">
          {pools?.map(pool => (
            <PoolCard key={pool.pool_type} pool={pool} />
          ))}
        </div>
      </div>

      {/* 快速配置指南 */}
      <div className="bg-white dark:bg-surface-800 rounded-xl border border-surface-200 dark:border-surface-700 p-4 sm:p-6">
        <h2 className="text-base sm:text-lg font-semibold text-surface-900 dark:text-white mb-3 sm:mb-4">
          Claude Code 配置
        </h2>
        <div className="bg-surface-50 dark:bg-surface-900 rounded-lg p-3 sm:p-4 font-mono text-xs sm:text-sm overflow-x-auto">
          <pre className="text-surface-700 dark:text-surface-300">
{`// ~/.claude/settings.json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8899",
    "ANTHROPIC_API_KEY": "任意值"
  }
}`}
          </pre>
        </div>
        <p className="mt-4 text-sm text-surface-500">
          配置后，Claude Code 请求 <code className="px-1 py-0.5 bg-surface-100 dark:bg-surface-700 rounded">haiku</code>、
          <code className="px-1 py-0.5 bg-surface-100 dark:bg-surface-700 rounded">sonnet</code>、
          <code className="px-1 py-0.5 bg-surface-100 dark:bg-surface-700 rounded">opus</code>
          将自动路由到对应池并轮询。
        </p>
      </div>
    </div>
  )
}

function StatCard({
  title,
  value,
  subtitle,
  icon: Icon,
  color,
}: {
  title: string
  value: string
  subtitle: string
  icon: React.ElementType
  color: 'blue' | 'green' | 'purple' | 'emerald'
}) {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400',
    green: 'bg-green-50 text-green-600 dark:bg-green-900/20 dark:text-green-400',
    purple: 'bg-purple-50 text-purple-600 dark:bg-purple-900/20 dark:text-purple-400',
    emerald: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/20 dark:text-emerald-400',
  }

  return (
    <div className="bg-white dark:bg-surface-800 rounded-xl border border-surface-200 dark:border-surface-700 p-4 sm:p-6">
      <div className="flex items-center justify-between">
        <div className="min-w-0 flex-1">
          <p className="text-xs sm:text-sm font-medium text-surface-500 truncate">{title}</p>
          <p className="mt-1 sm:mt-2 text-xl sm:text-2xl lg:text-3xl font-bold text-surface-900 dark:text-white">
            {value}
          </p>
          <p className="mt-0.5 sm:mt-1 text-xs sm:text-sm text-surface-500 truncate">{subtitle}</p>
        </div>
        <div className={clsx('p-2 sm:p-3 rounded-xl ml-2 flex-shrink-0', colorClasses[color])}>
          <Icon className="w-5 h-5 sm:w-6 sm:h-6" />
        </div>
      </div>
    </div>
  )
}

function PoolCard({ pool }: { pool: { pool_type: string; virtual_model_name: string; endpoint_count: number; healthy_endpoint_count: number; provider_count: number } }) {
  const poolLabels: Record<string, string> = {
    tool: '工具模型池',
    normal: '普通模型池',
    advanced: '高级模型池',
  }

  const poolColors: Record<string, string> = {
    tool: 'from-blue-500 to-cyan-500',
    normal: 'from-purple-500 to-pink-500',
    advanced: 'from-amber-500 to-orange-500',
  }

  const healthPercent = pool.endpoint_count > 0
    ? Math.round((pool.healthy_endpoint_count / pool.endpoint_count) * 100)
    : 0

  return (
    <div className="bg-white dark:bg-surface-800 rounded-xl border border-surface-200 dark:border-surface-700 overflow-hidden">
      {/* 渐变头部 */}
      <div className={clsx('h-1.5 sm:h-2 bg-gradient-to-r', poolColors[pool.pool_type])} />

      <div className="p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3 sm:mb-4">
          <div className="min-w-0 flex-1">
            <h3 className="font-semibold text-sm sm:text-base text-surface-900 dark:text-white truncate">
              {poolLabels[pool.pool_type] ?? pool.pool_type}
            </h3>
            <p className="text-xs sm:text-sm text-surface-500 font-mono truncate">
              model: {pool.virtual_model_name}
            </p>
          </div>
          <div className={clsx(
            'px-2 py-0.5 sm:px-3 sm:py-1 rounded-full text-xs font-medium ml-2 flex-shrink-0',
            healthPercent >= 80
              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
              : healthPercent >= 50
              ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
              : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
          )}>
            {healthPercent}% 健康
          </div>
        </div>

        <div className="space-y-2 sm:space-y-3">
          <div className="flex justify-between text-xs sm:text-sm">
            <span className="text-surface-500">服务商</span>
            <span className="font-medium text-surface-900 dark:text-white">
              {pool.provider_count} 个
            </span>
          </div>
          <div className="flex justify-between text-xs sm:text-sm">
            <span className="text-surface-500">模型端点</span>
            <span className="font-medium text-surface-900 dark:text-white">
              {pool.healthy_endpoint_count} / {pool.endpoint_count}
            </span>
          </div>
          {/* 进度条 */}
          <div className="h-1.5 sm:h-2 bg-surface-100 dark:bg-surface-700 rounded-full overflow-hidden">
            <div
              className={clsx('h-full rounded-full bg-gradient-to-r', poolColors[pool.pool_type])}
              style={{ width: `${healthPercent}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
