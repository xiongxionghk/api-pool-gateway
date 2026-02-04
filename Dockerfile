FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY backend/ ./

# 复制前端构建产物
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# 创建数据目录
RUN mkdir -p /app/data

# 暴露端口
EXPOSE 8899

# 启动命令
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8899"]
