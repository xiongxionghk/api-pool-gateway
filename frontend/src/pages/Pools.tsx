import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Layers,
  Server,
  CheckCircle,
  XCircle,
  Snowflake,
  Settings,
  Trash2,
  Scale,
  Clock,
  Search
} from 'lucide-react'
import clsx from 'clsx'
import { fetchPoolDetail, deleteEndpoint, updatePoolConfig, updateEndpoint } from '../api/client'

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
  const [showSettings, setShowSettings] = useState(false)
  const [cooldown, setCooldown] = useState<string>('')
  const [reqTimeout, setReqTimeout] = useState<string>('')
  const [modelFilter, setModelFilter] = useState('')
  const [showDisabled, setShowDisabled] = useState(true)

  const { data: poolDetail, isLoading } = useQuery({
    queryKey: ['pool', poolType],
    queryFn: () => fetchPoolDetail(poolType),
    refetchInterval: 5000,
  })

  // 同步设置到本地状态
  if (poolDetail && !showSettings) {
    if (cooldown === '') setCooldown(poolDetail.cooldown_seconds.toString())
    if (reqTimeout === '') setReqTimeout((poolDetail.timeout_seconds || 60).toString())
  }

  const updateConfigMutation = useMutation({
    mutationFn: (data: { cooldown_seconds: number; timeout_seconds: number }) => updatePoolConfig(poolType, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pool', poolType] })
      queryClient.invalidateQueries({ queryKey: ['pools'] })
      setShowSettings(false)
    },
    onError: (error: any) => {
      alert(`更新失败: ${error?.response?.data?.detail || error.message || '未知错误'}`)
    },
  })

  const handleSaveSettings = () => {
    const cooldownSec = parseInt(cooldown)
    const timeoutSec = parseInt(reqTimeout)

    if (isNaN(cooldownSec) || cooldownSec < 0) {
      alert('请输入有效的冷却时间')
      return
    }
    if (isNaN(timeoutSec) || timeoutSec <= 0) {
      alert('请输入有效的超时时间')
      return
    }

    updateConfigMutation.mutate({
      cooldown_seconds: cooldownSec,
      timeout_seconds: timeoutSec
    })
  }

  const deleteMutation = useMutation({
    mutationFn: deleteEndpoint,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pool', poolType] })
      queryClient.invalidateQueries({ queryKey: ['pools'] })
    },
    onError: (error: any) => {
      alert(`删除失败: ${error?.response?.data?.detail || error.message || '未知错误'}`)
    },
  })

  const updateEndpointMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => updateEndpoint(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['pool', poolType] })
    },
    onError: (error: any) => {
      alert(`更新失败: ${error?.response?.data?.detail || error.message || '未知错误'}`)
    }
  })

  const handleDelete = (id: number, modelId: string) => {
    if (window.confirm(`确定要移除模型 "${modelId}" 吗？`)) {
      deleteMutation.mutate(id)
    }
  }

  // 根据搜索词和显示设置过滤模型
  const filteredProviders = useMemo(() => {
    if (!poolDetail) return []

    // 1. 处理过滤逻辑
    const result = poolDetail.providers
      .map(provider => {
        // 先按显示设置过滤
        let models = provider.models;
        if (!showDisabled) {
          models = models.filter(m => m.enabled);
        }

        // 再按搜索词过滤
        if (modelFilter.trim()) {
          const keyword = modelFilter.toLowerCase().trim()
          models = models.filter(m =>
            m.model_id.toLowerCase().includes(keyword) ||
            provider.provider_name.toLowerCase().includes(keyword)
          )
        }

        return {
          ...provider,
          models
        }
      })
      .filter(provider => provider.models.length > 0)

    return result;
  }, [poolDetail, modelFilter, showDisabled])

  // 计算总权重
  const totalWeight = filteredProviders.reduce(
    (acc, p) => acc + p.models.filter(m => m.enabled && !m.is_cooling).reduce((sum, m) => sum + m.weight, 0),
    0
  ) || 1

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
              <div className="flex items-center gap-2">
                <h2 className="text-lg sm:text-xl font-semibold text-surface-900 dark:text-white">
                  {config.label}
                </h2>
                <button
                  onClick={() => {
                    setShowSettings(!showSettings)
                    if (!showSettings && poolDetail) {
                      setCooldown(poolDetail.cooldown_seconds.toString())
                      setReqTimeout((poolDetail.timeout_seconds || 60).toString())
                    }
                  }}
                  className="p-1.5 text-surface-400 hover:text-primary-500 hover:bg-surface-100 dark:hover:bg-surface-700 rounded-lg transition-colors"
                  title="设置"
                >
                  <Settings className="w-4 h-4" />
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1 text-xs sm:text-sm text-surface-500">
                <span>
                  虚拟模型名: <code className="px-2 py-0.5 bg-surface-100 dark:bg-surface-700 rounded">{config.model}</code>
                </span>
                <span className="flex items-center gap-1">
                  冷却: <span className="font-medium text-surface-700 dark:text-surface-300">{poolDetail.cooldown_seconds}s</span>
                </span>
                <span className="flex items-center gap-1 border-l border-surface-300 dark:border-surface-600 pl-4">
                  超时: <span className="font-medium text-surface-700 dark:text-surface-300">{poolDetail.timeout_seconds || 60}s</span>
                </span>
              </div>

              {/* 设置面板 */}
              {showSettings && (
                <div className="mt-4 p-4 bg-surface-50 dark:bg-surface-900/50 rounded-lg border border-surface-200 dark:border-surface-700 animate-fadeIn">
                  <div className="flex items-end gap-4">
                    <div>
                      <label className="block text-xs font-medium text-surface-700 dark:text-surface-300 mb-1">
                        失败冷却 (秒)
                      </label>
                      <input
                        type="number"
                        min="0"
                        value={cooldown}
                        onChange={e => setCooldown(e.target.value)}
                        className="w-24 px-3 py-1.5 text-sm bg-white dark:bg-surface-800 border border-surface-300 dark:border-surface-600 rounded-lg focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-medium text-surface-700 dark:text-surface-300 mb-1">
                        请求超时 (秒)
                      </label>
                      <input
                        type="number"
                        min="1"
                        value={reqTimeout}
                        onChange={e => setReqTimeout(e.target.value)}
                        className="w-24 px-3 py-1.5 text-sm bg-white dark:bg-surface-800 border border-surface-300 dark:border-surface-600 rounded-lg focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500"
                      />
                    </div>
                    <div className="flex gap-2">
                      <button
                        onClick={handleSaveSettings}
                        disabled={updateConfigMutation.isPending}
                        className="px-3 py-1.5 bg-primary-500 hover:bg-primary-600 text-white text-sm rounded-lg transition-colors disabled:opacity-50"
                      >
                        {updateConfigMutation.isPending ? '保存中...' : '保存'}
                      </button>
                      <button
                        onClick={() => setShowSettings(false)}
                        className="px-3 py-1.5 bg-surface-200 hover:bg-surface-300 dark:bg-surface-700 dark:hover:bg-surface-600 text-surface-700 dark:text-surface-200 text-sm rounded-lg transition-colors"
                      >
                        取消
                      </button>
                    </div>
                  </div>
                  <p className="mt-2 text-xs text-surface-500">
                    冷却时间：请求失败后端点暂停使用的时间（0禁用）。<br />
                    超时时间：单次请求的最大等待时间，超时后自动切换下一模型。
                  </p>
                </div>
              )}
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
        {/* 搜索框 + 显示开关 */}
        <div className="flex flex-col sm:flex-row gap-3 sm:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-surface-400" />
            <input
              type="text"
              placeholder="搜索模型ID或服务商名称..."
              value={modelFilter}
              onChange={(e) => setModelFilter(e.target.value)}
              className="w-full pl-9 pr-4 py-2 text-sm bg-white dark:bg-surface-800 border border-surface-200 dark:border-surface-700 rounded-lg focus:ring-2 focus:ring-primary-500/20 focus:border-primary-500 transition-shadow"
            />
          </div>

          <label className="flex items-center gap-2 px-3 py-2 bg-white dark:bg-surface-800 border border-surface-200 dark:border-surface-700 rounded-lg text-xs sm:text-sm text-surface-600 dark:text-surface-300 whitespace-nowrap">
            <input
              type="checkbox"
              checked={showDisabled}
              onChange={(e) => setShowDisabled(e.target.checked)}
              className="w-4 h-4 text-primary-500 border-surface-300 rounded focus:ring-primary-500"
            />
            显示已禁用
          </label>
        </div>

        {filteredProviders.length === 0 ? (
          <div className="text-center py-8 bg-white dark:bg-surface-800 rounded-xl border border-surface-200 dark:border-surface-700">
            <p className="text-surface-500 text-sm">
              {modelFilter
                ? '未找到匹配的模型'
                : showDisabled
                ? '该池还没有添加任何模型'
                : '未找到启用中的模型（可勾选“显示已禁用”查看全部）'}
            </p>
          </div>
        ) : (
          filteredProviders.map(provider => (
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
                    <div
                      className={clsx(
                        "p-2 rounded-lg flex-shrink-0",
                        model.is_cooling
                          ? "bg-blue-50 dark:bg-blue-900/20"
                          : model.enabled
                          ? "bg-green-50 dark:bg-green-900/20"
                          : "bg-red-50 dark:bg-red-900/20"
                      )}
                      title={model.is_cooling ? "冷却中" : model.enabled ? "已启用" : "已禁用"}
                    >
                      {model.is_cooling ? (
                        <Snowflake className="w-4 h-4 text-blue-500 animate-pulse-subtle" />
                      ) : model.enabled ? (
                        <CheckCircle className="w-4 h-4 text-green-500" />
                      ) : (
                        <XCircle className="w-4 h-4 text-red-500" />
                      )}
                    </div>

                    {/* 模型信息 */}
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className={clsx(
                          "font-mono text-xs sm:text-sm truncate transition-colors",
                          model.enabled ? "text-surface-900 dark:text-white" : "text-surface-400 dark:text-surface-500 line-through"
                        )}>
                          {model.model_id}
                        </p>
                        {model.enabled && !model.is_cooling && (
                          <span className="text-[10px] px-1.5 py-0.5 bg-surface-100 dark:bg-surface-700 text-surface-500 rounded-full">
                            {Math.round((model.weight / totalWeight) * 100)}%
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1">
                        {/* 权重控制 */}
                        <div className="flex items-center gap-1 bg-surface-50 dark:bg-surface-800/50 rounded px-1.5 py-0.5 border border-surface-200 dark:border-surface-700">
                          <Scale className="w-3 h-3 text-surface-400" />
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              if (model.weight > 1) {
                                updateEndpointMutation.mutate({
                                  id: model.id,
                                  data: { weight: model.weight - 1 }
                                })
                              }
                            }}
                            className="w-4 h-4 flex items-center justify-center text-surface-500 hover:text-primary-500 hover:bg-surface-200 dark:hover:bg-surface-600 rounded text-xs font-medium"
                          >
                            -
                          </button>
                          <span className="text-xs font-medium min-w-[1rem] text-center text-surface-700 dark:text-surface-300">
                            {model.weight}
                          </span>
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              updateEndpointMutation.mutate({
                                id: model.id,
                                data: { weight: model.weight + 1 }
                              })
                            }}
                            className="w-4 h-4 flex items-center justify-center text-surface-500 hover:text-primary-500 hover:bg-surface-200 dark:hover:bg-surface-600 rounded text-xs font-medium"
                          >
                            +
                          </button>
                        </div>

                        {model.is_cooling && (
                          <span className="text-xs text-blue-500">
                            冷却中 ({model.cooldown_remaining}s)
                          </span>
                        )}
                        <span className="text-xs text-surface-500">
                          成功率 {model.success_rate}%
                        </span>
                        <span className="text-xs text-surface-500">
                          延迟 {model.avg_latency_ms >= 1000
                            ? `${(model.avg_latency_ms / 1000).toFixed(2)}s`
                            : `${Math.round(model.avg_latency_ms)}ms`}
                        </span>

                        {/* 最小请求间隔设置 */}
                        <div className="flex items-center gap-1 bg-surface-50 dark:bg-surface-800/50 rounded px-1.5 py-0.5 border border-surface-200 dark:border-surface-700" title="最小请求间隔(秒)">
                          <Clock className="w-3 h-3 text-surface-400" />
                          <input
                            type="number"
                            min="0"
                            value={model.min_interval_seconds || 0}
                            onChange={(e) => {
                              const val = parseInt(e.target.value)
                              if (!isNaN(val) && val >= 0) {
                                updateEndpointMutation.mutate({
                                  id: model.id,
                                  data: { min_interval_seconds: val }
                                })
                              }
                            }}
                            onClick={(e) => e.stopPropagation()}
                            className="w-8 bg-transparent text-xs font-medium text-center text-surface-700 dark:text-surface-300 focus:outline-none"
                          />
                          <span className="text-[10px] text-surface-400">s</span>
                        </div>
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
                      onClick={() => updateEndpointMutation.mutate({
                        id: model.id,
                        data: { enabled: !model.enabled }
                      })}
                      disabled={model.is_cooling || updateEndpointMutation.isPending}
                      className={clsx(
                        'px-2.5 py-1.5 rounded-lg text-xs font-medium transition-colors',
                        model.is_cooling || updateEndpointMutation.isPending
                          ? 'bg-surface-200 text-surface-400 dark:bg-surface-700 dark:text-surface-500 cursor-not-allowed'
                          : model.enabled
                          ? 'bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-900/20 dark:text-red-400 dark:hover:bg-red-900/30'
                          : 'bg-green-50 text-green-600 hover:bg-green-100 dark:bg-green-900/20 dark:text-green-400 dark:hover:bg-green-900/30'
                      )}
                      title={model.enabled ? '禁用此模型' : '启用此模型'}
                    >
                      {model.enabled ? '禁用' : '启用'}
                    </button>

                    <button
                      onClick={() => handleDelete(model.id, model.model_id)}
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
        ))
        )}
      </div>
    </div>
  )
}
