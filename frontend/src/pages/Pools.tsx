import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Layers,
  Server,
  CheckCircle,
  XCircle,
  Snowflake,
  Trash2
} from 'lucide-react'
import clsx from 'clsx'
import { fetchPoolDetail, deleteEndpoint } from '../api/client'

const poolConfig = {
  tool: {
    label: '工具模型池',
    model: 'haiku',
    gradient: 'from-blue-500 to-cyan-500',
    bg: 'bg-blue-50 dark:bg-blue-900/20',
    text: 'text-blue-600 dark:text-blue-400',
  },
  normal: {
    label: '普通模型池',
    model: 'sonnet',
    gradient: 'from-purple-500 to-pink-500',
    bg: 'bg-purple-50 dark:bg-purple-900/20',
    text: 'text-purple-600 dark:text-purple-400',
  },
  advanced: {
    label: '高级模型池',
    model: 'opus',
    gradient: 'from-amber-500 to-orange-500',
    bg: 'bg-amber-50 dark:bg-amber-900/20',
    text: 'text-amber-600 dark:text-amber-400',
  },
}

export default function Pools() {
  const [activePool, setActivePool] = useState<'tool' | 'normal' | 'advanced'>('tool')

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 animate-fadeIn">
      {/* 页面标题 */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold text-surface-900 dark:text-white">
          模型池管理
        </h1>
        <p className="mt-1 text-sm text-surface-500">
          查看和管理三个模型池的端点分配
        </p>
      </div>

      {/* 池切换标签 */}
      <div className="flex flex-wrap gap-2">
        {(Object.keys(poolConfig) as Array<keyof typeof poolConfig>).map(poolType => (
          <button
            key={poolType}
            onClick={() => setActivePool(poolType)}
            className={clsx(
              'px-3 py-2 rounded-lg text-sm font-medium transition-colors',
              activePool === poolType
                ? `${poolConfig[poolType].bg} ${poolConfig[poolType].text}`
                : 'text-surface-500 hover:bg-surface-100 dark:hover:bg-surface-800'
            )}
          >
            {poolConfig[poolType].label}
          </button>
        ))}
      </div>

      {/* 池详情 */}
      <PoolDetailView poolType={activePool} />
    </div>
  )
}

