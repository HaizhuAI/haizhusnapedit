"""Anime / Fairy AI - cartoonization filters (multiple styles).
CPU-friendly AnimeGAN-ish effect using edge-preserving stylization."""
from __future__ import annotations
from PIL import Image
import numpy as np, cv2
from .base import BaseTool, ToolResult, ToolRegistry
import logging
log = logging.getLogger("snapedit.anime")

class AnimeTool(BaseTool):
    id = "anime"
    name = "Anime / Fairy AI"
    description = "动漫化：照片转动漫风格（SnapEdit Fairy AI）。支持多种风格"
    params = {
        "style": {"type": "string", "default": "anime", "description": "anime/ghibli/cyberpunk/watercolor/comic"},
        "strength": {"type": "integer", "default": 5, "description": "风格强度 1-10"},
    }

    def run(self, image: Image.Image, style="anime", strength=5, **kw) -> ToolResult:
        img = image.convert("RGB")
        arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        s = max(1, min(10, int(strength)))

        # downscale for edge extraction
        h, w = arr.shape[:2]
        small = cv2.resize(arr, (max(32, w // 4), max(32, h // 4)), interpolation=cv2.INTER_AREA)

        # bilateral filter = smooth regions
        smooth = cv2.bilateralFilter(arr, 9, 75 + 5*s, 75 + 5*s)
        # quantize colors
        Z = smooth.reshape((-1, 3)).astype(np.float32)
        K = 12 if s < 6 else 8
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
        _, labels, centers = cv2.kmeans(Z, K, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
        centers = np.uint8(centers)
        quantized = centers[labels.flatten()].reshape(smooth.shape)

        # edges
        gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
        gray = cv2.medianBlur(gray, 5)
        edges = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_MEAN_C,
                                      cv2.THRESH_BINARY, 9, 9)
        edges = cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR)
        edge_strength = 0.35 + 0.05 * (10 - s)  # stronger style = softer edges

        if style in ("ghibli", "watercolor"):
            edge_strength = 0.15
        elif style in ("cyberpunk", "comic"):
            edge_strength = 0.6

        out = cv2.addWeighted(quantized, 1 - edge_strength, edges, edge_strength, 0)

        if style == "cyberpunk":
            # pink/cyan tint
            hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[..., 0] = (hsv[..., 0] + 30) % 180
            hsv[..., 1] = np.clip(hsv[..., 1] * 1.2, 0, 255)
            out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        elif style == "watercolor":
            out = cv2.bilateralFilter(out, 7, 60, 60)
        elif style == "ghibli":
            out = cv2.bilateralFilter(out, 9, 50, 50)
            hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
            hsv[..., 1] = np.clip(hsv[..., 1] * 0.9, 0, 255)
            out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
        elif style == "comic":
            out = cv2.addWeighted(quantized, 0.5, edges, 0.5, 0)
            out = cv2.cvtColor(out, cv2.COLOR_BGR2GRAY)
            out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)

        result = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
        data = {"style": style, "strength": s}
        return ToolResult(image=result, data=data)

ToolRegistry.register(AnimeTool())
