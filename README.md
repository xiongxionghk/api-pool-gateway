# API Pool Gateway

多服务商模型池轮询网关，支持 OpenAI 和 Anthropic 格式。

## 功能特点

- **三级模型池**：工具池 (haiku)、普通池 (sonnet)、高级池 (opus)
- **两级轮询**：服务商级 → 模型级轮询
- **故障转移**：自动跳过冷却中的端点
- **格式转换**：自动转换 OpenAI ↔ Anthropic 格式
- **可视化管理**：现代化 Web 管理后台

## 快速开始

### Docker 部署（推荐）

```bash
# 克隆或进入项目目录
cd ~/api-pool-gateway

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

## 配置 Claude Code

编辑 `~/.claude/settings.json`：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:8899",
    "ANTHROPIC_API_KEY": "任意值"
  }
}
```

## 使用流程

1. **添加服务商**：在管理后台添加你的 API 服务商（URL + API Key）
2. **拉取模型**：点击服务商展开，拉取可用模型列表
3. **分配到池**：勾选模型，选择池类型，点击添加
4. **开始使用**：Claude Code 请求 haiku/sonnet/opus 会自动路由到对应池

## 端点说明

| 端点 | 说明 |
|------|------|
| `POST /v1/messages` | Anthropic 格式入口 |
| `POST /v1/chat/completions` | OpenAI 格式入口 |
| `GET /v1/models` | 列出虚拟模型 |
| `GET /admin/*` | 管理 API |
| `GET /` | 管理后台 UI |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `API_PORT` | 8899 | 服务端口 |
| `ADMIN_PASSWORD` | admin123 | 管理密码 |
| `DEFAULT_COOLDOWN_SECONDS` | 60 | 默认冷却时间 |
| `VIRTUAL_MODEL_TOOL` | haiku | 工具池虚拟模型名 |
| `VIRTUAL_MODEL_NORMAL` | sonnet | 普通池虚拟模型名 |
| `VIRTUAL_MODEL_ADVANCED` | opus | 高级池虚拟模型名 |

## 架构图

```
Claude Code
    │
    ▼
┌─────────────────────────────────────┐
│        API Pool Gateway :8899        │
│  ┌─────────────────────────────────┐ │
│  │ 虚拟模型: haiku / sonnet / opus │ │
│  └─────────────────────────────────┘ │
│              │                       │
│  ┌───────────┼───────────┐          │
│  ▼           ▼           ▼          │
│ Tool池    Normal池    Advanced池    │
│  │           │           │          │
│  ├─服务商A   ├─服务商A   ├─服务商A   │
│  │ ├model1  │ ├model1  │ ├model1  │
│  │ └model2  │ └model2  │ └model2  │
│  │           │           │          │
│  └─服务商B   └─服务商B   └─服务商B   │
│    └model1    └model1    └model1  │
└─────────────────────────────────────┘
         │           │           │
         ▼           ▼           ▼
      :8311       :4096       :xxxx
    (服务商A)   (服务商B)   (更多...)
```

## License

MIT
