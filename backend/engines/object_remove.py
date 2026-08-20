"""Object removal (super erase) - detection + inpainting.
Mirrors SnapEdit object_removal flow: detect objects -> mask -> inpaint.
CPU-friendly: uses rembg mask for salient object or OpenCV inpaint for brush erase."""
from __future__ import annotations
from PIL import Image
import numpy as np, cv2
from .base import BaseTool, ToolResult, ToolRegistry
import logging
log = logging.getLogger("snapedit.object_remove")

class ObjectRemoveTool(BaseTool):
    id = "remove_object"
    name = "Super Erase / Object Remover"
    description = "一键移除人物和物品（SnapEdit 超级擦除）。支持自动检测主体或手动掩码"
    params = {
        "mode": {"type": "string", "default": "auto", "description": "auto=自动检测主体; mask=使用上传掩码; brush=画笔擦除"},
        "inpaint_radius": {"type": "integer", "default": 5, "description": "inpaint 半径"},
        "method": {"type": "string", "default": "telea", "description": "telea 或 ns"},
    }

    def __init__(self):
        self._bg_session = None

    def _get_bg_session(self):
        if self._bg_session is None:
            from rembg import new_session
            self._bg_session = new_session("u2net")
        return self._bg_session

    def run(self, image: Image.Image, mode="auto", mask_image: Image.Image = None,
            inpaint_radius=5, method="telea", **kw) -> ToolResult:
        img = np.array(image.convert("RGB"))
        h, w = img.shape[:2]

        if mode == "mask" and mask_image is not None:
            mask = np.array(mask_image.convert("L").resize((w, h))).astype(np.uint8)
            mask = cv2.threshold(mask, 127, 255, cv2.THRESH_BINARY)[1]
        else:
            # auto: use u2net salient mask -> invert -> erase foreground objects
            from rembg import remove
            import io
            buf = io.BytesIO(); image.save(buf, format="PNG")
            out = remove(buf.getvalue(), session=self._get_bg_session(),
                         only_mask=True, alpha_matting=False)
            mask = np.array(Image.open(io.BytesIO(out)).convert("L"))
            mask = cv2.resize(mask, (w, h))
            # salient object mask: bright = object. Keep a soft margin.
            _, mask = cv2.threshold(mask, 128, 255, cv2.THRESH_BINARY)
            # optionally dilate a bit to cover edges
            kernel = np.ones((3,3), np.uint8)
            mask = cv2.dilate(mask, kernel, iterations=2)

        method_flag = cv2.INPAINT_TELEA if method == "telea" else cv2.INPAINT_NS
        # telea supports radius
        result = cv2.inpaint(img, mask, inpaint_radius, method_flag)
        result_img = Image.fromarray(result)

        data = {
            "erased_region_percent": round(float(mask.mean() / 255.0 * 100), 2),
            "method": method,
        }
        return ToolResult(image=result_img, data=data)

ToolRegistry.register(ObjectRemoveTool())
