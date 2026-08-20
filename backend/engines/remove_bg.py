"""Background removal tool (rmbg) - rembg U2Net on CPU."""
from __future__ import annotations
from PIL import Image
from .base import BaseTool, ToolResult, ToolRegistry
import logging
log = logging.getLogger("snapedit.remove_bg")

class RemoveBackgroundTool(BaseTool):
    id = "remove_background"
    name = "Background Remover"
    description = "一键移除背景，生成透明 PNG（SnapEdit 背景移除）"
    params = {
        "alpha_matting": {"type": "boolean", "default": False, "description": "使用 alpha matting 精细边缘"},
        "post_process_mask": {"type": "boolean", "default": False, "description": "后处理优化掩码"},
        "bg_color": {"type": "string", "default": "transparent", "description": "背景替换色: transparent/white/black/color hex"},
        "return_mask": {"type": "boolean", "default": False, "description": "同时返回分割掩码"},
    }

    def __init__(self):
        self._session = None

    def _get_session(self):
        if self._session is None:
            from rembg import new_session
            log.info("loading u2net session...")
            self._session = new_session("u2net")
        return self._session

    def run(self, image: Image.Image, alpha_matting=False, post_process_mask=False,
            bg_color="transparent", return_mask=False, **kw) -> ToolResult:
        from rembg import remove
        session = self._get_session()
        img_bytes = self._pil_to_bytes_png(image)
        out = remove(img_bytes, session=session, alpha_matting=alpha_matting,
                     post_process_mask=post_process_mask)
        import io
        result = Image.open(io.BytesIO(out)).convert("RGBA")

        data = {}
        if bg_color and bg_color != "transparent":
            color = self._parse_color(bg_color)
            result = self._flatten(result, color)

        if return_mask:
            mask = result.split()[-1]
            data["mask"] = self._pil_to_bytes_png(mask)

        data["mode"] = "rgba" if result.mode == "RGBA" else result.mode
        return ToolResult(image=result, data=data)

    @staticmethod
    def _pil_to_bytes_png(img: Image.Image) -> bytes:
        import io
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    @staticmethod
    def _parse_color(s: str):
        s = s.strip().lower()
        if s == "white": return (255, 255, 255, 255)
        if s == "black": return (0, 0, 0, 255)
        if s.startswith("#") and len(s) == 7:
            return tuple(int(s[i:i+2], 16) for i in (1, 3, 5)) + (255,)
        if s.startswith("#") and len(s) == 9:
            return tuple(int(s[i:i+2], 16) for i in (1, 3, 5, 7))
        return (255, 255, 255, 255)

    @staticmethod
    def _flatten(rgba: Image.Image, color) -> Image.Image:
        bg = Image.new("RGBA", rgba.size, color)
        return Image.alpha_composite(bg, rgba)

ToolRegistry.register(RemoveBackgroundTool())
