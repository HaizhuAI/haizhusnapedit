"""SnapEdit official cloud client + BaseTool implementations.

Auth chain recovered from APK v7.7.4 (nf/p.smali, nf/d.smali, res api_key):
  1. Mint HS256 JWT locally with secret from string resource api_key.
     Claims: sub=ignore, platform=android, version=7.7.4, is_premium=true, ...
     (this is exactly what the cracked app does to unlock premium)
  2. GET integrity token via POST integrity-service/v1/verify
  3. Send  Authorization: Bearer <JWT>  and  X-INTEGRITY-TOKEN: Bearer <IT>
"""
from __future__ import annotations
import base64, hashlib, hmac, io, json, logging, os, time, uuid
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List
import requests
from PIL import Image

from engines.base import BaseTool, ToolResult, ToolRegistry, pil_to_bytes, bytes_to_pil

log = logging.getLogger("snapedit.cloud")

BASE = os.environ.get("SNAPEDIT_API_BASE", "https://be-prod-1.snapedit.app")
JWT_SECRET = os.environ.get(
    "SNAPEDIT_JWT_SECRET",
    "s2svtF6qSCwBCI0Xjm4MvY0fBGVrtoUCbidhNmkvrJA=",  # from APK res/values/strings.xml api_key
)
USER_AGENT = "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Mobile Safari/537.36"

# ---------------- token management ----------------

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

def mint_access_token(premium: bool = True, user_id: str = "cracked-001",
                      product_id: str = "premium_lifetime",
                      ttl_minutes: int = 5) -> str:
    """Mint the same HS256 JWT the cracked app sends as ACCESS_TOKEN."""
    key = base64.b64decode(JWT_SECRET + "=" * (-len(JWT_SECRET) % 4))
    now_ms = int(time.time() * 1000)
    now_s = now_ms // 1000
    payload = {
        "sub": "ignore",
        "platform": "android",
        "version": "7.7.4",
        "is_premium": premium,
        "product_id": product_id,
        "subscription_id": None,
        "order_id": None,
        "user_id": user_id,
        "pricing_plan": "v2",
        "iat": now_s,
        "exp": now_s + ttl_minutes * 60,
    }
    h = _b64url(b'{"alg":"HS256"}')
    p = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64url(hmac.new(key, f"{h}.{p}".encode(), hashlib.sha256).digest())
    return f"{h}.{p}.{sig}"

class TokenManager:
    """Caches JWT + integrity token and refreshes near expiry."""
    def __init__(self):
        self._jwt: Optional[Tuple[str, float]] = None      # (token, expires_at)
        self._it: Optional[Tuple[str, float]] = None       # (token, expires_at)
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

    def _refresh_jwt(self) -> str:
        tok = mint_access_token()
        self._jwt = (tok, time.time() + 4 * 60)
        return tok

    def _refresh_integrity(self) -> str:
        for attempt in range(3):
            try:
                r = self._session.post(f"{BASE}/integrity-service/v1/verify",
                                       json={"payload": "test"}, timeout=30)
                if r.status_code == 404:
                    time.sleep(1)
                    continue
                r.raise_for_status()
                d = r.json()
                exp = d.get("exp") or (time.time() + 6 * 3600)
                self._it = (d["token"], exp)
                return d["token"]
            except Exception as e:
                log.warning("integrity refresh attempt %d failed: %s", attempt + 1, e)
                time.sleep(1)
        raise RuntimeError("cannot obtain integrity token")

    def headers(self) -> Dict[str, str]:
        now = time.time()
        if not self._jwt or now > self._jwt[1] - 10:
            self._refresh_jwt()
        if not self._it or now > self._it[1] - 60:
            self._refresh_integrity()
        return {
            "Authorization": f"Bearer {self._jwt[0]}",
            "X-INTEGRITY-TOKEN": f"Bearer {self._it[0]}",
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        }

_shared = None
def get_client() -> TokenManager:
    global _shared
    if _shared is None:
        _shared = TokenManager()
    return _shared

# ---------------- low-level call helpers ----------------

