# SnapEdit Studio — AI 照片编辑器能力移植项目

从 SnapEdit Premium v7.7.4（Android 版）逆向提取能力清单，
封装为 **SnapEdit 官方云端直连 + OpenAI 兼容 API + WebUI** 三合一服务。
**App 里的 AI 全在官方云端，本项目直接打通官方 API（本地铸 JWT 解锁高级版），部署不需要跑任何本地模型。**
高级版功能全部开放，无次数/尺寸限制，无水印。

## 能力映射（APK 功能 → 本服务工具）

| SnapEdit 原功能 | 官方云端 Endpoint | 本服务实现 |
|---|---|---|
| 移除背景 (Remove Background) | `rmbg/v1` | 直连云端 → 透明/纯色背景 |
| 超级擦除 (Super Erase) | `object_removal/v5/erase` | 云端扫描+掩码擦除 |
| 移除人物/物品 | `object_removal/v7/auto_suggest` | 云端自动主体检测 |
| AI 增强 (Enhance) | `enhance/v2` | 云端人脸增强 + 拼回原图 |
| 老照片修复 (Restore) | `restore/v1` | 云端修复 |
| 动漫化 (Fairy AI) | `fairyai/v1/gen_image` | 云端 108 风格动漫化 |
| 人像美容 (Retouch) | `retouch/v1/` | 云端美容 |
| 天空替换 (Sky Wizard) | `sky/v1` | 云端天空分割 + 150 背景合成 |
| 证件照 (Passport) | `passport/v1` | 云端抠图 + 本地证件合成 |
| 滤镜 (Filters) | 本地 | 纯色彩处理，无需 AI |
| 文字/水印擦除 | `object_removal/v5/text_detection` | 云端文字检测 + 擦除 |

> 原 APK 的 AI 推理全部在 SnapEdit 官方云端（返回 `{image_id, image}` base64）。
> 本项目从 APK 还原官方 API + 鉴权链（本地铸 JWT 解锁高级版），**直连官方云，零本地模型**。
> 后端开关：`SNAPEDIT_BACKEND=cloud`（默认）走官方云；`SNAPEDIT_BACKEND=local` 走本地 CPU 兜底。

## 快速开始

```bash
cd snapedit-webui
./start.sh                # 自动建 venv + 装依赖 + 启动 :8000
# 或手动：
# python3 -m venv venv && venv/bin/pip install -r requirements.txt
# venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

打开 `http://localhost:8000` 即 WebUI。

## 访问控制（v2）

> **WebUI 需要管理员密码**（默认 `SnapEdit@2026`，环境变量 `ADMIN_PASSWORD` 可改，上生产必须改）。
> **API 需要 Bearer Token**（默认 `snapedit-demo-token-2026`，环境变量 `API_TOKENS` 逗号分隔可配多个）。

```bash
# .env / 环境变量：
ADMIN_PASSWORD=你的管理员密码        # WebUI 登录
API_TOKENS=token1,token2             # API 调用凭证（OpenAI 兼容 key）
SESSION_SECRET=一串随机长字符串       # 会话签名密钥（建议 32+ 位）
SESSION_TTL=604800                   # 会话有效期秒（默认 7 天）
```

- WebUI：打开页面先登录管理员密码，签发 HttpOnly 会话 Cookie
- API：所有 `/v1/*` 接口必须带 `Authorization: Bearer <token>`（OpenAI SDK 直接把它当 api_key 传）
- 401 场景：未带凭证 / token 错误 / 会话过期，均返回 401

```bash
# API 调用示例（带 token）
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer <API_TOKEN>"

# WebUI 登录
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"password":"<ADMIN_PASSWORD>"}'   # 返回 cookie，后续请求自动带
```

## OpenAI 兼容 API

### 列出模型
```bash
curl http://localhost:8000/v1/models
```