function PoolDetailView({ poolType }: { poolType: 'tool' | 'normal' | 'advanced' }) {
  const queryClient = useQueryClient()
  const config = poolConfig[poolType]

  const { data: poolDetail, isLoading } = useQuery({
    queryKey: ['pool', poolType],
    queryFn: () => fetchPoolDetail(poolType),
    refetchInterval: 5000,
  })

  const deleteMutation = useMutation({
    mutationFn: deleteEndpoint,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pool', poolType] })
      queryClient.invalidateQueries({ queryKey: ['pools'] })
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  if (!poolDetail || poolDetail.providers.length === 0) {
    return (
      <div className="text-center py-12 bg-white dark:bg-surface-800 rounded-xl border border-surface-200 dark:border-surface-700">
        <Layers className="w-12 h-12 text-surface-300 mx-auto mb-4" />
        <p className="text-surface-500">该池还没有添加任何模型</p>
        <p className="text-sm text-surface-400 mt-2">
          前往「服务商」页面，拉取模型并添加到此池
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* 池信息卡片 */}
      <div className="bg-white dark:bg-surface-800 rounded-xl border border-surface-200 dark:border-surface-700 overflow-hidden">
        <div className={clsx('h-1.5 sm:h-2 bg-gradient-to-r', config.gradient)} />
        <div className="p-4 sm:p-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <h2 className="text-lg sm:text-xl font-semibold text-surface-900 dark:text-white">
                {config.label}
              </h2>
              <p className="text-xs sm:text-sm text-surface-500 mt-1">
                虚拟模型名: <code className="px-2 py-0.5 bg-surface-100 dark:bg-surface-700 rounded">{config.model}</code>
              </p>
            </div>
            <div className="text-left sm:text-right">
              <p className="text-xl sm:text-2xl font-bold text-surface-900 dark:text-white">
                {poolDetail.providers.reduce((acc, p) => acc + p.healthy_count, 0)}
                <span className="text-surface-400 text-base sm:text-lg font-normal">
                  {' / '}
                  {poolDetail.providers.reduce((acc, p) => acc + p.total_count, 0)}
                </span>
              </p>
              <p className="text-xs sm:text-sm text-surface-500">健康端点</p>
            </div>
          </div>
        </div>
      </div>

      {/* 按服务商分组的端点列表 */}
      <div className="space-y-4">
        {poolDetail.providers.map(provider => (
          <div
            key={provider.provider_id}
            className="bg-white dark:bg-surface-800 rounded-xl border border-surface-200 dark:border-surface-700"
          >
            {/* 服务商头部 */}
            <div className="p-3 sm:p-4 border-b border-surface-200 dark:border-surface-700">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                <div className="flex items-center space-x-2 sm:space-x-3 min-w-0">
                  <Server className="w-4 h-4 sm:w-5 sm:h-5 text-surface-400" />
                  <div className="min-w-0">
                    <span className="font-medium text-sm sm:text-base text-surface-900 dark:text-white truncate">
                      {provider.provider_name}
                    </span>
                    <span className="ml-2 text-xs text-surface-500 font-mono">
                      {provider.api_format.toUpperCase()}
                    </span>
                  </div>
                </div>
                <span className={clsx(
                  'px-2 py-0.5 sm:px-2.5 sm:py-1 rounded-full text-xs font-medium',
                  provider.healthy_count === provider.total_count
                    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                    : provider.healthy_count > 0
                    ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400'
                    : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                )}>
                  {provider.healthy_count} / {provider.total_count} 健康
                </span>
              </div>
            </div>

            {/* 模型列表 */}
            <div className="divide-y divide-surface-100 dark:divide-surface-700">
              {provider.models.map(model => (
                <div
                  key={model.id}
                  className="p-3 sm:p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 hover:bg-surface-50 dark:hover:bg-surface-700/50 transition-colors"
                >
                  <div className="flex items-start sm:items-center space-x-3 sm:space-x-4 min-w-0">
                    {/* 状态图标 */}
                    {model.is_cooling ? (
                      <div className="p-2 bg-blue-50 dark:bg-blue-900/20 rounded-lg flex-shrink-0">
                        <Snowflake className="w-4 h-4 text-blue-500 animate-pulse-subtle" />
                      </div>
                    ) : model.enabled ? (
                      <div className="p-2 bg-green-50 dark:bg-green-900/20 rounded-lg flex-shrink-0">
                        <CheckCircle className="w-4 h-4 text-green-500" />
                      </div>
                    ) : (
                      <div className="p-2 bg-red-50 dark:bg-red-900/20 rounded-lg flex-shrink-0">
                        <XCircle className="w-4 h-4 text-red-500" />
                      </div>
                    )}

                    {/* 模型信息 */}
                    <div className="min-w-0">
                      <p className="font-mono text-xs sm:text-sm text-surface-900 dark:text-white truncate">
                        {model.model_id}
                      </p>
                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1">
                        {model.is_cooling && (
                          <span className="text-xs text-blue-500">
                            冷却中 ({model.cooldown_remaining}s)
                          </span>
                        )}
                        <span className="text-xs text-surface-500">
                          成功率 {model.success_rate}%
                        </span>
                        <span className="text-xs text-surface-500">
                          延迟 {Math.round(model.avg_latency_ms)}ms
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* 统计和操作 */}
                  <div className="flex items-center justify-between sm:justify-end gap-3">
                    <div className="text-left sm:text-right text-xs sm:text-sm">
                      <p className="text-surface-900 dark:text-white">
                        {model.total_requests.toLocaleString()}
                      </p>
                      <p className="text-xs text-surface-500">请求</p>
                    </div>

                    <button
                      onClick={() => deleteMutation.mutate(model.id)}
                      className="p-2 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                      title="从池中移除"
                    >
                      <Trash2 className="w-4 h-4 text-red-500" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
