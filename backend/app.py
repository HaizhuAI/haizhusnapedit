"""SnapEdit WebUI + OpenAI-compatible API service.
Serves local CPU AI tools (background removal, object erase, enhance, restore,
anime, retouch, sky, passport, filters) plus optional SnapEdit cloud provider."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import io, json, os, time, uuid, base64, logging
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image

from engines import base as eng
# load all tool engines (register into ToolRegistry)
from engines import remove_bg, object_remove, enhance, restore, anime, retouch, sky, passport, filters  # noqa: F401
from engines.base import ToolRegistry, safe_run, pil_to_bytes, bytes_to_pil

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("snapedit.api")

# Cloud backend: use official SnapEdit cloud (no local models) unless SNAPEDIT_BACKEND=local
from cloud.snapedit_cloud import cloud_backend_enabled, install_cloud_tools
if cloud_backend_enabled():
    install_cloud_tools(replace=True)
    log.info("backend=cloud (SnapEdit official API, no local models)")
else:
    log.info("backend=local (CPU engines)")


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR = DATA_DIR / "outputs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------- auth ----------
from security import (ADMIN_PASSWORD, API_TOKENS, SESSION_TTL, SESSION_COOKIE,
                      auth_middleware, issue_session, valid_session,
                      set_session_cookie, clear_session_cookie)

app = FastAPI(title="SnapEdit AI API", version="7.7.4", description="SnapEdit 能力移植：OpenAI 兼容 API + WebUI")
app.middleware("http")(auth_middleware)


# ---------- auth endpoints ----------
@app.post("/api/auth/login")
async def login(request: Request):
    """Admin password login -> HttpOnly session cookie."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    pw = str(body.get("password", ""))
    import hmac as _hmac
    if not _hmac.compare_digest(pw, ADMIN_PASSWORD):
        raise HTTPException(401, "wrong password")
    resp = JSONResponse({"ok": True, "expires_in": SESSION_TTL, "api_tokens": len(API_TOKENS)})
    set_session_cookie(resp, issue_session())
    return resp

@app.post("/api/auth/logout")
def logout():
    resp = JSONResponse({"ok": True})
    clear_session_cookie(resp)
    return resp

@app.get("/api/auth/status")
def auth_status(request: Request):
    """Public: tell the WebUI whether the browser holds a valid admin session."""
    return {"authenticated": valid_session(request.cookies.get(SESSION_COOKIE)),
            "api_tokens": len(API_TOKENS)}

# ---------- helpers ----------
def _save_output(img: Image.Image, prefix: str) -> str:
    name = f"{prefix}_{uuid.uuid4().hex[:10]}.png"
    path = OUT_DIR / name
    img.save(path, format="PNG")
    return f"/outputs/{name}"

def _img_to_b64(img: Image.Image, fmt: str = "PNG") -> str:
    data = pil_to_bytes(img, fmt=fmt)
    return base64.b64encode(data).decode()

# ---------- OpenAI-compatible endpoints ----------
@app.get("/v1/models")
def list_models():
    """OpenAI-compatible model list."""
    models = []
    for t in ToolRegistry.all().values():
        models.append({
            "id": f"snapedit/{t.id}",
            "object": "model",
            "created": 1780000000,
            "owned_by": "snapedit",
            "permission": [],
            "root": f"snapedit/{t.id}",
            "parent": None,
            "description": t.description,
            "params": t.params,
        })
    # also expose a convenience aggregate model
    models.append({
        "id": "snapedit/auto",
        "object": "model", "created": 1780000000, "owned_by": "snapedit",
        "description": "自动识别工具（根据 prompt 关键词路由）", "params": {},
    })
    return {"object": "list", "data": models}


