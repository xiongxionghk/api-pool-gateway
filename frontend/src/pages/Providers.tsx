import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus,
  Trash2,
  RefreshCw,
  Server,
  CheckCircle,
  ChevronDown,
  ChevronRight,
  Layers,
  Edit2,
  Search,
  PlusCircle,
} from 'lucide-react'
import clsx from 'clsx'
import {
  fetchProviders,
  createProvider,
  updateProvider,
  deleteProvider,
  fetchProviderModels,
  batchCreateEndpoints,
  Provider,
} from '../api/client'

export default function Providers() {
  const queryClient = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [modalMode, setModalMode] = useState<'create' | 'edit'>('create')
  const [editingProvider, setEditingProvider] = useState<Provider | null>(null)

  const [expandedProvider, setExpandedProvider] = useState<number | null>(null)
  const [fetchedModels, setFetchedModels] = useState<Record<number, string[]>>({})
  const [selectedModels, setSelectedModels] = useState<Record<number, Set<string>>>({})
  const [selectedPool, setSelectedPool] = useState<'tool' | 'normal' | 'advanced'>('normal')
  const [searchQuery, setSearchQuery] = useState('')
  const [customModelId, setCustomModelId] = useState('')

  const { data: providers, isLoading } = useQuery({
    queryKey: ['providers'],
    queryFn: fetchProviders,
  })

  const deleteMutation = useMutation({
    mutationFn: deleteProvider,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['providers'] }),
    onError: (error: any) => {
      alert(`删除服务商失败: ${error?.response?.data?.detail || error.message || '未知错误'}`)
    },
  })

  const fetchModelsMutation = useMutation({
    mutationFn: fetchProviderModels,
    onSuccess: (data) => {
      setFetchedModels(prev => ({ ...prev, [data.provider_id]: data.models }))
      setSelectedModels(prev => ({ ...prev, [data.provider_id]: new Set() }))
    },
    onError: (error: any) => {
      alert(`拉取模型失败: ${error?.response?.data?.detail || error.message || '未知错误'}`)
    },
  })

  const addEndpointMutation = useMutation({
    mutationFn: (data: { provider_id: number; pool_type: 'tool' | 'normal' | 'advanced'; model_ids: string[] }) =>
      batchCreateEndpoints(data.provider_id, data.pool_type, data.model_ids),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] })
      queryClient.invalidateQueries({ queryKey: ['pools'] })
    },
    onError: (error: any) => {
      alert(`添加模型失败: ${error?.response?.data?.detail || error.message || '未知错误'}`)
    },
  })

  const handleFetchModels = (providerId: number) => {
    setExpandedProvider(expandedProvider === providerId ? null : providerId)
    setSearchQuery('') // 重置搜索
    setCustomModelId('') // 重置自定义输入
    if (!fetchedModels[providerId]) {
      fetchModelsMutation.mutate(providerId)
    }
  }

  const toggleModelSelection = (providerId: number, modelId: string) => {
    setSelectedModels(prev => {
      const current = prev[providerId] || new Set()
      const updated = new Set(current)
      if (updated.has(modelId)) {
        updated.delete(modelId)
      } else {
        updated.add(modelId)
      }
      return { ...prev, [providerId]: updated }
    })
  }

  const handleAddCustomModel = (providerId: number) => {
    if (!customModelId.trim()) return
    const modelId = customModelId.trim()

    setFetchedModels(prev => {
      const current = prev[providerId] || []
      // 如果已存在，不再重复添加，但会确保它被选中
      if (current.includes(modelId)) {
        // 自动选中的逻辑在下面统一处理
      } else {
        return { ...prev, [providerId]: [modelId, ...current] } // 添加到最前面
      }
      return prev
    })

    // 自动选中
    setSelectedModels(prev => {
      const current = prev[providerId] || new Set()
      const updated = new Set(current)
      updated.add(modelId)
      return { ...prev, [providerId]: updated }
    })

    setCustomModelId('')
    setSearchQuery('') // 清除搜索以便看到新添加的模型
  }

  const handleAddSelectedToPool = async (providerId: number) => {
    const models = selectedModels[providerId]
    if (!models || models.size === 0) return

    // 使用批量接口一次性添加所有模型
    addEndpointMutation.mutate({
      provider_id: providerId,
      pool_type: selectedPool,
      model_ids: Array.from(models),
    })

    // 清除选择
    setSelectedModels(prev => ({ ...prev, [providerId]: new Set() }))
  }

  const openCreateModal = () => {
    setModalMode('create')
    setEditingProvider(null)
    setShowModal(true)
  }

  const openEditModal = (provider: Provider) => {
    setModalMode('edit')
    setEditingProvider(provider)
    setShowModal(true)
  }

  if (isLoading) {
    return (
      <div className="p-8 flex items-center justify-center">
        <div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 animate-fadeIn">
      {/* 页面标题 */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-surface-900 dark:text-white">
            服务商管理
          </h1>
          <p className="mt-1 text-sm text-surface-500">
            添加和管理 API 服务商，拉取模型列表
          </p>
        </div>
        <button
          onClick={openCreateModal}
          className="flex items-center justify-center px-4 py-2.5 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors text-sm font-medium"
        >
          <Plus className="w-5 h-5 mr-2" />
          添加服务商
        </button>
      </div>

      {/* 服务商列表 */}
      <div className="space-y-3 sm:space-y-4">
        {providers?.map(provider => (
          <div
            key={provider.id}
            className="bg-white dark:bg-surface-800 rounded-xl border border-surface-200 dark:border-surface-700 overflow-hidden"
          >
            {/* 服务商头部 */}
            <div
              className="p-4 sm:p-6 cursor-pointer hover:bg-surface-50 dark:hover:bg-surface-700/50 transition-colors"
              onClick={() => handleFetchModels(provider.id)}
            >
              <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4">
                <div className="flex items-center space-x-3 sm:space-x-4 flex-1 min-w-0">
                  <div className="p-2 sm:p-3 bg-primary-50 dark:bg-primary-900/20 rounded-xl flex-shrink-0">
                    <Server className="w-5 h-5 sm:w-6 sm:h-6 text-primary-500" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-semibold text-sm sm:text-base text-surface-900 dark:text-white truncate">
                        {provider.name}
                      </h3>
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          openEditModal(provider)
                        }}
                        className="p-1 text-surface-400 hover:text-primary-500 transition-all"
                        title="编辑配置"
                      >
                        <Edit2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                    <div className="text-xs text-surface-500 truncate mt-1 font-mono">
                      {provider.base_url}
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between sm:justify-end gap-2 sm:gap-4 flex-wrap">
                  {/* 状态标签 */}
                  <span className={clsx(
                    'px-2 py-0.5 sm:px-3 sm:py-1 rounded-full text-xs font-medium',
                    provider.enabled
                      ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                      : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                  )}>
                    {provider.enabled ? '启用' : '禁用'}
                  </span>

                  {/* 格式标签 */}
                  <span className="px-2 py-0.5 sm:px-3 sm:py-1 bg-surface-100 dark:bg-surface-700 rounded-full text-xs font-medium text-surface-600 dark:text-surface-400">
                    {provider.api_format.toUpperCase()}
                  </span>

                  {/* 统计 */}
                  <div className="text-xs sm:text-sm text-surface-500">
                    <span className="text-green-500">{provider.healthy_endpoint_count}</span>
                    {' / '}
                    <span>{provider.endpoint_count}</span>
                    {' 端点'}
                  </div>

                  {/* 展开/收起指示器 */}
                  <div className="p-2">
                    {expandedProvider === provider.id ? (
                      <ChevronDown className="w-5 h-5 text-surface-500" />
                    ) : (
                      <ChevronRight className="w-5 h-5 text-surface-500" />
                    )}
                  </div>

                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      deleteMutation.mutate(provider.id)
                    }}
                    className="p-2 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                    title="删除"
                  >
                    <Trash2 className="w-5 h-5 text-red-500" />
                  </button>
                </div>
              </div>
            </div>

            {/* 模型列表（展开时显示） */}
            {expandedProvider === provider.id && (
              <div className="border-t border-surface-200 dark:border-surface-700 p-4 sm:p-6 bg-surface-50 dark:bg-surface-900">
                {fetchModelsMutation.isPending ? (
                  <div className="flex items-center justify-center py-8">
                    <RefreshCw className="w-6 h-6 text-primary-500 animate-spin" />
                    <span className="ml-2 text-surface-500">正在拉取模型...</span>
                  </div>
                ) : fetchedModels[provider.id] ? (
                  <div className="space-y-4">
                    {/* 自定义添加模型 */}
                    <div className="p-3 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg">
                      <div className="flex items-center gap-2 mb-2">
                        <PlusCircle className="w-4 h-4 text-amber-600 dark:text-amber-500" />
                        <span className="text-xs font-medium text-amber-800 dark:text-amber-400">
                          手动添加自定义模型 ID
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        <input
                          type="text"
                          value={customModelId}
                          onChange={(e) => setCustomModelId(e.target.value)}
                          placeholder="例如: claude-3-opus-20240229 或自定义ID"
                          className="flex-1 px-3 py-2 bg-white dark:bg-surface-800 border border-amber-300 dark:border-amber-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') handleAddCustomModel(provider.id)
                          }}
                        />
                        <button
                          onClick={() => handleAddCustomModel(provider.id)}
                          disabled={!customModelId.trim()}
                          className={clsx(
                            "px-4 py-2 rounded-lg text-sm font-medium transition-colors flex items-center whitespace-nowrap",
                            customModelId.trim()
                              ? "bg-amber-500 text-white hover:bg-amber-600"
                              : "bg-surface-200 text-surface-400 cursor-not-allowed"
                          )}
                        >
                          <PlusCircle className="w-4 h-4 mr-1.5" />
                          添加
                        </button>
                      </div>
                      <p className="mt-2 text-xs text-amber-700 dark:text-amber-500">
                        用于服务商模型列表更新不及时或需要添加未列出的模型 ID
                      </p>
                    </div>

                    {/* 池选择和工具栏 */}
                    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
                      <div className="flex flex-col sm:flex-row gap-3 flex-1">
                        {/* 搜索框 */}
                        <div className="relative max-w-xs">
                          <input
                            type="text"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            placeholder="搜索模型..."
                            className="w-full pl-9 pr-3 py-1.5 bg-white dark:bg-surface-800 border border-surface-300 dark:border-surface-600 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                          />
                          <Search className="w-4 h-4 text-surface-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
                        </div>

                        {/* 池选择 */}
                        <div className="flex items-center space-x-2">
                          <span className="text-xs sm:text-sm text-surface-500 whitespace-nowrap">添加到池:</span>
                          <select
                            value={selectedPool}
                            onChange={(e) => setSelectedPool(e.target.value as 'tool' | 'normal' | 'advanced')}
                            className="px-3 py-1.5 bg-white dark:bg-surface-800 border border-surface-300 dark:border-surface-600 rounded-lg text-sm"
                          >
                            <option value="tool">工具池 (haiku)</option>
                            <option value="normal">普通池 (sonnet)</option>
                            <option value="advanced">高级池 (opus)</option>
                          </select>
                        </div>
                      </div>

                      <button
                        onClick={() => handleAddSelectedToPool(provider.id)}
                        disabled={!selectedModels[provider.id]?.size}
                        className={clsx(
                          'flex items-center justify-center px-4 py-2 rounded-lg text-sm font-medium transition-colors whitespace-nowrap',
                          selectedModels[provider.id]?.size
                            ? 'bg-primary-500 text-white hover:bg-primary-600'
                            : 'bg-surface-200 text-surface-400 cursor-not-allowed'
                        )}
                      >
                        <Layers className="w-4 h-4 mr-2" />
                        添加选中 ({selectedModels[provider.id]?.size || 0})
                      </button>
                    </div>

                    {/* 模型网格 */}
                    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
                      {fetchedModels[provider.id]
                        .filter(modelId => modelId.toLowerCase().includes(searchQuery.toLowerCase()))
                        .map(modelId => (
                        <label
                          key={modelId}
                          className={clsx(
                            'flex items-center p-3 rounded-lg border cursor-pointer transition-colors',
                            selectedModels[provider.id]?.has(modelId)
                              ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
                              : 'border-surface-200 dark:border-surface-700 hover:border-surface-300 dark:hover:border-surface-600'
                          )}
                        >
                          <input
                            type="checkbox"
                            checked={selectedModels[provider.id]?.has(modelId) || false}
                            onChange={() => toggleModelSelection(provider.id, modelId)}
                            className="sr-only"
                          />
                          <div className={clsx(
                            'w-4 h-4 rounded border mr-3 flex items-center justify-center',
                            selectedModels[provider.id]?.has(modelId)
                              ? 'bg-primary-500 border-primary-500'
                              : 'border-surface-300 dark:border-surface-600'
                          )}>
                            {selectedModels[provider.id]?.has(modelId) && (
                              <CheckCircle className="w-3 h-3 text-white" />
                            )}
                          </div>
                          <span className="text-sm text-surface-700 dark:text-surface-300 truncate">
                            {modelId}
                          </span>
                        </label>
                      ))}
                    </div>
                  </div>
                ) : (
                  <p className="text-center text-surface-500 py-4">
                    点击展开以拉取模型列表
                  </p>
                )}
              </div>
            )}
          </div>
        ))}

        {providers?.length === 0 && (
          <div className="text-center py-12 bg-white dark:bg-surface-800 rounded-xl border border-surface-200 dark:border-surface-700">
            <Server className="w-12 h-12 text-surface-300 mx-auto mb-4" />
            <p className="text-surface-500">还没有添加服务商</p>
            <button
              onClick={openCreateModal}
              className="mt-4 text-primary-500 hover:text-primary-600"
            >
              添加第一个服务商
            </button>
          </div>
        )}
      </div>

      {/* 服务商弹窗 (添加/编辑) */}
      {showModal && (
        <ProviderModal
          mode={modalMode}
          initialData={editingProvider}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  )
}

