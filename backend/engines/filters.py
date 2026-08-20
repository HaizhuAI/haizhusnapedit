"""Photo filters (LUT-style presets) + text erase.
SnapEdit filter presets port."""
from __future__ import annotations
from PIL import Image, ImageEnhance, ImageOps
import numpy as np, cv2
from .base import BaseTool, ToolResult, ToolRegistry
import logging
log = logging.getLogger("snapedit.filters")

FILTER_PRESETS = {
    "original": {},
    "vivid": {"color": 1.35, "contrast": 1.1, "brightness": 1.02},
    "bw": {"bw": True},
    "warm": {"color": 1.1, "contrast": 1.05, "temperature": 0.25},
    "cool": {"color": 1.1, "contrast": 1.05, "temperature": -0.25},
    "vintage": {"color": 0.85, "contrast": 0.9, "brightness": 1.05, "sepia": 0.4},
    "drama": {"color": 1.2, "contrast": 1.3, "brightness": 0.95},
    "fade": {"color": 0.75, "contrast": 0.8, "brightness": 1.1},
    "cinema": {"color": 1.05, "contrast": 1.25, "temperature": -0.15, "fade": 0.15},
    "noir": {"bw": True, "contrast": 1.3},
    "golden": {"color": 1.2, "contrast": 1.1, "temperature": 0.4},
}

class FilterTool(BaseTool):
    id = "filter"
    name = "Photo Filters"
    description = "滤镜预设（SnapEdit Filters）：vivid/bw/warm/cool/vintage/drama/fade/cinema/noir/golden"
    params = {
        "filter": {"type": "string", "default": "vivid", "description": "滤镜名"},
    }

    def run(self, image: Image.Image, filter="vivid", **kw) -> ToolResult:
        img = image.convert("RGB")
        cfg = FILTER_PRESETS.get(filter, FILTER_PRESETS["original"])

        if cfg.get("bw"):
            img = ImageOps.grayscale(img).convert("RGB")

        if cfg.get("color"):
            img = ImageEnhance.Color(img).enhance(cfg["color"])
        if cfg.get("contrast"):
            img = ImageEnhance.Contrast(img).enhance(cfg["contrast"])
        if cfg.get("brightness"):
            img = ImageEnhance.Brightness(img).enhance(cfg["brightness"])

        temp = cfg.get("temperature", 0.0)
        if temp:
            arr = np.array(img).astype(np.float32)
            arr[..., 0] = np.clip(arr[..., 0] + temp * 60, 0, 255)   # red
            arr[..., 2] = np.clip(arr[..., 2] - temp * 60, 0, 255)   # blue
            img = Image.fromarray(arr.astype(np.uint8))

        if cfg.get("sepia"):
            arr = np.array(img).astype(np.float32)
            r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
            nr = 0.393*r + 0.769*g + 0.189*b
            ng = 0.349*r + 0.686*g + 0.168*b
            nb = 0.272*r + 0.534*g + 0.131*b
            sep = np.stack([nr, ng, nb], axis=-1)
            arr = arr * (1 - cfg["sepia"]) + sep * cfg["sepia"]
            img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

        if cfg.get("fade"):
            arr = np.array(img).astype(np.float32)
            arr = arr * (1 - cfg["fade"]) + 128 * cfg["fade"]
            img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

        data = {"filter": filter}
        return ToolResult(image=img, data=data)


class TextEraseTool(BaseTool):
    id = "text_erase"
    name = "Text / Object Erase"
    description = "文字/杂物擦除：画笔区域内容移除（SnapEdit Super Erase 手动模式）"
    params = {
        "radius": {"type": "integer", "default": 6, "description": "inpaint 半径"},
    }

    def run(self, image: Image.Image, mask_image: Image.Image = None, radius=6, **kw) -> ToolResult:
        img = np.array(image.convert("RGB"))
        h, w = img.shape[:2]
        if mask_image is None:
            # no mask -> return copy (UI must supply mask)
            return ToolResult(image=image, data={"note": "需要掩码", "erased": 0.0})
        mask = np.array(mask_image.convert("L").resize((w, h))).astype(np.uint8)
        mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)[1]
        result = cv2.inpaint(img, mask, max(1, int(radius)), cv2.INPAINT_TELEA)
        data = {"erased_region_percent": round(float(mask.mean() / 255.0 * 100), 2)}
        return ToolResult(image=Image.fromarray(result), data=data)

ToolRegistry.register(FilterTool())
ToolRegistry.register(TextEraseTool())
