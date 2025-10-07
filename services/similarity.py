# services/similarity.py
from __future__ import annotations
from pathlib import Path
from typing import Tuple, Optional
import numpy as np

from PIL import Image
from skimage.metrics import structural_similarity as ssim

SUPPORTED_IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}

def _load_gray_square_resize(p: Path, size: int = 512) -> Image.Image:
    img = Image.open(p).convert("L")
    w, h = img.size
    s = max(w, h)
    canvas = Image.new("L", (s, s), 255)
    canvas.paste(img, ((s - w)//2, (s - h)//2))
    return canvas.resize((size, size), Image.Resampling.BICUBIC)

def _ssim(a: Image.Image, b: Image.Image) -> float:
    A = np.asarray(a, dtype=np.float32)
    B = np.asarray(b, dtype=np.float32)
    return float(ssim(A, B, data_range=255))

def best_similarity_against_folder(
    target_path: Path,
    folder: Path,
    size: int = 512
) -> Tuple[float, Optional[Path]]:
    """
    folder 내 모든 이미지와 target_path(이미지)를 SSIM 비교.
    가장 높은 점수와 그 파일 경로를 반환. (이미지 없으면 0.0, None)
    """
    if not target_path.exists():
        return 0.0, None
    if not folder.exists() or not folder.is_dir():
        return 0.0, None

    tgt = _load_gray_square_resize(target_path, size=size)
    best = 0.0
    best_file = None

    for cand in folder.iterdir():
        if not cand.is_file():
            continue
        if cand.suffix.lower() not in SUPPORTED_IMG_EXT:
            continue
        try:
            ref = _load_gray_square_resize(cand, size=size)
            score = _ssim(tgt, ref)
            if score > best:
                best = score
                best_file = cand
        except Exception:
            # 손상 이미지 등은 스킵
            continue
    return best, best_file
