# RetainPDF Server

**将 RetainPDF 的 PDF 保留排版翻译能力封装为可部署的后端 API 服务。**

原项目：[wxyhgk/retain-pdf](https://github.com/wxyhgk/retain-pdf)

本 Server 剥离了桌面端 GUI 和静态前端页面，专注于提供稳定、异步、可观测的 HTTP API，使其他系统能够通过接口调用完成：

- PDF 上传
- OCR 识别（图片型/扫描版 PDF）
- 保留版面翻译（公式、表格、段落结构）
- 渲染输出（PDF / Markdown / ZIP）

---

## 目录

1. [快速启动](#快速启动)
2. [环境变量](#环境变量)
3. [API 文档](#api-文档)
4. [任务状态说明](#任务状态说明)
5. [下载结果说明](#下载结果说明)
6. [Docker 部署](#docker-部署)
7. [常见问题排查](#常见问题排查)
8. [目录结构](#目录结构)

---

## 快速启动

### 本地启动（需要 Python 3.11+）

```bash
# 1. 克隆本 server 和原项目
git clone https://github.com/wxyhgk/retain-pdf.git ./retain-pdf
cd retain_pdf_server

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 TRANSLATOR_API_KEY 等

# 4. 启动
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

服务启动后：
- API 根地址：`http://localhost:8000`
- OpenAPI 文档：`http://localhost:8000/docs`
- 健康检查：`http://localhost:8000/health`

---

### Docker 启动

```bash
# 1. 构建并启动
docker compose up -d --build

# 2. 查看日志
docker compose logs -f server

# 3. 停止
docker compose down
```

默认暴露端口 `8000`，上传文件、输出文件和 `jobs.db` 通过 Docker Volume `retain_pdf_data` 持久化。

---

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SERVER_HOST` | `0.0.0.0` | 监听地址 |
| `SERVER_PORT` | `8000` | 监听端口 |
| `UPLOAD_DIR` | `./data/uploads` | 上传 PDF 存储目录 |
| `OUTPUT_DIR` | `./data/outputs` | 翻译结果输出目录 |
| `TEMP_DIR` | `./data/temp` | 临时文件目录 |
| `JOB_DB` | `./data/jobs.db` | SQLite 任务数据库路径 |
| `RETAIN_PDF_ROOT` | `./retain-pdf` | 原 retain-pdf 项目根目录 |
| `TRANSLATOR_PROVIDER` | `deepseek` | 翻译服务提供商 |
| `TRANSLATOR_API_KEY` | - | **必填**，翻译 API Key |
| `TRANSLATOR_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI-compatible 接口地址 |
| `TRANSLATOR_MODEL` | `deepseek-chat` | 模型名称 |
| `OCR_PROVIDER` | `mineru` | OCR 提供商 |
| `OCR_API_KEY` | - | OCR API Key（如需） |
| `OCR_ENABLED` | `true` | 是否默认启用 OCR |
| `MAX_UPLOAD_SIZE_MB` | `200` | 单文件最大上传限制 |
| `MAX_CONCURRENT_JOBS` | `2` | 最大并发任务数 |
| `TRANSLATION_MODE` | `sci` | 翻译模式：`fast` / `precise` / `sci` |
| `MATH_MODE` | `direct_typst` | 公式处理模式 |
| `RENDER_MODE` | `typst` | 渲染模式：`auto` / `overlay` / `typst` / `dual` |
| `PDF_COMPRESS_DPI` | `150` | 输出 PDF 图片压缩 DPI |
| `DEFAULT_TARGET_LANG` | `zh` | 默认目标语言 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

> **注意**：不要把 `TRANSLATOR_API_KEY` 写死在代码里，始终通过 `.env` 或环境变量注入。

---

## API 文档

### A. 健康检查

```http
GET /health
```

响应：
```json
{
  "status": "ok",
  "version": "0.1.0-server",
  "service": "retain-pdf-server"
}
```

---

### B. 上传并创建任务

```http
POST /api/v1/jobs
Content-Type: multipart/form-data
```

字段：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `file` | File | ✅ | PDF 文件 |
| `source_lang` | string | | 源语言代码 |
| `target_lang` | string | | 默认 `zh` |
| `translator` | string | | 翻译提供商覆盖 |
| `ocr_enabled` | boolean | | 默认 `true` |
| `preserve_layout` | boolean | | 默认 `true` |
| `output_format` | string | | `pdf` / `markdown` / `zip` / `all` |
| `config` | string | | JSON 字符串，高级配置 |

**curl 示例：**

```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -F "file=@example.pdf" \
  -F "target_lang=zh" \
  -F "ocr_enabled=true" \
  -F "output_format=pdf"
```

响应：
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "queued",
  "message": "job created"
}
```

---

### C. 查询任务状态

```http
GET /api/v1/jobs/{job_id}
```

**curl 示例：**

```bash
curl http://localhost:8000/api/v1/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

响应：
```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "running",
  "progress": 45,
  "stage": "translate",
  "created_at": "2026-05-23T14:00:00+00:00",
  "updated_at": "2026-05-23T14:02:30+00:00",
  "error": null,
  "output_paths": null
}
```

---

### D. 下载结果

```http
GET /api/v1/jobs/{job_id}/download?format=pdf
```

支持 `format`：`pdf`、`markdown`、`zip`、`all`

**curl 示例：**

```bash
curl -L "http://localhost:8000/api/v1/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/download?format=pdf" \
  -o translated.pdf
```

---

### E. 删除任务

```http
DELETE /api/v1/jobs/{job_id}
```

清理上传文件、临时文件和输出结果。

**curl 示例：**

```bash
curl -X DELETE http://localhost:8000/api/v1/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### F. 获取配置模板

```http
GET /api/v1/config/default
```

返回当前服务的默认配置（OCR、翻译、渲染等默认值）。

---

## 任务状态说明

| 状态 | 含义 |
|------|------|
| `queued` | 已创建，等待执行（或被并发限制阻塞） |
| `running` | 正在执行 pipeline |
| `succeeded` | 全部完成，可以下载 |
| `failed` | 某个阶段失败，`error` 字段包含原因 |
| `cancelled` | 已取消 |

### Pipeline 阶段（stage）

| 阶段 | 说明 |
|------|------|
| `upload` | 文件已保存 |
| `ocr` | OCR 识别中 |
| `translate` | 翻译中 |
| `layout` | 排版回填中 |
| `render` | 最终渲染中 |
| `done` | 结束（成功或失败） |

---

## 下载结果说明

- **`format=pdf`**：下载翻译后的 PDF（保留原版面）
- **`format=markdown`**：下载 Markdown 版本（如可用）
- **`format=zip`**：下载完整输出包（含所有中间产物）
- **`format=all`**：同 `zip`

如果某种格式不存在，API 会返回 `404` 并提示 `Output file not found`。

---

## Docker 部署

### 生产部署

```bash
# 1. 准备 .env
cp .env.example .env
nano .env

# 2. 启动
docker compose up -d

# 3. 查看状态
docker compose ps
docker compose logs -f server

# 4. 更新镜像
docker compose pull
docker compose up -d
```

### 数据持久化

上传文件、输出文件和 SQLite 数据库都存储在 Docker Volume `retain_pdf_data` 中，重启容器不会丢失。

如果需要映射到宿主机目录：

```yaml
volumes:
  - /host/path/to/data:/data
```

---

## 常见问题排查

### Q1: Server 启动后 `/health` 返回错误？

- 检查端口是否被占用：`lsof -i :8000`
- 检查日志：`docker compose logs -f server`

### Q2: 上传 PDF 后任务一直处于 `queued`？

- 检查 `MAX_CONCURRENT_JOBS` 是否已满
- 查看 worker 线程日志中的异常信息

### Q3: OCR 阶段失败？

- 确认 `RETAIN_PDF_ROOT` 指向的目录包含 `backend/scripts`
- 确认 OCR 提供商的 API Key 已正确配置
- 原项目依赖（如 MinerU / Paddle）是否已安装

### Q4: 翻译阶段失败？

- 检查 `TRANSLATOR_API_KEY` 是否有效
- 检查 `TRANSLATOR_BASE_URL` 是否可达
- 查看日志中的 `stderr` 输出

### Q5: 没有输出文件？

- 确认任务状态为 `succeeded`
- 检查 `OUTPUT_DIR` / `jobs.db` 中记录的 `output_paths`
- 使用 `format=zip` 下载完整包查看中间产物

---

## 目录结构

```
retain_pdf_server/
├── app/
│   ├── __init__.py
│   ├── main.py               # FastAPI 入口
│   ├── api/
│   │   └── routes/
│   │       ├── health.py     # GET /health
│   │       ├── jobs.py       # 任务 CRUD + 下载
│   │       └── config.py     # GET /api/v1/config/default
│   ├── core/
│   │   ├── config.py         # Pydantic Settings（.env 驱动）
│   │   └── logging.py        # 结构化日志
│   ├── models/
│   │   └── __init__.py       # Pydantic 模型
│   ├── services/
│   │   ├── job_service.py    # SQLite Job 持久化
│   │   └── pipeline_service.py # 原项目 pipeline 适配器
│   └── workers/
│       └── task_worker.py    # 后台异步任务
├── data/                     # 运行数据（上传/输出/数据库）
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README_SERVER.md
```

---

## 与原项目的关系

- **保留**：OCR 归一化、翻译 pipeline、排版回填、PDF 渲染、字体控制、公式处理
- **剥离**：Electron 桌面壳、静态浏览器前端页面、桌面端打包脚本
- **新增**：FastAPI HTTP 接口、异步 Job 队列、SQLite 状态追踪、Docker 部署

如果需要恢复前端，可以将原项目的 `frontend/` 或 `frontend-react/` 目录挂载为静态资源，或单独部署一个前端容器调用本 Server 的 API。

---

## License

与原项目一致：MIT