### 图片编辑（`POST /v1/images/edits`，OpenAI 格式）
```bash
# 背景移除
curl -X POST http://localhost:8000/v1/images/edits \
  -F image=@photo.jpg \
  -F model=snapedit/remove_background \
  -F response_format=url

# 增强 + 超分（prompt 传 JSON 参数）
curl -X POST http://localhost:8000/v1/images/edits \
  -F image=@photo.jpg \
  -F model=snapedit/enhance \
  -F 'prompt={"strength":4,"upscale":2}'

# 动漫化
curl -X POST http://localhost:8000/v1/images/edits \
  -F image=@photo.jpg \
  -F model=snapedit/anime \
  -F 'prompt={"style":"ghibli"}'

# 自动路由（prompt 关键词）
curl -X POST http://localhost:8000/v1/images/edits \
  -F image=@photo.jpg -F model=snapedit/auto -F 'prompt=移除背景'
```

### 直接工具调用（`POST /v1/tools/{tool_id}`）
```bash
curl -X POST http://localhost:8000/v1/tools/sky \
  -F image=@photo.jpg -F 'params_json={"sky":"sunset"}'

curl -X POST http://localhost:8000/v1/tools/passport \
  -F image=@photo.jpg -F 'params_json={"bg_color":"blue","size":"1inch"}'

curl -X POST http://localhost:8000/v1/tools/remove_object \
  -F image=@photo.jpg -F mask=@mask.png -F 'params_json={"mode":"mask"}'
```

### 流水线（`POST /v1/pipeline`）
```bash
curl -X POST http://localhost:8000/v1/pipeline \
  -F image=@photo.jpg \
  -F 'steps_json=[{"tool":"remove_background"},{"tool":"enhance","params":{"strength":3}}]'
```

### Python 客户端
```python
import requests, base64
r = requests.post("http://localhost:8000/v1/images/edits",
    files={"image": open("a.jpg","rb")},
    data={"model": "snapedit/remove_background", "response_format": "b64_json"})
b64 = r.json()["data"][0]["b64_json"]
open("out.png","wb").write(base64.b64decode(b64))
```

## 工具 ID 表

`remove_background` `remove_object` `enhance` `restore` `anime` `retouch` `sky` `passport` `filter` `text_erase`

## 目录结构

```
snapedit-webui/
├── backend/
│   ├── app.py              # FastAPI 服务（OpenAI 兼容 + WebUI 静态）
│   ├── cloud/              # 官方云 provider（JWT 铸签 + 端点调用 + 合成）
│   │   └── snapedit_cloud.py
│   └── engines/            # 本地 CPU 引擎（SNAPEDIT_BACKEND=local 时使用）
│       ├── base.py         # 工具基类 + 注册表
│       ├── remove_bg.py    # U2Net 抠图
│       ├── object_remove.py# 检测 + inpaint
│       ├── enhance.py      # 增强/超分
│       ├── restore.py      # 老照片修复
│       ├── anime.py        # 动漫化
│       ├── retouch.py      # 人像美容
│       ├── sky.py          # 天空替换
│       ├── passport.py     # 证件照
│       └── filters.py      # 滤镜 + 文字擦除
├── frontend/               # WebUI (index.html / app.js / style.css)
├── data/outputs/           # 结果输出
├── apk/                    # 原始 APK + 反编译产物
└── start.sh
```

## 逆向资料（APK 分析结论）

- 原始包：`snapedit.app.remove`，7 dex，包内含 TFLite 运行时 + ffmpeg 全家桶
- **AI 全云端**：`https://be-prod-1.snapedit.app/api/...`，响应 `{image_id, image(base64)}`
- 功能端点已还原 40+：见 `docs/api-endpoints.md`
- 鉴权：本地铸 HS256 JWT（密钥在 res `api_key`，`is_premium=true` 解锁高级版）+ `X-INTEGRITY-TOKEN`（`integrity-service/v1/verify`）双头直连
- 安全组件：`bin.mt.signature.KillerApplication`（签名校验）+ `com.Level360`（更新检查）
- 加密模型容器：assets 下 50 个 `IAP` 格式文件（magic `00 49 41 50`），字节自定义加密格式

## 已知限制

- **cloud 后端必须联网**（直连官方 `be-prod-1.snapedit.app`）；内网离线请切 `SNAPEDIT_BACKEND=local`
- 上传图片建议 ≤2000px（官方 enhance/sky 等端点有 body 上限）
- 物体移除支持自动（扫第一个主体）或上传掩码；文字擦除自动检测文字区域
