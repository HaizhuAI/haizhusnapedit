"""Base tool interface + registry for SnapEdit-style AI tools."""
from __future__ import annotations
import abc, logging, time
from typing import Dict, Any, Optional, Tuple, List
import numpy as np
from PIL import Image

log = logging.getLogger("snapedit.engine")

class ToolResult:
    def __init__(self, image: Optional[Image.Image] = None, data: Optional[dict] = None,
                 error: Optional[str] = None, elapsed: float = 0.0):
        self.image = image
        self.data = data or {}
        self.error = error
        self.elapsed = elapsed

class BaseTool(abc.ABC):
    """One SnapEdit tool capability."""
    id: str = ""
    name: str = ""
    description: str = ""
    input_modes: Tuple[str, ...] = ("image",)   # what the tool consumes
    params: Dict[str, dict] = {}                 # extra params schema

    @abc.abstractmethod
    def run(self, image: Image.Image, **kwargs) -> ToolResult:
        ...

    def warmup(self) -> None:
        pass

class ToolRegistry:
    _tools: Dict[str, BaseTool] = {}

    @classmethod
    def register(cls, tool: BaseTool):
        cls._tools[tool.id] = tool
        return tool

    @classmethod
    def get(cls, tool_id: str) -> Optional[BaseTool]:
        return cls._tools.get(tool_id)

    @classmethod
    def all(cls) -> Dict[str, BaseTool]:
        return cls._tools

    @classmethod
    def summary(cls) -> List[dict]:
        return [{
            "id": t.id, "name": t.name, "description": t.description,
            "params": {k: v for k, v in t.params.items()},
        } for t in cls._tools.values()]

def safe_run(tool: BaseTool, image: Image.Image, **kwargs) -> ToolResult:
    t0 = time.time()
    try:
        r = tool.run(image, **kwargs)
        r.elapsed = time.time() - t0
        return r
    except Exception as e:
        log.exception("tool %s failed", tool.id)
        return ToolResult(error=f"{type(e).__name__}: {e}", elapsed=time.time() - t0)

def pil_to_bytes(img: Image.Image, fmt: str = "PNG", quality: int = 95) -> bytes:
    import io
    buf = io.BytesIO()
    if fmt.upper() == "JPEG":
        img = img.convert("RGB")
        img.save(buf, format="JPEG", quality=quality)
    else:
        img.save(buf, format=fmt)
    return buf.getvalue()

def bytes_to_pil(data: bytes) -> Image.Image:
    import io
    return Image.open(io.BytesIO(data)).convert("RGB")

def to_rgb_np(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("RGB")).astype(np.float32)
