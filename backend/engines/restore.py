"""Old photo restore - scratch removal, fade correction, color boost.
CPU-friendly equivalent of SnapEdit restore/v1 (老照片修复)."""
from __future__ import annotations
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np, cv2
from .base import BaseTool, ToolResult, ToolRegistry
import logging
log = logging.getLogger("snapedit.restore")

class RestoreTool(BaseTool):
    id = "restore"
    name = "Old Photo Restore"
    description = "老照片修复：去划痕、去噪、褪色校正、对比度恢复（SnapEdit Restore）"
    params = {
        "scratch_removal": {"type": "boolean", "default": True, "description": "划痕移除"},
        "color_restore": {"type": "boolean", "default": True, "description": "色彩恢复"},
        "face_enhance": {"type": "boolean", "default": False, "description": "人脸增强"},
        "strength": {"type": "integer", "default": 3, "description": "强度 1-5"},
    }

    def run(self, image: Image.Image, scratch_removal=True, color_restore=True,
            face_enhance=False, strength=3, **kw) -> ToolResult:
        img = image.convert("RGB")
        s = max(1, min(5, int(strength)))
        arr = np.array(img)
        rgb = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        if scratch_removal:
            # median filter removes thin scratches
            rgb = cv2.medianBlur(rgb, 3)
            # stronger denoise
            rgb = cv2.fastNlMeansDenoisingColored(rgb, None, 5, 5, 7, 21)

        # de-fade: normalize histogram
        if color_restore:
            lab = cv2.cvtColor(rgb, cv2.COLOR_BGR2LAB)
            l, a, b = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=1.5 + 0.2 * s, tileGridSize=(8, 8))
            l = clahe.apply(l)
            lab = cv2.merge((l, a, b))
            rgb = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
            # saturation & contrast
            pil = Image.fromarray(cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB))
            pil = ImageEnhance.Color(pil).enhance(1.0 + 0.12 * s)
            pil = ImageEnhance.Contrast(pil).enhance(1.0 + 0.10 * s)
            rgb = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)

        # subtle sharpening
        blur = cv2.GaussianBlur(rgb, (0, 0), 0.8)
        rgb = cv2.addWeighted(rgb, 1.15, blur, -0.15, 0)

        pil = Image.fromarray(cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB))

        if face_enhance:
            blurred = pil.filter(ImageFilter.GaussianBlur(radius=2))
            pil = Image.blend(pil, blurred, 0.12)

        data = {"strength": s, "scratch_removal": scratch_removal, "color_restore": color_restore}
        return ToolResult(image=pil, data=data)

ToolRegistry.register(RestoreTool())
