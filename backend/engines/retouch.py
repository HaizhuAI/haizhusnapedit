"""Retouch / skin beauty / portrait enhance.
SnapEdit retouch/v1 + skin_beauty/v1 CPU equivalent."""
from __future__ import annotations
from PIL import Image, ImageFilter
import numpy as np, cv2
from .base import BaseTool, ToolResult, ToolRegistry
import logging
log = logging.getLogger("snapedit.retouch")

class RetouchTool(BaseTool):
    id = "retouch"
    name = "Portrait Retouch"
    description = "人像美容：皮肤磨皮、美白、祛痘、红眼修复（SnapEdit Retouch / Skin Beauty）"
    params = {
        "smooth": {"type": "integer", "default": 5, "description": "皮肤平滑 1-10"},
        "whiten": {"type": "integer", "default": 3, "description": "美白 1-10"},
        "remove_blemish": {"type": "boolean", "default": True, "description": "祛痘/瑕疵"},
        "red_eye": {"type": "boolean", "default": False, "description": "红眼修复"},
        "face_contour": {"type": "boolean", "default": False, "description": "脸型微调"},
    }

    def run(self, image: Image.Image, smooth=5, whiten=3, remove_blemish=True,
            red_eye=False, face_contour=False, **kw) -> ToolResult:
        img = image.convert("RGB")
        arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        sm = max(0, min(10, int(smooth)))
        wh = max(0, min(10, int(whiten)))

        # frequency-based skin smoothing (guided-like via bilateral pyramid)
        base = arr.copy()
        detail = arr.copy()
        for _ in range(2):
            base = cv2.bilateralFilter(base, 9, 40 + 8*sm, 40 + 8*sm)
        detail = cv2.addWeighted(arr, 1.0, base, 0.0, 0) - base
        # blend back some detail
        out = cv2.addWeighted(base, 1.0, detail, 0.6, 0)

        # skin mask (YCbCr): keep edges but smooth skin tones
        ycrcb = cv2.cvtColor(arr, cv2.COLOR_BGR2YCrCb)
        skin = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
        skin = cv2.GaussianBlur(skin.astype(np.float32), (0, 0), 15).astype(np.uint8)
        skin = cv2.merge([skin, skin, skin]) / 255.0
        out = (base.astype(np.float32) * skin + arr.astype(np.float32) * (1 - skin)).astype(np.uint8)

        if remove_blemish:
            # median filter only in skin region (small spots)
            med = cv2.medianBlur(out, 5)
            out = (med.astype(np.float32) * skin * 0.5 + out.astype(np.float32) * (1 - skin*0.5)).astype(np.uint8)

        # whiten: raise L channel
        if wh > 0:
            lab = cv2.cvtColor(out, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            l = np.clip(l.astype(np.float32) + wh * 2.2, 0, 255).astype(np.uint8)
            lab = cv2.merge((l, a, b))
            out = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

        if red_eye:
            out = self._fix_red_eye(out)

        result = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
        data = {"smooth": sm, "whiten": wh}
        return ToolResult(image=result, data=data)

    @staticmethod
    def _fix_red_eye(bgr):
        # simple red-channel suppression in eye regions via red mask
        b, g, r = cv2.split(bgr.astype(np.float32))
        red_mask = ((r > g * 1.6) & (r > b * 1.6)).astype(np.float32)
        red_mask = cv2.GaussianBlur(red_mask, (0, 0), 5)
        r = r * (1 - red_mask) + (g + b) / 2 * red_mask
        return cv2.merge((b, g, r)).astype(np.uint8)

ToolRegistry.register(RetouchTool())