@app.post("/v1/images/edits")
async def images_edits(
    image: UploadFile = File(...),
    prompt: Optional[str] = Form(None),
    model: str = Form("snapedit/remove_background"),
    mask: Optional[UploadFile] = File(None),
    n: int = Form(1),
    size: Optional[str] = Form(None),
    response_format: str = Form("url"),
):
    """OpenAI images/edit compatible endpoint.
    model selects which tool: snapedit/remove_background, snapedit/remove_object,
    snapedit/enhance, snapedit/restore, snapedit/anime, snapedit/retouch,
    snapedit/sky, snapedit/passport, snapedit/filter, snapedit/text_erase.
    prompt may carry tool params as JSON (e.g. {"sky":"sunset","strength":4})."""
    raw = await image.read()
    if not raw:
        raise HTTPException(400, "empty image")
    try:
        img = bytes_to_pil(raw)
    except Exception as e:
        raise HTTPException(400, f"cannot decode image: {e}")

    tool_id = model.replace("snapedit/", "")
    tool = ToolRegistry.get(tool_id)
    if tool is None:
        # auto route by prompt
        tool = _auto_route(prompt or "")
        if tool is None:
            raise HTTPException(404, f"unknown model {model}")

    params = {}
    if prompt:
        try:
            stripped = prompt.strip()
            if stripped.startswith("{"):
                params = json.loads(stripped)
            else:
                params["prompt"] = stripped
                # simple keyword routing for params
                for key in ("sky", "style", "filter", "bg_color", "strength", "mode", "size"):
                    if key in stripped.lower():
                        # skip, too fuzzy
                        pass
        except Exception:
            params["prompt"] = prompt

    mask_img = None
    if mask is not None:
        mraw = await mask.read()
        if mraw:
            try:
                mask_img = bytes_to_pil(mraw)
            except Exception:
                pass

    # size param: "512x512" style -> resize input
    if size and "x" in size:
        try:
            w, h = map(int, size.lower().split("x"))
            img = img.resize((w, h), Image.LANCZOS)
        except Exception:
            pass

    params.setdefault("mask_image", mask_img)
    r = safe_run(tool, img, **params)
    if r.error:
        raise HTTPException(500, r.error)

    if response_format == "b64_json":
        data = {"b64_json": _img_to_b64(r.image)}
    else:
        url = _save_output(r.image, tool.id)
        data = {"url": url}

    data["elapsed_seconds"] = round(r.elapsed, 3)
    data["tool"] = tool.id
    data.update({k: v for k, v in r.data.items() if not isinstance(v, (bytes, bytearray))})
    return {"created": int(time.time()), "data": [data]}


@app.post("/v1/tools/{tool_id}")
async def run_tool(
    tool_id: str,
    image: UploadFile = File(...),
    mask: Optional[UploadFile] = File(None),
    response_format: str = Form("url"),
    params_json: Optional[str] = Form(None),
):
    """Direct tool endpoint: POST image + optional params_json."""
    tool = ToolRegistry.get(tool_id)
    if tool is None:
        raise HTTPException(404, f"unknown tool {tool_id}")

    raw = await image.read()
    try:
        img = bytes_to_pil(raw)
    except Exception as e:
        raise HTTPException(400, f"cannot decode image: {e}")

    params = {}
    if params_json:
        try:
            params = json.loads(params_json)
        except Exception:
            params = {}
    mask_img = None
    if mask is not None:
        mraw = await mask.read()
        if mraw:
            try:
                mask_img = bytes_to_pil(mraw)
            except Exception:
                pass
    params.setdefault("mask_image", mask_img)

    r = safe_run(tool, img, **params)
    if r.error:
        raise HTTPException(500, r.error)

    if response_format == "b64_json":
        payload = {"b64_json": _img_to_b64(r.image)}
    else:
        payload = {"url": _save_output(r.image, tool.id)}
    payload["elapsed_seconds"] = round(r.elapsed, 3)
    payload["tool"] = tool.id
    for k, v in r.data.items():
        if not isinstance(v, (bytes, bytearray)):
            payload[k] = v
    return payload


@app.get("/v1/tools")
def list_tools():
    return {"tools": ToolRegistry.summary()}


