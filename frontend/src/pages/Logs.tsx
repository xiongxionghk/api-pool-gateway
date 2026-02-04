import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ScrollText,
  CheckCircle,
  XCircle,
  Trash2,
  RefreshCw,
  Filter
} from 'lucide-react'
import clsx from 'clsx'
import { fetchLogs, clearLogs, type LogEntry } from '../api/client'

export default function Logs() {
  const queryClient = useQueryClient()
  const [filters, setFilters] = useState({
    pool_type: '',
    success: '',
  })
  const [page, setPage] = useState(0)
  const limit = 50

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['logs', filters, page],
    queryFn: () => fetchLogs({
      limit,
      offset: page * limit,
      pool_type: filters.pool_type || undefined,
      success: filters.success === '' ? undefined : filters.success === 'true',
    }),
    refetchInterval: 10000,
  })

  const clearMutation = useMutation({
    mutationFn: clearLogs,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['logs'] }),
  })

  return (
    <div className="p-4 sm:p-6 lg:p-8 space-y-4 sm:space-y-6 animate-fadeIn">
      {/* 页面标题 */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-surface-900 dark:text-white">
            请求日志
          </h1>
          <p className="mt-1 text-sm text-surface-500">
            查看 API 请求历史和错误详情
          </p>
        </div>
        <div className="flex items-center gap-2 sm:gap-3">
          <button
            onClick={() => refetch()}
            className="flex items-center px-3 py-2 text-surface-600 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-800 rounded-lg transition-colors text-sm"
          >
            <RefreshCw className="w-4 h-4 mr-2" />
            刷新
          </button>
          <button
            onClick={() => clearMutation.mutate()}
            className="flex items-center px-3 py-2 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors text-sm"
          >
            <Trash2 className="w-4 h-4 mr-2" />
            清空日志
          </button>
        </div>
      </div>

      {/* 筛选器 */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3 bg-white dark:bg-surface-800 p-4 rounded-xl border border-surface-200 dark:border-surface-700">
        <Filter className="w-5 h-5 text-surface-400" />

        <div className="flex flex-wrap items-center gap-2">
          <select
            value={filters.pool_type}
            onChange={(e) => setFilters({ ...filters, pool_type: e.target.value })}
            className="px-3 py-1.5 bg-surface-50 dark:bg-surface-900 border border-surface-300 dark:border-surface-600 rounded-lg text-sm"
          >
            <option value="">所有池</option>
            <option value="tool">工具池</option>
            <option value="normal">普通池</option>
            <option value="advanced">高级池</option>
          </select>

          <select
            value={filters.success}
            onChange={(e) => setFilters({ ...filters, success: e.target.value })}
            className="px-3 py-1.5 bg-surface-50 dark:bg-surface-900 border border-surface-300 dark:border-surface-600 rounded-lg text-sm"
          >
            <option value="">所有状态</option>
            <option value="true">成功</option>
            <option value="false">失败</option>
          </select>

          <span className="text-xs sm:text-sm text-surface-500">
            共 {data?.total ?? 0} 条记录
          </span>
        </div>
      </div>

      {/* 日志表格 */}
      <div className="bg-white dark:bg-surface-800 rounded-xl border border-surface-200 dark:border-surface-700 overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin w-8 h-8 border-4 border-primary-500 border-t-transparent rounded-full" />
          </div>
        ) : data?.logs.length === 0 ? (
          <div className="text-center py-12">
            <ScrollText className="w-12 h-12 text-surface-300 mx-auto mb-4" />
            <p className="text-surface-500">暂无日志记录</p>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead className="bg-surface-50 dark:bg-surface-900">
                  <tr>
                    <th className="px-3 sm:px-4 py-2 sm:py-3 text-left text-xs font-medium text-surface-500 uppercase tracking-wider">
                      状态
                    </th>
                    <th className="px-3 sm:px-4 py-2 sm:py-3 text-left text-xs font-medium text-surface-500 uppercase tracking-wider">
                      池
                    </th>
                    <th className="px-3 sm:px-4 py-2 sm:py-3 text-left text-xs font-medium text-surface-500 uppercase tracking-wider">
                      请求模型
                    </th>
                    <th className="px-3 sm:px-4 py-2 sm:py-3 text-left text-xs font-medium text-surface-500 uppercase tracking-wider hidden md:table-cell">
                      实际模型
                    </th>
                    <th className="px-3 sm:px-4 py-2 sm:py-3 text-left text-xs font-medium text-surface-500 uppercase tracking-wider hidden lg:table-cell">
                      服务商
                    </th>
                    <th className="px-3 sm:px-4 py-2 sm:py-3 text-left text-xs font-medium text-surface-500 uppercase tracking-wider hidden sm:table-cell">
                      延迟
                    </th>
                    <th className="px-3 sm:px-4 py-2 sm:py-3 text-left text-xs font-medium text-surface-500 uppercase tracking-wider">
                      时间
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-100 dark:divide-surface-700">
                  {data?.logs.map(log => (
                    <LogRow key={log.id} log={log} />
                  ))}
                </tbody>
              </table>
            </div>

            {/* 分页 */}
            <div className="flex items-center justify-between px-3 sm:px-4 py-2 sm:py-3 border-t border-surface-200 dark:border-surface-700">
              <button
                onClick={() => setPage(p => Math.max(0, p - 1))}
                disabled={page === 0}
                className="px-3 py-1.5 text-xs sm:text-sm text-surface-600 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                上一页
              </button>
              <span className="text-xs sm:text-sm text-surface-500">
                第 {page + 1} 页
              </span>
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={!data || data.logs.length < limit}
                className="px-3 py-1.5 text-xs sm:text-sm text-surface-600 dark:text-surface-400 hover:bg-surface-100 dark:hover:bg-surface-700 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                下一页
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function LogRow({ log }: { log: LogEntry }) {
  const [expanded, setExpanded] = useState(false)

  const poolLabels: Record<string, string> = {
    tool: '工具',
    normal: '普通',
    advanced: '高级',
  }

  const poolColors: Record<string, string> = {
    tool: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
    normal: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
    advanced: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  }

  return (
    <>
      <tr
        onClick={() => log.error_message && setExpanded(!expanded)}
        className={clsx(
          'hover:bg-surface-50 dark:hover:bg-surface-700/50 transition-colors',
          log.error_message && 'cursor-pointer'
        )}
      >
        <td className="px-3 sm:px-4 py-2 sm:py-3">
          {log.success ? (
            <CheckCircle className="w-4 h-4 sm:w-5 sm:h-5 text-green-500" />
          ) : (
            <XCircle className="w-4 h-4 sm:w-5 sm:h-5 text-red-500" />
          )}
        </td>
        <td className="px-3 sm:px-4 py-2 sm:py-3">
          <span className={clsx(
            'px-2 py-0.5 rounded text-xs font-medium',
            poolColors[log.pool_type] || 'bg-surface-100 text-surface-600'
          )}>
            {poolLabels[log.pool_type] || log.pool_type}
          </span>
        </td>
        <td className="px-3 sm:px-4 py-2 sm:py-3 font-mono text-xs sm:text-sm text-surface-700 dark:text-surface-300 max-w-[140px] sm:max-w-none truncate">
          {log.requested_model}
        </td>
        <td className="px-3 sm:px-4 py-2 sm:py-3 font-mono text-xs sm:text-sm text-surface-700 dark:text-surface-300 max-w-[180px] truncate hidden md:table-cell">
          {log.actual_model}
        </td>
        <td className="px-3 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm text-surface-600 dark:text-surface-400 hidden lg:table-cell">
          {log.provider_name}
        </td>
        <td className="px-3 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm text-surface-600 dark:text-surface-400 hidden sm:table-cell">
          {log.latency_ms}ms
        </td>
        <td className="px-3 sm:px-4 py-2 sm:py-3 text-xs sm:text-sm text-surface-500">
          {new Date(log.created_at).toLocaleString('zh-CN')}
        </td>
      </tr>

      {/* 错误详情展开 */}
      {expanded && log.error_message && (
        <tr>
          <td colSpan={7} className="px-3 sm:px-4 py-2 sm:py-3 bg-red-50 dark:bg-red-900/10">
            <p className="text-xs sm:text-sm text-red-600 dark:text-red-400 font-mono whitespace-pre-wrap">
              {log.error_message}
            </p>
          </td>
        </tr>
      )}
    </>
  )
}
