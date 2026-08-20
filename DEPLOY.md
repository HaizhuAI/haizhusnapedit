# 部署指南（Cloud 版 — 不跑任何本地模型）

> **重要**：本项目默认走 **SnapEdit 官方云端 API**（`SNAPEDIT_BACKEND=cloud`）。
> App 里所有 AI 处理（抠图/增强/修复/动漫/美容/天空/证件照/擦除）本来就在官方云端完成，
> 本服务只是把官方 API 封装成 OpenAI 兼容接口 + WebUI。**部署只需要联网，不需要 GPU，
> 不需要下载任何模型，4GB 内存都嫌多。**

## 后端开关

| 环境变量 | 值 | 说明 |
|---|---|---|
| `SNAPEDIT_BACKEND` | `cloud`（默认） | 直连 SnapEdit 官方云，零本地模型 |
| `SNAPEDIT_BACKEND` | `local` | 本地 CPU 引擎兜底（会下载 u2net 模型） |

## 三种方式

### 方式一：裸机直接跑（推荐，最简单）

```bash
# 1. 上传整个 snapedit-webui 目录到目标机
# 2. 装 Python 3.10+（含 venv 支持）：
#    Ubuntu/Debian:  sudo apt install python3 python3-venv
# 3. 启动（自动建 venv + 装依赖）：
cd snapedit-webui
./start.sh
# 打开 http://<服务器IP>:8000
```

### 方式二：Docker

```bash
docker compose up -d --build
# 或
docker build -t snapedit-studio .
docker run -d --name snapedit -p 8000:8000 -v $(pwd)/data:/app/data snapedit-studio
```

### 方式三：systemd 常驻服务（生产）

```bash
sudo mkdir -p /opt && sudo cp -r snapedit-webui /opt/
cd /opt/snapedit-webui && ./start.sh   # 先初始化 venv（第一次跑完 Ctrl+C）
sudo cp deploy/snapedit.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now snapedit
sudo systemctl status snapedit
```

## 认证配置（v2 必读）

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `ADMIN_PASSWORD` | `SnapEdit@2026` | WebUI 管理员密码，**生产必须改** |
| `API_TOKENS` | `snapedit-demo-token-2026` | API Bearer Token，逗号分隔多值 |
| `SESSION_SECRET` | 随机生成 | 会话签名密钥；不设则重启后所有 WebUI 会话失效 |
| `SESSION_TTL` | `604800` | 会话有效期（秒） |

- WebUI：浏览器打开后需输入管理员密码，成功签发 HttpOnly + SameSite=Lax 会话 Cookie
- API：所有 `/v1/*` 接口强制校验 `Authorization: Bearer <token>`（错误/缺失返回 401）
- `/healthz`、`/static`、`/outputs`（结果图片 URL）保持公开；输出文件名随机不可枚举
- OpenAI SDK 用法：`OpenAI(base_url="http://<host>:8000/v1", api_key="<API_TOKENS 里任意一个>")`

```
## 部署检查清单（Cloud 版）

| 项 | 要求 | 说明 |
|---|---|---|
| Python | ≥3.10 | venv 必须可用 |
| 内存 | ≥1GB 即可 | **不跑本地模型，无模型驻留** |
| CPU | 任意 | 只做转发 + 少量像素合成 |
| 磁盘 | ≥500MB | venv ~400MB |
| 网络 | **必须能访问外网** | 直连 `be-prod-1.snapedit.app`（Cloudflare 全球可达） |
| 端口 | 8000 | 可改 PORT 环境变量 |

> 离线/内网环境无法用 cloud 后端（必须联网）。若必须离线，把 `SNAPEDIT_BACKEND=local`
> 设上，首次调用会从 GitHub 下载 u2net.onnx（176MB）本地推理，功能降级为纯 CPU 版本。

## 反向代理（可选）

nginx 示例：
```nginx
server {
    listen 80;
    server_name snapedit.example.com;
    client_max_body_size 50m;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_read_timeout 300s;
    }
}
```

## 验证部署

```bash
## 验证部署

```bash
curl http://localhost:8000/healthz
# {"status":"ok","tools":[...]}
curl http://localhost:8000/v1/models | python3 -m json.tool
```

## 常见问题

- **首次处理慢**：正常，在下载模型；之后秒级
- **502/超时**：大图超分 CPU 慢，反向代理调大 proxy_read_timeout，或前端用小图
- **端口被占**：`PORT=9000 ./start.sh`
- **内存不足**：处理前先用小图（≤1500px），或换 8GB 机器
