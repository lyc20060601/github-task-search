# Self-Hosted Open-Source Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 GitHub Task Search 打包成不依赖云服务器、其他用户可在自己电脑上安全部署的开源项目。

**Architecture:** 保留现有 Next.js 前端、FastAPI 后端和 Docker Sandbox。新增生产容器与根目录 Docker Compose，前端通过运行时配置连接后端，后端只从环境变量读取密钥。默认启动搜索、智能搜索、推荐和手动仓库验证；不把任何密钥、宿主机目录、Docker socket 暴露给应用容器。

**Tech Stack:** Next.js, FastAPI, Uvicorn, Docker Compose, GitHub API, DeepSeek-compatible API.

---

### Task 1: 清理发布边界与敏感信息

**Files:**
- Modify: `github-task-search/.gitignore`
- Create: `github-task-search/.dockerignore`
- Verify: `github-task-search/backend/.env.example`

- [x] 检查并清理发布目录中的可删除缓存；Windows 锁定的本地依赖/测试目录保留，但已同时从 Git 和 Docker context 排除；未删除用户工作区外文件。
- [x] 确认 `.gitignore` 忽略 `.env`、密钥、构建产物、Python/Node 缓存。
- [x] 创建 `.dockerignore`，排除 `.env*`（保留 `.env.example` 作为源码占位模板）、`.git`、`node_modules`、`.next`、`.venv`、`__pycache__`、`*.log`、测试缓存。
- [x] 用文本扫描检查 GitHub Token、LLM Key 和本机绝对路径；唯一绝对路径命中是安全测试中的虚构值 `C:/Users/example/.env`。
- [x] 验收：已跟踪文件中的真实密钥格式命中数为 0，且 `.env` 不在 Git 或 Docker build context 中。

### Task 2: 固定后端容器运行方式

**Files:**
- Create: `github-task-search/backend/Dockerfile`
- Modify: `github-task-search/backend/requirements.txt` only if a production dependency is missing

- [x] 使用轻量 Python 3.12 slim 基础镜像，设置工作目录 `/app`，先复制 `requirements.txt` 再安装依赖以利用缓存。
- [x] 复制后端源码，使用 UID/GID 10001 的非 root 用户运行。
- [x] 未在镜像构建阶段执行 GitHub 项目代码、Docker Sandbox、依赖安装测试或任何真实搜索。
- [x] 使用 `uvicorn main:app --host 0.0.0.0 --port 8000` 启动。
- [x] 加入 `HEALTHCHECK` 请求 `/`，且镜像与测试容器均未注入密钥。
- [x] 验收：镜像构建成功；容器身份为 `uid=10001(app)`；`/` 返回 API 消息；健康状态为 `healthy`。

### Task 3: 固定前端容器运行方式

**Files:**
- Create: `github-task-search/frontend/Dockerfile`
- Create: `github-task-search/frontend/.dockerignore`
- Modify: `github-task-search/frontend/next.config.ts` if standalone output is needed

- [x] 使用 multi-stage build：依赖安装、Next.js 构建、最小 standalone 运行镜像。
- [x] 通过 `NEXT_PUBLIC_API_BASE_URL` 构建参数连接浏览器可访问的后端地址；未向前端传入后端密钥。
- [x] 使用 UID/GID 10001 的非 root 用户启动 standalone `server.js`，监听 `0.0.0.0:3000`。
- [x] 加入前端 HTTP 健康检查。
- [x] 验收：Next.js/TypeScript 生产构建成功；首页可加载；容器身份为 `uid=10001(app)`；健康状态为 `healthy`；密钥环境变量数量为 0。

### Task 4: 创建一键启动 Compose

**Files:**
- Create: `github-task-search/docker-compose.yml`
- Create: `github-task-search/.env.example`

- [x] 定义 `backend` 和 `frontend` 两个服务，分别暴露 `8000` 和 `3000`；默认用户访问 `http://localhost:3000`。
- [x] 后端注入 `GITHUB_TOKEN`、`LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`、`FRONTEND_ORIGIN`，只允许通过用户本机 `.env` 提供，不写入镜像。
- [x] 前端注入 `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`，确保浏览器使用宿主机可访问地址，不使用容器内部 hostname。
- [x] 不挂载用户主目录、SSH 目录或 Docker socket；不使用 `privileged`。
- [x] 为两个服务设置 restart policy、健康检查和后端健康依赖；未让验证任务自动执行。
- [x] 保留“用户点击验证按钮后才执行”的现有 Docker Sandbox 触发语义。
- [x] 验收：`docker compose config` 成功；使用 `.env.example` 构建并启动两个服务；前端首页、后端 `/` 均正常；两个容器均 healthy；Compose volumes/mounts 为空；前端没有密钥环境变量；测试后容器和网络已清理。

