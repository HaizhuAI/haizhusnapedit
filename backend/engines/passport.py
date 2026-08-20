"""Passport maker (证件照) - background color, size crop, head adjust.
CPU equivalent of SnapEdit passport/v1."""
from __future__ import annotations
from PIL import Image
import numpy as np, cv2
from .base import BaseTool, ToolResult, ToolRegistry
import logging
log = logging.getLogger("snapedit.passport")

class PassportTool(BaseTool):
    id = "passport"
    name = "Passport Maker"
    description = "证件照制作：一键换背景色（红/白/蓝）、标准尺寸裁切（SnapEdit Passport）"
    params = {
        "bg_color": {"type": "string", "default": "blue", "description": "背景色: blue/white/red"},
        "size": {"type": "string", "default": "1inch", "description": "尺寸: 1inch/2inch/35x45"},
        "dpi": {"type": "integer", "default": 300, "description": "DPI"},
    }

    SIZES = {"1inch": (295, 413), "2inch": (413, 579), "35x45": (413, 531)}
    COLORS = {"blue": (67, 142, 219), "white": (255, 255, 255), "red": (222, 50, 50)}

    def __init__(self):
        self._bg_session = None

    def _get_session(self):
        if self._bg_session is None:
            from rembg import new_session
            self._bg_session = new_session("u2net")
        return self._bg_session

    def run(self, image: Image.Image, bg_color="blue", size="1inch", dpi=300, **kw) -> ToolResult:
        from rembg import remove
        import io
        buf = io.BytesIO(); image.save(buf, format="PNG")
        out = remove(buf.getvalue(), session=self._get_session(), alpha_matting=False)
        person = Image.open(io.BytesIO(out)).convert("RGBA")

        color = self.COLORS.get(bg_color, self.COLORS["blue"])
        bg = Image.new("RGBA", person.size, color + (255,))
        composed = Image.alpha_composite(bg, person)

        # canvas to target size (fit inside)
        tw, th = self.SIZES.get(size, self.SIZES["1inch"])
        canvas = Image.new("RGBA", (tw, th), color + (255,))
        # scale person to fill ~ 80% height
        scale = min((th * 0.85) / composed.height, (tw * 0.8) / composed.width)
        nh = int(composed.height * scale)
        nw = int(composed.width * scale)
        composed = composed.resize((nw, nh), Image.LANCZOS)
        canvas.paste(composed, ((tw - nw) // 2, int((th - nh) * 0.45)), composed)

        data = {"size": size, "bg_color": bg_color, "dpi": int(dpi),
                "pixels": f"{canvas.width}x{canvas.height}"}
        return ToolResult(image=canvas.convert("RGB"), data=data)

ToolRegistry.register(PassportTool())
