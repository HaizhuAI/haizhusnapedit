"""Sky replacement (Sky Wizard) - detect sky region, replace with preset.
CPU equivalent of SnapEdit sky/v1."""
from __future__ import annotations
from PIL import Image
import numpy as np, cv2
from .base import BaseTool, ToolResult, ToolRegistry
import logging
log = logging.getLogger("snapedit.sky")

# built-in sky presets (gradient-based, no external assets)
SKY_PRESETS = {
    "sunset": (255, 94, 58, 255, 200, 120),      # orange->yellow
    "blue": (30, 80, 180, 160, 200, 255),        # deep->light blue
    "pink": (220, 120, 190, 255, 210, 230),      # pink->cream
    "purple": (80, 40, 130, 190, 130, 230),      # violet->light purple
    "night": (10, 15, 60, 60, 70, 130),          # dark blue
    "gold": (240, 190, 80, 255, 240, 200),       # golden
}

class SkyTool(BaseTool):
    id = "sky"
    name = "Sky Replacement"
    description = "天空替换（SnapEdit Sky Wizard）：自动分割天空并替换为预设天空"
    params = {
        "sky": {"type": "string", "default": "sunset", "description": "天空预设: sunset/blue/pink/purple/night/gold"},
        "blend": {"type": "integer", "default": 30, "description": "融合强度 % 10-60"},
    }

    def run(self, image: Image.Image, sky="sunset", blend=30, **kw) -> ToolResult:
        img = image.convert("RGB")
        arr = np.array(img).astype(np.float32)
        h, w = arr.shape[:2]

        # simple sky mask: bright + blue-ish in upper region
        b, g, r = arr[..., 0], arr[..., 1], arr[..., 2]
        # blue-dominance score
        blue_score = np.clip((b - r) / 255.0, 0, 1) + np.clip((b - g) / 255.0, 0, 1)
        bright = (r + g + b) / (3 * 255.0)
        sky_score = blue_score * 0.7 + bright * 0.3
        # weight upper half more
        y = np.linspace(0, 1, h)[:, None]
        sky_score = sky_score * (1 - y * 0.3)  # top heavier

        # threshold to binary, then feather
        mask = np.clip((sky_score - 0.35) * 8, 0, 1).astype(np.float32)

        # build gradient sky
        if sky not in SKY_PRESETS:
            sky = "sunset"
        c1 = np.array(SKY_PRESETS[sky][:3], dtype=np.float32)
        c2 = np.array(SKY_PRESETS[sky][3:], dtype=np.float32)
        t = np.linspace(0, 1, h)[:, None, None]
        sky_img = (c1[None, None, :] * (1 - t) + c2[None, None, :] * t).repeat(w, axis=1)

        a = float(np.clip(blend, 10, 60)) / 100.0
        mask = mask * a
        out = arr * (1 - mask[..., None]) + sky_img * mask[..., None]
        out = np.clip(out, 0, 255).astype(np.uint8)

        result = Image.fromarray(out)
        data = {"sky": sky, "mask_percent": round(float(mask.mean() * 100), 2)}
        return ToolResult(image=result, data=data)

ToolRegistry.register(SkyTool())
