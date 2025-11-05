# services/similarity.py
# 유사 이미지 검사 비활성 스텁: 항상 (0.0, None) 반환
from pathlib import Path
from typing import Tuple, Optional, Union, Iterable

PathLike = Union[str, Path]
AttachmentArg = Union[PathLike, Iterable[PathLike]]

def best_similarity_against_folder(
    target_path: AttachmentArg,
    folder: Path,
    size: int = 512
) -> Tuple[float, Optional[Path]]:
    """
    비활성 스텁:
    항상 유사도 0.0과 참조 경로 None을 반환.
    """
    return 0.0, None