### Task 5: 增强可配置性与本地启动脚本

**Files:**
- Modify: `github-task-search/frontend/app/page.tsx`
- Modify: `github-task-search/backend/main.py` only for production-safe configuration validation/CORS messages
- Create: `github-task-search/scripts/start.ps1`
- Create: `github-task-search/scripts/start.sh`

- [x] 前端所有请求继续使用 `NEXT_PUBLIC_API_BASE_URL`，Compose 默认注入 `http://localhost:8000`，开发回退地址仅用于本地开发。
- [x] 后端 CORS 继续从 `FRONTEND_ORIGIN` 读取并保留 localhost 开发兼容；Compose 不在响应中回显密钥。
- [x] 新增 PowerShell 和 POSIX shell 启动脚本，只执行 Docker/Compose 检查与 `docker compose up --build`，不安装软件、不修改系统 PATH。
- [x] 脚本启动前检查 Docker 命令和 Engine；缺少 `.env` 只输出提醒，不打印任何变量值。
- [x] 验收：PowerShell 语法通过；`start.sh` 在 Alpine 中 `sh -n` 通过；PowerShell detached 启动实际成功，两个服务 healthy，前端/后端 HTTP 检查通过，测试后已清理。

### Task 6: 编写开源使用文档和许可证

**Files:**
- Create/Modify: `github-task-search/README.md`
- Create: `github-task-search/LICENSE`
- Create: `github-task-search/SECURITY.md`
- Create: `github-task-search/CONTRIBUTING.md`

- [x] README 明确项目用途、架构、功能边界、最低硬件/软件要求和服务结构。
- [x] 提供 Windows、Linux、macOS 的 Docker Desktop/Engine 前置条件与逐步启动命令。
- [x] 明确用户必须使用自己的 GitHub Token 和大模型 API Key；禁止把密钥提交到 Git；说明 DeepSeek 按量计费。
- [x] 说明推荐搜索与手动“验证可运行性”的区别，Docker 验证可能耗时和消耗资源，且不会自动运行陌生仓库训练代码。
- [x] 提供常见故障排查：端口占用、后端/API 错误、Docker Engine 未运行、GPU/CUDA 不可用和验证失败。
- [x] 使用 MIT License；SECURITY 文档说明密钥泄露、漏洞报告和不提交敏感信息的规则；CONTRIBUTING 说明测试和安全边界。

### Task 7: 做干净环境验收

**Files:**
- Create: `github-task-search/tests/self_hosted_smoke.ps1` (or a documented manual checklist)

- [x] 在不依赖当前 `.venv`、`node_modules` 和本地开发服务器的前提下运行：`docker compose build`。
- [x] 运行：`docker compose up -d`，检查 `http://localhost:3000`、`http://localhost:8000/`。
- [x] 使用不含真实密钥的 `.env.example` 验证禁用模式和前后端健康状态；验收过程未注入真实密钥。
- [x] 通过 OpenAPI 和 mock 测试验证 `/search`、`/smart-search`、`/recommend-search` 的连接路径；验收未执行真实外部搜索。
- [x] 通过受控 Worker 集成测试确认 Sandbox 约束：非 root、资源限制、超时、无 socket/SSH/主目录挂载、容器销毁；未运行陌生仓库代码。
- [x] 运行 backend 和 frontend 全部测试；记录 failed、skipped、warnings。
- [x] 执行敏感信息扫描和镜像检查，确认镜像没有 `.env` 或密钥环境变量。

### Task 8: 发布到 GitHub

**Files:**
- Repository metadata only after user chooses repository name/visibility

- [ ] 创建 GitHub 仓库，建议公开仓库；首次推送前再次确认 `.env` 未被跟踪。
- [ ] 提交源码、Docker/Compose、README、许可证和测试，不提交 `.next`、`node_modules`、`.venv`、日志、Token。
- [ ] 创建第一个 Release，例如 `v0.1.0-self-hosted`，在 Release notes 中写明环境要求和已知限制。
- [ ] 用全新目录执行 README 的安装命令，验证其他用户不需要 Codex、VS Code 特定配置或本机绝对路径。

### Final Release Gate

- [x] `docker compose config` 成功。
- [x] `docker compose build` 成功。
- [x] 前端和后端容器均以非 root 用户运行。
- [x] 无真实 Token、LLM Key、Authorization header、`.env` 内容进入仓库或镜像。
- [x] `/search`、`/smart-search`、`/recommend-search` 路由正常；`/validate-repository` 仍由用户主动触发。
- [x] backend/frontend 测试通过；基础网站依赖 Docker Engine，启用主机验证 Worker 时还需要本机 Python 和 backend `.venv`。
- [x] README 提供从示例环境文件到 Compose 启动、验证和停止的完整部署步骤。
