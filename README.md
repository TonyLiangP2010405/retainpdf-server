# Yoru RetainPDF Server

深紫玻璃风格的 PDF 翻译工作台。项目把 RetainPDF 的保留排版翻译能力封装成 FastAPI 服务，并内置一个可直接使用的静态前端：上传 PDF、配置模型、查看任务进度、下载翻译结果都在同一个页面完成。

![Yoru RetainPDF preview](docs/project-proof.png)

## 能力概览

| 模块 | 说明 |
| --- | --- |
| PDF 上传 | 支持浏览器拖拽或选择 PDF 文件，创建异步翻译任务 |
| OCR 识别 | 可接入 MinerU / PaddleOCR，用于扫描件或图片型 PDF |
| 翻译处理 | OpenAI-compatible 配置，默认面向 DeepSeek 接口 |
| 版式保留 | 保留段落、表格、公式和页面结构，适合论文与技术文档 |
| 结果导出 | 支持 PDF、Markdown、ZIP 下载 |
| 任务队列 | SQLite 记录任务状态，前端自动轮询刷新 |

## 快速启动

需要 Python 3.11+。

```bash
git clone https://github.com/TonyLiangP2010405/retainpdf-server.git
cd retainpdf-server

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

启动后打开：

| 页面 | 地址 |
| --- | --- |
| 前端工作台 | http://127.0.0.1:8000 |
| OpenAPI 文档 | http://127.0.0.1:8000/docs |
| 健康检查 | http://127.0.0.1:8000/health |

## Docker 部署

```bash
cp .env.example .env
docker compose up -d --build
docker compose logs -f server
```

默认对外暴露 `8000` 端口，上传文件、输出文件和 `jobs.db` 会保存在 Docker volume `retain_pdf_data` 中。

## 前端使用流程

1. 打开 `http://127.0.0.1:8000`。
2. 在右侧翻译设置中填写翻译 API Key。
3. 选择目标语言、翻译模式、渲染模式和输出格式。
4. 拖拽或选择 PDF 文件。
5. 在“翻译记录”中查看任务进度，完成后下载结果。

高级模型配置在页面底部的“API 接口”区域，可调整 `model`、`base_url`、`OCR Provider` 和 OCR API Key。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SERVER_HOST` | `0.0.0.0` | 服务监听地址 |
| `SERVER_PORT` | `8000` | 服务监听端口 |
| `UPLOAD_DIR` | `./data/uploads` | 上传文件目录 |
| `OUTPUT_DIR` | `./data/outputs` | 翻译结果目录 |
| `TEMP_DIR` | `./data/temp` | 临时文件目录 |
| `JOB_DB` | `./data/jobs.db` | SQLite 任务数据库 |
| `RETAIN_PDF_ROOT` | `./retain-pdf` | 原 RetainPDF 项目目录 |
| `TRANSLATOR_PROVIDER` | `deepseek` | 翻译服务提供商 |
| `TRANSLATOR_API_KEY` | 空 | 翻译 API Key，生产环境必填 |
| `TRANSLATOR_BASE_URL` | `https://api.deepseek.com/v1` | OpenAI-compatible Base URL |
| `TRANSLATOR_MODEL` | `deepseek-chat` | 默认模型 |
| `OCR_PROVIDER` | `mineru` | OCR 提供商 |
| `OCR_API_KEY` | 空 | OCR API Key |
| `OCR_ENABLED` | `true` | 是否默认启用 OCR |
| `MAX_UPLOAD_SIZE_MB` | `200` | 单文件上传大小限制 |
| `MAX_CONCURRENT_JOBS` | `2` | 最大并发任务数 |
| `TRANSLATION_MODE` | `sci` | `fast` / `precise` / `sci` |
| `RENDER_MODE` | `typst` | `auto` / `overlay` / `typst` / `dual` |
| `DEFAULT_TARGET_LANG` | `zh` | 默认目标语言 |
| `LOG_LEVEL` | `INFO` | 日志级别 |

不要把 API Key 写进代码仓库；使用 `.env`、环境变量或部署平台的密钥管理。

## API 摘要

### 健康检查

```http
GET /health
```

### 获取默认配置

```http
GET /api/v1/config/default
```

### 创建翻译任务

```http
POST /api/v1/jobs
Content-Type: multipart/form-data
```

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | File | 是 | PDF 文件 |
| `source_lang` | string | 否 | 源语言代码 |
| `target_lang` | string | 否 | 默认 `zh` |
| `translator` | string | 否 | 翻译提供商覆盖 |
| `ocr_enabled` | boolean | 否 | 默认 `true` |
| `preserve_layout` | boolean | 否 | 默认 `true` |
| `output_format` | string | 否 | `pdf` / `markdown` / `zip` / `all` |
| `config` | string | 否 | JSON 字符串，高级配置 |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/jobs \
  -F "file=@example.pdf" \
  -F "target_lang=zh" \
  -F "ocr_enabled=true" \
  -F "output_format=pdf"
```

### 查询任务

```http
GET /api/v1/jobs/{job_id}
GET /api/v1/jobs?limit=50
```

### 下载结果

```http
GET /api/v1/jobs/{job_id}/download?format=pdf
```

支持 `format=pdf`、`markdown`、`zip`、`all`。

### 删除任务

```http
DELETE /api/v1/jobs/{job_id}
```

## 任务状态

| 状态 | 含义 |
| --- | --- |
| `queued` | 已创建，等待执行 |
| `running` | 正在执行 |
| `succeeded` | 已完成，可以下载 |
| `failed` | 执行失败，查看 `error` 字段 |
| `cancelled` | 已取消 |

| 阶段 | 含义 |
| --- | --- |
| `upload` | 文件已保存 |
| `ocr` | OCR 识别中 |
| `translate` | 翻译中 |
| `layout` | 排版回填中 |
| `render` | 最终渲染中 |
| `done` | 结束 |

## 本地验证

```bash
python -m compileall app
curl -fsS http://127.0.0.1:8000/health
curl -fsS http://127.0.0.1:8000/api/v1/config/default | python -m json.tool
```

前端变更建议额外跑一次浏览器检查：桌面视口、移动视口、控制台错误、保存配置、非法文件上传提示和任务列表刷新。

## 目录结构

```text
.
├── app/
│   ├── main.py
│   ├── api/routes/
│   ├── core/
│   ├── models/
│   ├── services/
│   └── workers/
├── static/
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── assets/
├── docs/
│   └── project-proof.png
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## 上游项目

本服务基于 [wxyhgk/retain-pdf](https://github.com/wxyhgk/retain-pdf) 的 PDF 翻译能力进行服务化封装。当前仓库负责 HTTP API、异步任务、静态前端、Docker 部署与运行文档。

## License

MIT
