"""AI Enhance - multi-strength enhancement: denoise, sharpen, contrast, deblur.
CPU-friendly equivalents of SnapEdit enhance/v2 (upscale + enhance)."""
from __future__ import annotations
from PIL import Image, ImageEnhance, ImageFilter
import numpy as np, cv2
from .base import BaseTool, ToolResult, ToolRegistry
import logging
log = logging.getLogger("snapedit.enhance")

class EnhanceTool(BaseTool):
    id = "enhance"
    name = "AI Enhance"
    description = "AI 增强：去噪、锐化、对比度、色彩增强、超分辨率（SnapEdit AI Enhance）"
    params = {
        "strength": {"type": "integer", "default": 3, "description": "增强强度 1-5"},
        "upscale": {"type": "integer", "default": 1, "description": "超分倍数 1-4 (2x=双倍)"},
        "denoise": {"type": "boolean", "default": True, "description": "去噪"},
        "deblur": {"type": "boolean", "default": True, "description": "去模糊"},
        "enhance_face": {"type": "boolean", "default": False, "description": "人脸增强"},
        "mode": {"type": "string", "default": "auto", "description": "auto/standard/pro"},
    }

    def run(self, image: Image.Image, strength=3, upscale=1, denoise=True,
            deblur=True, enhance_face=False, mode="auto", **kw) -> ToolResult:
        img = image.convert("RGB")
        s = max(1, min(5, int(strength)))

        # --- upscale first (nearest + unsharp) ---
        if upscale and upscale > 1:
            new_size = (img.width * int(upscale), img.height * int(upscale))
            img = img.resize(new_size, Image.LANCZOS)
            img = img.filter(ImageFilter.UnsharpMask(radius=2, percent=80, threshold=2))

        arr = np.array(img)
        rgb = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        # --- denoise ---
        if denoise:
            h_strength = 3 + s
            rgb = cv2.fastNlMeansDenoisingColored(rgb, None, h_strength, h_strength, 7, 21)

        # --- deblur via unsharp / deconvolution-ish sharpening ---
        if deblur:
            # mild unsharp masking (safe)
            blur = cv2.GaussianBlur(rgb, (0, 0), sigmaX=1.0 + s * 0.25)
            sharp = cv2.addWeighted(rgb, 1.0 + 0.15 * s, blur, -0.15 * s, 0)
            rgb = sharp

        # --- contrast & saturation ---
        pil = Image.fromarray(cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB))
        pil = ImageEnhance.Contrast(pil).enhance(1.0 + 0.08 * s)
        pil = ImageEnhance.Color(pil).enhance(1.0 + 0.06 * s)
        pil = ImageEnhance.Brightness(pil).enhance(1.0 + 0.03 * s)

        # --- extra pro mode: stronger clarity ---
        if mode == "pro" or s >= 4:
            pil = pil.filter(ImageFilter.UnsharpMask(radius=3, percent=120, threshold=2))
            pil = ImageEnhance.Sharpness(pil).enhance(1.15)

        if enhance_face:
            pil = self._face_soft(pil)

        data = {"strength": s, "upscale": int(upscale), "mode": mode}
        return ToolResult(image=pil, data=data)

    @staticmethod
    def _face_soft(img: Image.Image) -> Image.Image:
        # gentle skin smoothing: low-pass blend
        blurred = img.filter(ImageFilter.GaussianBlur(radius=2))
        return Image.blend(img, blurred, 0.15)

ToolRegistry.register(EnhanceTool())