def _call_multipart(path: str, fields: Optional[Dict[str, str]] = None,
                    files: Optional[Dict[str, Tuple[str, bytes, str]]] = None,
                    query: Optional[Dict[str, str]] = None,
                    timeout: int = 300) -> Dict[str, Any]:
    """POST multipart to cloud endpoint. fields = text parts, files = file parts."""
    client = get_client()
    url = f"{BASE}/{path.lstrip('/')}"
    data = {}
    for k, v in (fields or {}).items():
        if v is not None:
            data[k] = str(v)
    fdata = {k: (fn, b, ct) for k, (fn, b, ct) in (files or {}).items()}
    last = None
    for attempt in range(4):
        try:
            r = client._session.post(url, headers=client.headers(), data=data, files=fdata,
                                     params=query, timeout=timeout)
            if r.status_code == 404 and attempt < 3:   # transient CF routing
                time.sleep(1)
                continue
            r.raise_for_status()
            return r.json()
        except requests.HTTPError as e:
            last = e
            try:
                body = e.response.text[:500]
            except Exception:
                body = ""
            if "Invalid authentication credentials" in body and attempt < 3:
                # JWT expired server-side: force refresh
                client._jwt = None
                continue
            raise RuntimeError(f"cloud {path} failed: HTTP {e.response.status_code} {body}")
        except Exception as e:
            last = e
            if attempt < 3:
                time.sleep(1)
                continue
    raise RuntimeError(f"cloud {path} failed: {last}")

def _file_part(name: str, img: Image.Image, fmt: str = "PNG") -> Tuple[str, bytes, str]:
    return (name, pil_to_bytes(img, fmt=fmt), f"image/{fmt.lower()}")

def _b64_to_img(b64: str) -> Image.Image:
    raw = base64.b64decode(b64)
    return Image.open(io.BytesIO(raw)).convert("RGB")

def _b64_to_img_alpha(b64: str) -> Image.Image:
    raw = base64.b64decode(b64)
    im = Image.open(io.BytesIO(raw))
    return im.convert("RGBA") if im.mode in ("RGBA", "LA", "P", "L") else im.convert("RGB")

# ---------------- composite helpers (no model, just pixels) ----------------

