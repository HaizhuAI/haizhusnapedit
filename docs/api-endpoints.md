# SnapEdit 官方 API 逆向记录（be-prod-1.snapedit.app）

Base: `https://be-prod-1.snapedit.app/`
鉴权: `Authorization: Bearer <firebase idToken>`（AI 端点 403 无鉴权）
静态资源: `https://assets.snapedit.app/...` 匿名可达

## AI 功能端点（POST multipart，响应 `{image_id, image}` base64）

| 功能 | 路径 |
|---|---|
| 背景移除 | api/rmbg/v1 |
| 增强 v2 | api/enhance/v2 |
| 增强 Pro | api/enhance/v2/pro |
| 背景增强 | api/enhance/v1/bg |
| 物体移除（擦除） | api/object_removal/v5/erase |
| 对象自动建议 | api/object_removal/v7/auto_suggest |
| 文字检测 | api/object_removal/v5/text_detection |
| 电线检测 | api/object_removal/v6/wire_detection |
| 老照片修复 | api/restore/v1 |
| 人像美容 | api/retouch/v1/ |
| 皮肤美化 | api/skin_beauty/v1 |
| 天空替换 | api/sky/v1 |
| 实体分割 | api/entity_seg/v1 |
| 动漫生成 | api/fairyai/v1/gen_image |
| 发型 AI | api/hairstyler/v1 |
| 表情迁移 | api/face_expression/v1/translate |
| 姿势推荐 | api/recommendation/v1/pose |
| 背景生成 | api/bgen/v1 |
| 证件照 v1/v2 | api/passport/v1, api/passport/v2 |
| 风格重绘 | api/restyle/v1 |
| 图像编辑 v2 | api/image-edit/v2, api/image-edit/v2/multi |
| AI 效果（任务） | api/image-editing/v1/tasks (POST), api/image-editing/v1/tasks/{taskId} (GET 轮询) |
| AI 效果（直出） | api/image-edit/v2 |
| 视频生成 | api/video/v1/generate, api/video/v1/tasks, api/video/v1/tasks/{task_id} |
| Agent 推荐 | api/agent/v1/recommendations |
| 用户信息 | api/users/v1/userInfo (GET, Authorization) |
| 订阅 | api/subscription/v1/{subscription_id} |
| 模板 | api/templates/v1/categories |
| 完整性校验 | integrity-service/v1/verify (payload->TokenResponse{token, expiredAt}) |

## 静态配置（匿名）
- assets.snapedit.app/stickers/stickers.json
- assets.snapedit.app/filter/snapedit_photo_filter.json
- assets.snapedit.app/passport/{passport,clothes,backdrops_v2}.json
- assets.snapedit.app/fairyai/anime_styles_6mar25.json
- assets.snapedit.app/restyle/styles.json
- assets.snapedit.app/skywizard/backgrounds.json
- assets.snapedit.app/aihair/ai_hair_styles_v1.json

## 请求参数（multipart 字段）
- input_image0 / input_image1 / mask_image / styleId / prompt / mode / strength /
  guidanceScale / inferenceSteps / outW / outH / clientId / query / runFast
- 尺寸限制配置: standard 1200 / high 1920 / pro 3000（RemoveObjectConfig）
- enhance: standard_upload 1200, premium_upload 1200, max 3000

## 响应模型
- 对象扫描: {detected_objects:[{accuracy,box[4],mask(png b64),mask_id,object_description,object_type}], event_id, session_id, suggest_object_ids}
- 任务: AIEffectCreateTaskResponse / AIEffectTaskStatusResponse / AIEffectDirectResponse

## 破解层
- bin.mt.signature.KillerApplication: ApkSignatureKillerEx（native SignatureKiller 干掉签名校验，hardcode 原 Google 证书）
- com.Level360: AndroForever 更新检查 https://raw.githubusercontent.com/androforever-source/Updatedbyandrof/.../SnapEdit%20Nuevo
- 内置 Firebase: project snapedit-android-92fd5, sender 719234618152,
  api_key s2svtF6qSCwBCI0Xjm4MvY0fBGVrtoUCbidhNmkvrJA=,
  google_api_key AIzaSyAHM0kIlyPfLmFRnLLa99r55dbhExdCxbU
