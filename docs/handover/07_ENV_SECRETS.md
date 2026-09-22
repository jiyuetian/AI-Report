# 07 · 环境 / 密钥注意事项（ENV_SECRETS）

> **铁律：本仓库不写明文密钥。** 密钥统一进 `backend/.env`（已被 `.gitignore` 忽略，不入库）。`.env.example` 仅含占位/说明。

## 1. 配置文件位置

| 文件 | 作用 | 是否入库 |
|------|------|----------|
| `backend/.env` | 运行时真实密钥（SECRET_KEY / LLM 网关 key / DUCKDB_PATH） | ❌ 忽略 |
| `backend/.env.example` | 模板，含说明与占位，**无真实密钥** | ✅ 入库 |
| `frontend/.env` / `.env.local` | 前端运行配置 | ❌ 忽略（若有） |

## 2. 关键变量（含义，非值）

- `SECRET_KEY`：JWT 签名密钥。dev 默认 `local-dev-secret-key`；**生产必须换强随机值**。
- `DUCKDB_PATH`：业务库路径，相对 `backend/` 解析 → `./data/duckdb/aibi.db`（`718019d` 绝对路径化）。
- `LLM_*`：商汤网关单 key 路由 kimi-k3 / deepseek-v4-flash / glm-5.2 / sensenova-6.8-flash-lite。网关要求 `business_type=chat`；kimi 系列仅允许 `temperature=1`（否则 400）。
- `HTTP_PROXY` / `HTTPS_PROXY`：后端访问 LLM 网关走 `http://127.0.0.1:7897`（Clash）。用单份小写，避免大小写重复导致 MCP 崩溃。

## 3. 密钥来源（不在此写出）

- LLM 网关 key：来自商汤 SenseNova 聚合网关控制台，存入 `backend/.env`。
- JWT mint（联调用）：可用 Python `hmac` + `SECRET_KEY` 本地签发，勿硬编码到代码。

## 4. 安全红线回顾

- 禁止把 `.env`、key、token 写进代码或提交。
- 改密钥方案参考 `docs/CONVENTIONS.md`「dev 密钥方案（不写码）」。
- 若需新增密钥字段：先加 `.env.example` 占位 + `app/core/config.py` 读取 + 文档说明，再让接手方填 `backend/.env`。

## 5. 出网与代理

- 后端→LLM 网关需出网；本机靠 Clash 7897。
- 若后端报网关超时：先确认代理在线、再确认 `business_type=chat` 与 `temperature` 合规（kimi=1）。