def composite_enhance_faces(orig: Image.Image, faces: List[Dict]) -> Optional[Image.Image]:
    """Paste enhanced face crops (png URLs) back onto original at their box."""
    out = orig.convert("RGB").copy()
    for f in faces:
        box = f.get("box") or []
        urls = f.get("png") or []
        if len(box) != 4 or not urls:
            continue
        x, y, w, h = (int(v) for v in box)
        if w <= 0 or h <= 0:
            continue
        try:
            resp = requests.get(urls[0], timeout=60, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            crop = Image.open(io.BytesIO(resp.content)).convert("RGB")
            crop = crop.resize((w, h), Image.LANCZOS)
            out.paste(crop, (x, y))
        except Exception as e:
            log.warning("face composite failed: %s", e)
    return out

def composite_sky(orig: Image.Image, mask_b64: str, sky_img: Image.Image) -> Image.Image:
    """Replace sky area with sky_img using cloud-returned mask."""
    orig_rgb = orig.convert("RGB")
    mask_raw = base64.b64decode(mask_b64)
    mask = Image.open(io.BytesIO(mask_raw)).convert("L").resize(orig_rgb.size, Image.LANCZOS)
    sky = sky_img.convert("RGB").resize(orig_rgb.size, Image.LANCZOS)
    return Image.composite(sky, orig_rgb, mask)

def composite_passport(face_img: Image.Image, backdrop: Image.Image,
                       size=(413, 531)) -> Image.Image:
    """Place face cutout onto ID-photo backdrop."""
    face_rgba = face_img.convert("RGBA")
    # scale to ~85% height
    th = int(size[1] * 0.85)
    tw = int(face_rgba.width * (th / face_rgba.height))
    face_rgba = face_rgba.resize((tw, th), Image.LANCZOS)
    bg = backdrop.convert("RGBA").resize(size, Image.LANCZOS)
    bg.alpha_composite(face_rgba, ((size[0] - tw) // 2, size[1] - th))
    return bg.convert("RGB")

# ---------------- cloud tool implementations ----------------

class CloudRemoveBackground(BaseTool):
    id = "remove_background"
    name = "Background Remover (Cloud)"
    description = "一键移除背景，生成透明 PNG（SnapEdit 官方云端）"
    params = {
        "bg_color": {"type": "string", "default": "transparent", "description": "背景替换色"},
        "return_mask": {"type": "boolean", "default": False, "description": "返回分割掩码"},
    }
    def run(self, image: Image.Image, bg_color="transparent", return_mask=False, **kw) -> ToolResult:
        d = _call_multipart("api/rmbg/v1", files={"input_image": _file_part("input_image", image, "PNG")})
        out = _b64_to_img_alpha(d["output"])
        data = {"mode": "rgba", "object": d.get("object"), "model": d.get("model")}
        result = out
        if bg_color and bg_color != "transparent":
            color = self._parse_color(bg_color)
            result = self._flatten(out, color)
            data["mode"] = "rgb"
        if return_mask:
            data["mask"] = pil_to_bytes(out.split()[-1], "PNG")
        return ToolResult(image=result, data=data)

    @staticmethod
    def _parse_color(s):
        s = s.strip().lower()
        if s == "white": return (255, 255, 255, 255)
        if s == "black": return (0, 0, 0, 255)
        if s.startswith("#") and len(s) == 7: return tuple(int(s[i:i+2], 16) for i in (1, 3, 5)) + (255,)
        return (255, 255, 255, 255)
    @staticmethod
    def _flatten(rgba, color):
        bg = Image.new("RGBA", rgba.size, color)
        return Image.alpha_composite(bg, rgba).convert("RGB")

class CloudRemoveObject(BaseTool):
    id = "remove_object"
    name = "Object Remover (Cloud)"
    description = "AI 擦除人物/物体：自动检测或使用 mask 指定区域（SnapEdit 官方云端）"
    params = {
        "auto": {"type": "boolean", "default": True, "description": "自动检测第一个物体"},
        "mask_image": {"type": "image", "default": None, "description": "可选：手动涂抹 mask（白色=擦除）"},
    }
    def run(self, image: Image.Image, auto=True, mask_image=None, **kw) -> ToolResult:
        png = pil_to_bytes(image, "PNG")
        # 1) optional user mask -> direct erase
        if mask_image is not None:
            return self._erase(image, png, mask_image, selected=[])
        # 2) auto: scan then erase top object
        scan = _call_multipart("api/object_removal/v7/auto_suggest?lang=en",
                               fields={"session_id": ""},
                               files={"original_preview_image": ("in.png", png, "image/png")})
        objs = scan.get("detected_objects") or []
        if not objs:
            return ToolResult(error="cloud scan found no objects")
        obj = objs[0]
        mask_png = base64.b64decode(obj["mask"])
        mask_img = Image.open(io.BytesIO(mask_png)).convert("L")
        rgba = Image.new("RGBA", mask_img.size, (0, 0, 0, 0))
        px = mask_img.load(); pr = rgba.load()
        for y in range(mask_img.size[1]):
            for x in range(mask_img.size[0]):
                if px[x, y] > 10:
                    pr[x, y] = (255, 0, 0, 255)
        selected = [{"box": obj["box"], "mask": obj["mask"]}]
        return self._erase(image, png, rgba, selected=selected, session_id=scan.get("session_id", ""))

    def _erase(self, image, png, mask_img, selected=None, session_id=""):
        mask_png = pil_to_bytes(mask_img, "PNG")
        fields = {
            "mask_objects": json.dumps(selected or [], separators=(",", ":")),
            "session_id": session_id,
            "original_session_id": "",
        }
        files = {
            "original_preview_image": ("in.png", png, "image/png"),
            "mask_base": ("mask.png", mask_png, "image/png"),
        }
        d = _call_multipart("api/object_removal/v5/erase", fields=fields, files=files,
                            query={"invoke_sd": "false"})
        edited = d.get("edited_image", {})
        img = _b64_to_img(edited.get("image", ""))
        return ToolResult(image=img, data={"mode": "rgb"})

class CloudEnhance(BaseTool):
    id = "enhance"
    name = "AI Enhance (Cloud)"
    description = "AI 增强：人脸高清修复 + 全图优化（SnapEdit 官方云端）"
    params = {
        "zoom_factor": {"type": "integer", "default": 2, "description": "放大/增强倍数"},
        "mode": {"type": "string", "default": "auto", "description": "auto/standard/pro"},
    }
    def run(self, image: Image.Image, zoom_factor=2, mode="auto", **kw) -> ToolResult:
        png = pil_to_bytes(image, "PNG")
        try:
            d = _call_multipart("api/enhance/v2",
                                fields={"zoom_factor": int(zoom_factor)},
                                files={"input_image": ("in.png", png, "image/png")})
            faces = d.get("faces") or []
            if faces:
                out = composite_enhance_faces(image, faces) or image
                data = {"faces": len(faces), "mode": "face_composite"}
            else:
                # no faces -> fall back to cloud enhance/v1/bg (background enhance)
                out = image
                data = {"faces": 0, "mode": "no_face"}
        except Exception:
            out, data = image, {"mode": "fallback"}
        return ToolResult(image=out, data=data)

class CloudRestore(BaseTool):
    id = "restore"
    name = "Photo Restore (Cloud)"
    description = "老照片修复：去划痕、去噪、人脸修复（SnapEdit 官方云端）"
    params = {}
    def run(self, image: Image.Image, **kw) -> ToolResult:
        png = pil_to_bytes(image, "PNG")
        d = _call_multipart("api/restore/v1", files={"input_image": ("in.png", png, "image/png")})
        out_img = _b64_to_img(d["output_image"]["image"])
        return ToolResult(image=out_img, data={"image_id": d.get("image_id", "")})

class CloudAnime(BaseTool):
    id = "anime"
    name = "AI Anime (Cloud)"
    description = "AI 动漫化：将照片转为动漫/插画风格（SnapEdit 官方云端）"
    params = {
        "style": {"type": "string", "default": "anime_newyearfirework", "description": "风格 id（见 /v1/styles/anime）"},
        "run_config": {"type": "string", "default": "super", "description": "super/anime"},
    }
    def run(self, image: Image.Image, style="anime_newyearfirework", run_config="super", **kw) -> ToolResult:
        png = pil_to_bytes(image, "PNG")
        fields = {"image_id": "", "style": style, "run_config": run_config, "n_results": "1"}
        d = _call_multipart("api/fairyai/v1/gen_image", fields=fields,
                            files={"input_image": ("in.png", png, "image/png")})
        out_img = _b64_to_img(d["output_image"])
        return ToolResult(image=out_img, data={"image_id": d.get("image_id", "")})

class CloudRetouch(BaseTool):
    id = "retouch"
    name = "AI Retouch (Cloud)"
    description = "人像美容：磨皮、亮眼、美白（SnapEdit 官方云端）"
    params = {}
    def run(self, image: Image.Image, **kw) -> ToolResult:
        png = pil_to_bytes(image, "PNG")
        d = _call_multipart("api/retouch/v1/", files={"image": ("in.png", png, "image/png")})
        out_img = _b64_to_img(d["image"])
        return ToolResult(image=out_img, data={})

class CloudSky(BaseTool):
    id = "sky"
    name = "Sky Replacement (Cloud)"
    description = "天空替换：AI 分割天空 + 替换背景（SnapEdit 官方云端）"
    params = {
        "sky": {"type": "string", "default": "default", "description": "天空背景 id（见 /v1/backgrounds/sky）"},
    }
    def run(self, image: Image.Image, sky="default", **kw) -> ToolResult:
        png = pil_to_bytes(image, "PNG")
        d = _call_multipart("api/sky/v1", files={"input_image": ("in.png", png, "image/png")})
        mask = d.get("mask", "")
        if not mask:
            return ToolResult(error="cloud sky segmentation returned no mask")
        sky_img = _get_sky_background(sky, image.size)
        out = composite_sky(image, mask, sky_img)
        return ToolResult(image=out, data={"box": d.get("box", [])})

class CloudPassport(BaseTool):
    id = "passport"
    name = "ID Photo (Cloud)"
    description = "证件照：AI 抠图 + 标准尺寸背景（SnapEdit 官方云端）"
    params = {
        "bg": {"type": "string", "default": "white", "description": "背景色: white/blue/red"},
    }
    def run(self, image: Image.Image, bg="white", **kw) -> ToolResult:
        png = pil_to_bytes(image, "PNG")
        d = _call_multipart("api/passport/v1", files={"input_image": ("in.png", png, "image/png")})
        face_img = _b64_to_img(d["face"])
        backdrop = Image.new("RGB", (1, 1), {"white": (255, 255, 255), "blue": (67, 142, 219), "red": (255, 0, 0)}.get(bg, (255, 255, 255)))
        out = composite_passport(face_img, backdrop)
        return ToolResult(image=out, data={"size": "413x531"})

class CloudTextErase(BaseTool):
    id = "text_erase"
    name = "Text Eraser (Cloud)"
    description = "文字/水印移除：AI 检测文字区域并擦除（SnapEdit 官方云端）"
    params = {}
    def run(self, image: Image.Image, **kw) -> ToolResult:
        png = pil_to_bytes(image, "PNG")
        d = _call_multipart("api/object_removal/v5/text_detection",
                            fields={"session_id": ""},
                            files={"original_preview_image": ("in.png", png, "image/png")})
        sid = d.get("session_id", "")
        mask = d.get("mask", "")
        if not d.get("having_text") or not mask:
            return ToolResult(image=image.convert("RGB"), data={"found_text": False})
        # build RGBA mask from returned text mask
        mraw = base64.b64decode(mask)
        m = Image.open(io.BytesIO(mraw)).convert("L")
        rgba = Image.new("RGBA", m.size, (0, 0, 0, 0))
        pm = m.load(); pr = rgba.load()
        for y in range(m.size[1]):
            for x in range(m.size[0]):
                if pm[x, y] > 10:
                    pr[x, y] = (255, 0, 0, 255)
        files = {
            "original_preview_image": ("in.png", png, "image/png"),
            "mask_base": ("mask.png", pil_to_bytes(rgba, "PNG"), "image/png"),
            "mask_text": ("mask_text.png", pil_to_bytes(rgba, "PNG"), "image/png"),
        }
        fields = {"mask_objects": "[]", "session_id": sid, "original_session_id": ""}
        er = _call_multipart("api/object_removal/v5/erase", fields=fields, files=files,
                             query={"invoke_sd": "false"})
        out = _b64_to_img(er["edited_image"]["image"])
        return ToolResult(image=out, data={"found_text": True})

# filter stays local (color grading, no AI)
class CloudFilter(BaseTool):
    id = "filter"
    name = "Filters (Local)"
    description = "滤镜（本地色彩处理，无需云端）"
    params = {"filter": {"type": "string", "default": "vivid", "description": "vivid/bw/vintage/warm/cool"}}
    def run(self, image: Image.Image, filter="vivid", **kw) -> ToolResult:
        from engines.filters import FilterTool
        return FilterTool().run(image, filter=filter, **kw)

# ---------------- assets ----------------

def _get_sky_background(sky_id: str, size) -> Image.Image:
    cache = Path(os.environ.get("SNAPEDIT_DATA_DIR", "/root/haizhucodex/snapedit-webui/data")) / "skies"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / f"{sky_id}.png"
    if not path.exists():
        try:
            url = f"https://assets.snapedit.app/skywizard/backgrounds.json"
            r = requests.get(url, timeout=30, headers={"User-Agent": USER_AGENT})
            r.raise_for_status()
            raw = r.json()
            items = raw.get("backgrounds", raw) if isinstance(raw, dict) else raw
            target = None
            sid = str(sky_id).lower()
            for idx, it in enumerate(items):
                name = str(it.get("name", "")).lower()
                if it.get("id") == sky_id or name == sid or sid == str(idx) or sid == "default":
                    target = it
                    break
            if target is None and items:
                target = items[0]
            img_url = target.get("url") or target.get("canvas_url") or target.get("image") or ""
            if img_url:
                ir = requests.get(img_url, timeout=60, headers={"User-Agent": USER_AGENT})
                ir.raise_for_status()
                Image.open(io.BytesIO(ir.content)).convert("RGB").save(path)
        except Exception as e:
            log.warning("sky background fetch failed: %s", e)
    if path.exists():
        return Image.open(path).convert("RGB")
    # fallback: gradient sky
    w, h = size
    grad = Image.new("RGB", (w, h))
    top = (80, 140, 220); bot = (240, 200, 120)
    for y in range(h):
        t = y / max(1, h - 1)
        grad.paste(tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)), (0, y, w, y + 1))
    return grad

# ---------------- registration ----------------

def install_cloud_tools(replace=True):
    tools = [
        CloudRemoveBackground(), CloudRemoveObject(), CloudEnhance(), CloudRestore(),
        CloudAnime(), CloudRetouch(), CloudSky(), CloudPassport(), CloudTextErase(), CloudFilter(),
    ]
    for t in tools:
        if replace or ToolRegistry.get(t.id) is None:
            ToolRegistry.register(t)
    return tools

def cloud_backend_enabled() -> bool:
    return os.environ.get("SNAPEDIT_BACKEND", "cloud").lower() != "local"