# ---------- convenience: pipeline (multiple tools chained) ----------
@app.post("/v1/pipeline")
async def run_pipeline(
    image: UploadFile = File(...),
    steps_json: str = Form("[]"),
):
    """Chain multiple tools: steps_json = [{"tool":"remove_background"},{"tool":"enhance","params":{}}]"""
    try:
        steps = json.loads(steps_json)
    except Exception:
        steps = []
    if not isinstance(steps, list) or not steps:
        raise HTTPException(400, "steps must be non-empty list")

    raw = await image.read()
    img = bytes_to_pil(raw)
    results = []
    for st in steps:
        tid = st.get("tool")
        tool = ToolRegistry.get(tid)
        if tool is None:
            raise HTTPException(404, f"unknown tool {tid}")
        params = dict(st.get("params", {}))
        r = safe_run(tool, img, **params)
        if r.error:
            raise HTTPException(500, f"{tid}: {r.error}")
        img = r.image
        results.append({"tool": tid, "elapsed_seconds": round(r.elapsed, 3)})
    url = _save_output(img, "pipeline")
    return {"url": url, "steps": results, "elapsed_seconds": round(sum(x["elapsed_seconds"] for x in results), 3)}


def _auto_route(prompt: str) -> Optional[eng.BaseTool]:
    p = prompt.lower()
    mapping = [
        ("remove_background", ["background", "bg", "抠图", "背景", "移除背景", "透明"]),
        ("remove_object", ["remove object", "object", "erase", "擦除", "移除", "删除", "物体", "人物移除", "super"]),
        ("enhance", ["enhance", "增强", "清晰", "高清", "deblur", "upscale", "超分"]),
        ("restore", ["restore", "修复", "老照片", "old photo", "scratch", "划痕"]),
        ("anime", ["anime", "动漫", "动画", "cartoon", "fairy", "ghibli"]),
        ("retouch", ["retouch", "美容", "皮肤", "美颜", "skin", "portrait", "人像"]),
        ("sky", ["sky", "天空", "skywizard"]),
        ("passport", ["passport", "证件", "id photo", "idphoto"]),
        ("filter", ["filter", "滤镜", "vivid", "bw", "vintage"]),
        ("text_erase", ["text", "文字", "watermark", "水印"]),
    ]
    for tid, kws in mapping:
        for kw in kws:
            if kw in p:
                return ToolRegistry.get(tid)
    return None



# ---------- cloud asset catalogs ----------
@app.get("/v1/styles/anime")
def list_anime_styles():
    """Anime style catalog from SnapEdit official assets."""
    import requests as _rq
    ua = {"User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7)"}
    try:
        r = _rq.get("https://assets.snapedit.app/fairyai/anime_styles_6mar25.json", timeout=30, headers=ua)
        r.raise_for_status()
        return {"styles": r.json()}
    except Exception as e:
        raise HTTPException(502, f"cannot fetch anime styles: {e}")

@app.get("/v1/backgrounds/sky")
def list_sky_backgrounds():
    import requests as _rq
    ua = {"User-Agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7)"}
    try:
        r = _rq.get("https://assets.snapedit.app/skywizard/backgrounds.json", timeout=30, headers=ua)
        r.raise_for_status()
        d = r.json()
        if isinstance(d, dict) and isinstance(d.get("backgrounds"), list):
            return {"backgrounds": d["backgrounds"]}
        return {"backgrounds": d}
    except Exception as e:
        raise HTTPException(502, f"cannot fetch sky backgrounds: {e}")

# ---------- static / WebUI ----------
FRONT = ROOT / "frontend"
@app.get("/")
def index():
    return FileResponse(FRONT / "index.html")

app.mount("/outputs", StaticFiles(directory=str(OUT_DIR)), name="outputs")
app.mount("/static", StaticFiles(directory=str(FRONT)), name="static")

@app.get("/healthz")
def healthz():
    return {"status": "ok", "tools": list(ToolRegistry.all().keys()), "time": time.time()}
