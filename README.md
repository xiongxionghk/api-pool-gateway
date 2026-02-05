# API Pool Gateway

**多模型轮询网关** - 统一管理多个 LLM 服务商，实现智能负载均衡与故障转移。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

## 项目简介

API Pool Gateway 是一个轻量级的 LLM API 网关，帮助你：

- 统一管理多个 API 服务商（中转站、官方 API 等）
- 自动进行负载均衡和故障转移
- 通过虚拟模型名简化客户端配置
- 可视化监控请求状态和端点健康度

## 功能特点

- **三级模型池**：工具池 (haiku)、普通池 (sonnet)、高级池 (opus)
- **智能轮询**：服务商级 + 模型级两级轮询，支持权重配置
- **故障转移**：自动跳过冷却中的端点，指数退避重试
- **格式兼容**：同时支持 OpenAI 和 Anthropic API 格式
- **可视化管理**：现代化 Web 管理后台，实时监控

## 快速开始

### Docker 部署（推荐）

```bash
# 克隆仓库
git clone https://github.com/xiongxionghk/api-pool-gateway.git
cd api-pool-gateway

# 一键启动
docker-compose up -d

# 查看日志
docker-compose logs -f
```

### 本地开发

```bash
# 后端
cd backend
pip install -r requirements.txt
python main.py

# 前端（另一个终端）
cd frontend
npm install
npm run dev
```

## 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `API_PORT` | 8899 | 服务端口 |
| `ADMIN_PASSWORD` | admin123 | 管理密码（**生产环境请务必修改**） |
| `DEFAULT_COOLDOWN_SECONDS` | 60 | 端点故障后的冷却时间（秒） |
| `VIRTUAL_MODEL_TOOL` | haiku | 工具池虚拟模型名 |
| `VIRTUAL_MODEL_NORMAL` | sonnet | 普通池虚拟模型名 |
| `VIRTUAL_MODEL_ADVANCED` | opus | 高级池虚拟模型名 |

### 配置 Claude Code

编辑 `~/.claude/settings.json`：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8899",
    "ANTHROPIC_API_KEY": "any-value"
  }
}
```

## 使用流程

1. **添加服务商**：在管理后台添加你的 API 服务商（URL + API Key）
2. **拉取模型**：点击服务商展开，拉取可用模型列表
3. **分配到池**：勾选模型，选择池类型，点击添加
4. **开始使用**：客户端请求 haiku/sonnet/opus 会自动路由到对应池

## API 端点

| 端点 | 说明 |
|------|------|
| `POST /v1/messages` | Anthropic 格式入口 |
| `POST /v1/chat/completions` | OpenAI 格式入口 |
| `GET /v1/models` | 列出虚拟模型 |
| `GET /admin/*` | 管理 API |
| `GET /` | 管理后台 UI |

## 架构图

```
客户端 (Claude Code / ChatGPT 等)
    │
    ▼
┌─────────────────────────────────────┐
│       API Pool Gateway :8899        │
│  ┌─────────────────────────────────┐│
│  │ 虚拟模型: haiku / sonnet / opus ││
│  └─────────────────────────────────┘│
│              │                      │
│  ┌───────────┼───────────┐          │
│  ▼           ▼           ▼          │
│ Tool池    Normal池    Advanced池    │
│  │           │           │          │
│  ├─服务商A   ├─服务商A   ├─服务商A  │
│  │ ├model1   │ ├model1   │ ├model1  │
│  │ └model2   │ └model2   │ └model2  │
│  │           │           │          │
│  └─服务商B   └─服务商B   └─服务商B  │
│    └model1     └model1     └model1  │
└─────────────────────────────────────┘
         │           │           │
         ▼           ▼           ▼
      服务商A     服务商B      更多...
```

## 安全提示

- **生产环境请务必修改默认管理密码** `ADMIN_PASSWORD`
- API Key 存储在本地 SQLite 数据库中，请妥善保护 `data/` 目录
- 建议在内网或配合反向代理使用

## 仓库地址

**GitHub**: https://github.com/xiongxionghk/api-pool-gateway

## License

[MIT](LICENSE)
