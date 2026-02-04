import axios from 'axios'

const api = axios.create({
  baseURL: '/admin',
  timeout: 30000,
})

// 类型定义
export interface Provider {
  id: number
  name: string
  base_url: string
  api_key: string
  api_format: 'openai' | 'anthropic'
  enabled: boolean
  total_requests: number
  success_requests: number
  error_requests: number
  created_at: string
  endpoint_count: number
  healthy_endpoint_count: number
}

export interface ModelEndpoint {
  id: number
  provider_id: number
  provider_name: string
  model_id: string
  pool_type: 'tool' | 'normal' | 'advanced' | null
  enabled: boolean
  priority: number
  is_cooling: boolean
  cooldown_until: string | null
  last_error: string | null
  total_requests: number
  success_requests: number
  error_requests: number
  avg_latency_ms: number
  success_rate: number
}

export interface Pool {
  pool_type: 'tool' | 'normal' | 'advanced'
  virtual_model_name: string
  cooldown_seconds: number
  max_retries: number
  endpoint_count: number
  healthy_endpoint_count: number
  provider_count: number
}

export interface PoolDetail {
  pool_type: string
  virtual_model_name: string
  providers: {
    provider_id: number
    provider_name: string
    base_url: string
    api_format: string
    models: {
      id: number
      model_id: string
      enabled: boolean
      is_cooling: boolean
      cooldown_remaining: number
      total_requests: number
      success_requests: number
      success_rate: number
      avg_latency_ms: number
    }[]
    healthy_count: number
    total_count: number
  }[]
}

export interface Stats {
  total_providers: number
  enabled_providers: number
  total_endpoints: number
  healthy_endpoints: number
  cooling_endpoints: number
  total_requests: number
  success_requests: number
  error_requests: number
  success_rate: number
  pool_stats: Record<string, {
    total_endpoints: number
    healthy_endpoints: number
    total_requests: number
    success_requests: number
  }>
}

export interface LogEntry {
  id: number
  pool_type: string
  requested_model: string
  actual_model: string
  provider_name: string
  success: boolean
  status_code: number | null
  error_message: string | null
  latency_ms: number
  input_tokens: number | null
  output_tokens: number | null
  created_at: string
}

// API 函数
export const fetchProviders = () =>
  api.get<Provider[]>('/providers').then(r => r.data)

export const createProvider = (data: {
  name: string
  base_url: string
  api_key: string
  api_format: 'openai' | 'anthropic'
}) => api.post<Provider>('/providers', data).then(r => r.data)

export const updateProvider = (id: number, data: Partial<Provider>) =>
  api.put<Provider>(`/providers/${id}`, data).then(r => r.data)

export const deleteProvider = (id: number) =>
  api.delete(`/providers/${id}`).then(r => r.data)

export const fetchProviderModels = (id: number) =>
  api.post<{ provider_id: number; provider_name: string; models: string[] }>(
    `/providers/${id}/fetch-models`
  ).then(r => r.data)

export const fetchEndpoints = (params?: { provider_id?: number; pool_type?: string }) =>
  api.get<ModelEndpoint[]>('/endpoints', { params }).then(r => r.data)

export const createEndpoint = (data: {
  provider_id: number
  model_id: string
  pool_type: 'tool' | 'normal' | 'advanced'
  priority?: number
}) => api.post<ModelEndpoint>('/endpoints', data).then(r => r.data)

export const batchCreateEndpoints = (
  provider_id: number,
  pool_type: 'tool' | 'normal' | 'advanced',
  model_ids: string[]
) => api.post('/endpoints/batch', null, {
  params: { provider_id, pool_type },
  data: model_ids,
}).then(r => r.data)

export const updateEndpoint = (id: number, data: Partial<ModelEndpoint>) =>
  api.put<ModelEndpoint>(`/endpoints/${id}`, data).then(r => r.data)

export const deleteEndpoint = (id: number) =>
  api.delete(`/endpoints/${id}`).then(r => r.data)

export const fetchPools = () =>
  api.get<Pool[]>('/pools').then(r => r.data)

export const fetchPoolDetail = (poolType: string) =>
  api.get<PoolDetail>(`/pools/${poolType}`).then(r => r.data)

export const fetchStats = () =>
  api.get<Stats>('/stats').then(r => r.data)

export const fetchLogs = (params?: {
  limit?: number
  offset?: number
  pool_type?: string
  success?: boolean
  provider_name?: string
}) => api.get<{ total: number; logs: LogEntry[] }>('/logs', { params }).then(r => r.data)

export const clearLogs = () =>
  api.delete('/logs').then(r => r.data)