function ProviderModal({
  mode,
  initialData,
  onClose
}: {
  mode: 'create' | 'edit'
  initialData: Provider | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const [formData, setFormData] = useState({
    name: '',
    base_url: '',
    api_key: '',
    api_format: 'openai' as 'openai' | 'anthropic',
    enabled: true,
  })

  // 初始化表单数据
  useEffect(() => {
    if (mode === 'edit' && initialData) {
      setFormData({
        name: initialData.name,
        base_url: initialData.base_url,
        api_key: '', // 编辑时不自动填充 key，只在需要修改时输入
        api_format: initialData.api_format,
        enabled: initialData.enabled,
      })
    } else {
      setFormData({
        name: '',
        base_url: '',
        api_key: '',
        api_format: 'openai',
        enabled: true,
      })
    }
  }, [mode, initialData])

  const createMutation = useMutation({
    mutationFn: createProvider,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] })
      onClose()
    },
    onError: (error: any) => {
      alert(`添加服务商失败: ${error?.response?.data?.detail || error.message || '未知错误'}`)
    },
  })

  const updateMutation = useMutation({
    mutationFn: (data: any) => updateProvider(initialData!.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['providers'] })
      onClose()
    },
    onError: (error: any) => {
      alert(`更新服务商失败: ${error?.response?.data?.detail || error.message || '未知错误'}`)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (mode === 'create') {
      createMutation.mutate(formData)
    } else {
      // 过滤掉空值（比如 api_key 没填就不更新）
      const updateData: any = { ...formData }
      if (!updateData.api_key) {
        delete updateData.api_key
      }
      updateMutation.mutate(updateData)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-surface-800 rounded-2xl w-full max-w-md p-4 sm:p-6 animate-fadeIn">
        <h2 className="text-lg sm:text-xl font-semibold text-surface-900 dark:text-white mb-4 sm:mb-6">
          {mode === 'create' ? '添加服务商' : '编辑服务商'}
        </h2>

        <form onSubmit={handleSubmit} className="space-y-3 sm:space-y-4">
          <div>
            <label className="block text-xs sm:text-sm font-medium text-surface-700 dark:text-surface-300 mb-1">
              名称
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="例如: 服务商A"
              className="w-full px-4 py-2 bg-surface-50 dark:bg-surface-900 border border-surface-300 dark:border-surface-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm"
              required
            />
          </div>

          <div>
            <label className="block text-xs sm:text-sm font-medium text-surface-700 dark:text-surface-300 mb-1">
              Base URL
            </label>
            <input
              type="url"
              value={formData.base_url}
              onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
              placeholder="例如: http://127.0.0.1:8311/v1"
              className="w-full px-4 py-2 bg-surface-50 dark:bg-surface-900 border border-surface-300 dark:border-surface-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent font-mono text-xs sm:text-sm"
              required
            />
            <p className="mt-1 text-xs text-surface-500">
              Docker 部署时请使用 host.docker.internal 访问主机
            </p>
          </div>

          <div>
            <label className="block text-xs sm:text-sm font-medium text-surface-700 dark:text-surface-300 mb-1">
              API Key
              {mode === 'edit' && <span className="ml-2 text-xs font-normal text-surface-400">(留空保持不变)</span>}
            </label>
            <input
              type="password"
              value={formData.api_key}
              onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
              placeholder={mode === 'edit' ? "******" : "API 密钥"}
              className="w-full px-4 py-2 bg-surface-50 dark:bg-surface-900 border border-surface-300 dark:border-surface-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm"
              required={mode === 'create'}
            />
          </div>

          <div>
            <label className="block text-xs sm:text-sm font-medium text-surface-700 dark:text-surface-300 mb-1">
              API 格式
            </label>
            <select
              value={formData.api_format}
              onChange={(e) => setFormData({ ...formData, api_format: e.target.value as 'openai' | 'anthropic' })}
              className="w-full px-4 py-2 bg-surface-50 dark:bg-surface-900 border border-surface-300 dark:border-surface-600 rounded-lg focus:ring-2 focus:ring-primary-500 focus:border-transparent text-sm"
            >
              <option value="openai">OpenAI (/v1/chat/completions)</option>
              <option value="anthropic">Anthropic (/v1/messages)</option>
            </select>
          </div>

          {mode === 'edit' && (
            <div className="flex items-center">
              <input
                id="provider-enabled"
                type="checkbox"
                checked={formData.enabled}
                onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                className="w-4 h-4 text-primary-500 border-surface-300 rounded focus:ring-primary-500"
              />
              <label htmlFor="provider-enabled" className="ml-2 text-sm text-surface-700 dark:text-surface-300">
                启用此服务商
              </label>
            </div>
          )}

          <div className="flex justify-end space-x-3 pt-3 sm:pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-sm text-surface-600 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-700 rounded-lg transition-colors"
            >
              取消
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending || updateMutation.isPending}
              className="px-4 py-2 text-sm bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors disabled:opacity-50"
            >
              {createMutation.isPending || updateMutation.isPending ? '保存中...' : '保存'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
