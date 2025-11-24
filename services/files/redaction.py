from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple

import math

from services.attachment import SavedFileInfo
from services.regex_rules import PATTERNS as REGEX_PATTERNS

# -------------------------------
# 외부 라이브러리 (선택)
# -------------------------------
try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None  # type: ignore

try:
    import pytesseract  # type: ignore
except ImportError:  # pragma: no cover
    pytesseract = None  # type: ignore

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore

from PIL import Image, ImageDraw

# 테서렉트 경로 체크
if pytesseract is not None:
    from pathlib import Path as _Path
    # Ubuntu 패키지 설치 기본 경로들 체크 
    for _cand in ["/usr/bin/tesseract", "/usr/local/bin/tesseract"]:
        if _Path(_cand).exists():
            pytesseract.pytesseract.tesseract_cmd = _cand
            break

# ------------------------------------
# 설정값
# ------------------------------------

MIN_MP = 0.3           # 0.3 Megapixel 이하 이미지는 스킵
PDF_DPI = 220          # PDF 래스터라이즈 DPI
OCR_LANG = "kor+eng"   # Tesseract 언어
OCR_PSM = 3            # 페이지 세그먼트 모드
OCR_OEM = 1            # LSTM-only

IMAGE_EXTS = {"png", "jpg", "jpeg", "webp"}
PDF_EXTS = {"pdf"}

# 대부분 PATTERNS는 "토큰 단위"로도 매칭이 가능하지만,
# PRIVATE_KEY 같이 블록 전체를 보는 패턴은 페이지 전체를 가리는 방식으로 처리한다.
PAGE_ONLY_LABELS = {"PRIVATE_KEY"}
TOKEN_LABELS = [k for k in REGEX_PATTERNS.keys() if k not in PAGE_ONLY_LABELS]

# === EAST 관련 추가 ===
EAST_CONF_THRESH = 0.5
EAST_NMS_THRESH = 0.4

BASE_DIR = Path(__file__).resolve().parent  # == services/files

EAST_MODEL_CANDIDATES = [
    BASE_DIR / "models" / "frozen_east_text_detection.pb",  # services/files/models/...
    Path("models/frozen_east_text_detection.pb"),           # (옵션) 프로젝트 루트/models 도 같이 체크
]

_EAST_NET = None
_EAST_TRIED = False
# ======================


@dataclass
class RedactedFileInfo:
    """레댁션/마스킹 처리 후 결과."""
    ext: str
    mime: str
    original_path: Path
    redacted_path: Path        # 레댁션된 파일 경로 (레댁션이 없으면 original과 동일)
    redaction_performed: bool  # 실제로 뭔가 가린 경우 True
    redaction_error: Optional[str] = None


# ------------------------------------
# 공통 유틸
# ------------------------------------

def _mpixels_of_img(pil_img: Image.Image) -> float:
    w, h = pil_img.size
    return (w * h) / 1_000_000.0


def _ensure_ocr_available() -> Optional[str]:
    if pytesseract is None:
        return "pytesseract_not_available"
    return None


# === EAST 관련 함수들 ===

def _load_east_model():
    """frozen_east_text_detection.pb가 있으면 한 번만 로딩해서 캐싱."""
    global _EAST_NET, _EAST_TRIED
    if _EAST_TRIED:
        return _EAST_NET
    _EAST_TRIED = True

    if cv2 is None:
        _EAST_NET = None
        return None

    for p in EAST_MODEL_CANDIDATES:
        if p.exists():
            try:
                net = cv2.dnn.readNet(str(p))
                _EAST_NET = net
                return net
            except Exception:
                _EAST_NET = None
                return None

    _EAST_NET = None
    return None


def _east_has_text(net, pil_img: Image.Image, conf_thresh: float = EAST_CONF_THRESH) -> bool:
    """
    EAST로 '텍스트가 있을 법한지'만 빠르게 확인.
    - net이 None이면 True 반환 (OCR 수행 경로로)
    """
    if net is None or cv2 is None:
        return True

    img = cv2.cvtColor(
        # PIL → numpy → BGR
        __import__("numpy").array(pil_img),  # numpy가 없으면 ImportError 나지만, 일반적으로 설치되어 있음
        cv2.COLOR_RGB2BGR,
    )

    inpW = 320
    inpH = 320
    blob = cv2.dnn.blobFromImage(
        img,
        1.0,
        (inpW, inpH),
        (123.68, 116.78, 103.94),
        swapRB=True,
        crop=False,
    )
    net.setInput(blob)
    try:
        scores, geometry = net.forward(
            ["feature_fusion/Conv_7/Sigmoid", "feature_fusion/concat_3"]
        )
    except Exception:
        # EAST 실행 실패 시에는 OCR 경로를 타도록 True
        return True

    rects_xyxy: List[Tuple[int, int, int, int]] = []
    confidences: List[float] = []

    numRows, numCols = scores.shape[2:4]
    for y in range(numRows):
        scoresData = scores[0, 0, y]
        xData0 = geometry[0, 0, y]
        xData1 = geometry[0, 1, y]
        xData2 = geometry[0, 2, y]
        xData3 = geometry[0, 3, y]
        anglesData = geometry[0, 4, y]

        for x in range(numCols):
            score = float(scoresData[x])
            if score < conf_thresh:
                continue

            offsetX = x * 4.0
            offsetY = y * 4.0
            angle = float(anglesData[x])
            cos = math.cos(angle)
            sin = math.sin(angle)

            h = float(xData0[x] + xData2[x])
            w = float(xData1[x] + xData3[x])

            endX = int(offsetX + (cos * xData1[x]) + (sin * xData2[x]))
            endY = int(offsetY - (sin * xData1[x]) + (cos * xData2[x]))
            startX = int(endX - w)
            startY = int(endY - h)

            rects_xyxy.append((startX, startY, endX, endY))
            confidences.append(score)

    if not rects_xyxy:
        return False

    # xyxy → xywh
    boxes_xywh = []
    for (sx, sy, ex, ey) in rects_xyxy:
        x = int(sx)
        y = int(sy)
        w = int(max(1, ex - sx))
        h = int(max(1, ey - sy))
        boxes_xywh.append([x, y, w, h])

    try:
        idxs = cv2.dnn.NMSBoxes(boxes_xywh, confidences, conf_thresh, EAST_NMS_THRESH)
    except Exception:
        # NMS 실패 시에는 '텍스트 있을 수 있다'로 간주
        return True

    if idxs is None:
        return False
    try:
        return len(idxs) > 0
    except Exception:
        return True

# =========================


# ------------------------------------
# 이미지용 OCR + 레댁션 (regex_rules 기반)
# ------------------------------------

def _tesseract_ocr(pil_img: Image.Image) -> Tuple[str, dict]:
    cfg = f"--psm {OCR_PSM} --oem {OCR_OEM}"
    text = pytesseract.image_to_string(pil_img, lang=OCR_LANG, config=cfg)  # type: ignore
    data = pytesseract.image_to_data(
        pil_img, lang=OCR_LANG, config=cfg,
        output_type=pytesseract.Output.DICT  # type: ignore
    )
    return text, data


def _ocr_sensitive_boxes(ocr_data: dict) -> List[Tuple[int, int, int, int]]:
    """
    Tesseract image_to_data 결과에서
    regex_rules.PATTERNS(토큰형 라벨들)에 매칭되는 단어들의 박스(픽셀 좌표)를 반환.
    """
    boxes: List[Tuple[int, int, int, int]] = []

    texts = ocr_data.get("text", []) or []
    L = ocr_data.get("left", []) or []
    T = ocr_data.get("top", []) or []
    W = ocr_data.get("width", []) or []
    H = ocr_data.get("height", []) or []

    for i, w in enumerate(texts):
        s = str(w or "").strip()
        if not s:
            continue

        # 모든 토큰형 PATTERNS에 대해 검사
        for label in TOKEN_LABELS:
            rx = REGEX_PATTERNS.get(label)
            if rx and rx.search(s):
                x1 = int(L[i])
                y1 = int(T[i])
                x2 = x1 + int(W[i])
                y2 = y1 + int(H[i])
                boxes.append((x1, y1, x2, y2))
                break  # 한 단어에 여러 라벨이 걸려도 한 번만 박스 추가

    return boxes


def _merge_horiz_boxes_px(
    boxes: List[Tuple[int, int, int, int]],
    x_gap: int = 12,
    y_tol: int = 10,
) -> List[Tuple[int, int, int, int]]:
    """같은 줄 상의 인접 박스를 수평 병합 (이메일, 계좌번호 등이 분절된 경우 보완)."""
    if not boxes:
        return []
    boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
    merged = [boxes[0]]
    for x1, y1, x2, y2 in boxes[1:]:
        X1, Y1, X2, Y2 = merged[-1]
        same_line = abs(y1 - Y1) <= y_tol and abs(y2 - Y2) <= y_tol
        near = (x1 - X2) <= x_gap
        if same_line and near:
            merged[-1] = (X1, min(Y1, y1), max(X2, x2), max(Y2, y2))
        else:
            merged.append((x1, y1, x2, y2))
    return merged


def _pad_boxes_px(
    boxes: List[Tuple[int, int, int, int]],
    pad_px: int = 2,
) -> List[Tuple[int, int, int, int]]:
    """픽셀 좌표에 소폭 패딩."""
    out: List[Tuple[int, int, int, int]] = []
    for x1, y1, x2, y2 in boxes:
        out.append((
            max(0, x1 - pad_px),
            max(0, y1 - pad_px),
            x2 + pad_px,
            y2 + pad_px,
        ))
    return out


def _redact_image(pil_img: Image.Image, boxes: List[Tuple[int, int, int, int]]) -> Image.Image:
    img = pil_img.copy()
    draw = ImageDraw.Draw(img)
    for (x1, y1, x2, y2) in boxes:
        draw.rectangle([x1, y1, x2, y2], fill="black")
    return img


def _redact_image_file(saved: SavedFileInfo) -> RedactedFileInfo:
    """
    이미지 파일에 대해:
    - 해상도 체크
    - (선택) EAST로 텍스트 존재 여부 확인
    - Tesseract OCR
    - regex_rules.PATTERNS 기반 매칭 → 박스 계산
    - 박스 병합/패딩
    - 픽셀 단위로 검정 박스(래스터 마스킹)
    """
    ocr_err = _ensure_ocr_available()
    if ocr_err:
        return RedactedFileInfo(
            ext=saved.ext,
            mime=saved.mime,
            original_path=saved.path,
            redacted_path=saved.path,
            redaction_performed=False,
            redaction_error=ocr_err,
        )

    # PIL 로드
    pil = Image.open(saved.path).convert("RGB")
    if _mpixels_of_img(pil) < MIN_MP:
        # 해상도가 너무 작으면 스킵
        return RedactedFileInfo(
            ext=saved.ext,
            mime=saved.mime,
            original_path=saved.path,
            redacted_path=saved.path,
            redaction_performed=False,
            redaction_error="small_resolution",
        )

    # === EAST: 텍스트 존재 여부 빠른 체크 ===
    east_net = _load_east_model()
    if east_net is not None and not _east_has_text(east_net, pil):
        return RedactedFileInfo(
            ext=saved.ext,
            mime=saved.mime,
            original_path=saved.path,
            redacted_path=saved.path,
            redaction_performed=False,
            redaction_error="no_text_detected_by_east",
        )
    # =====================================

    # 전처리 없이 OCR (서버 안정성을 위해 최소화)
    text, data = _tesseract_ocr(pil)

    # 토큰 단위 민감정보 박스
    boxes = _ocr_sensitive_boxes(data)

    # PRIVATE_KEY 같이 블록 패턴은 전체 텍스트 기준으로 검사해서
    # 한 번이라도 매칭되면 페이지 전체를 박스로 가려버린다 (보수적 처리).
    for label in PAGE_ONLY_LABELS:
        rx = REGEX_PATTERNS.get(label)
        if rx and rx.search(text):
            boxes.append((0, 0, pil.width, pil.height))
            break

    if not boxes:
        # 아무것도 없으면 레댁션 불필요
        return RedactedFileInfo(
            ext=saved.ext,
            mime=saved.mime,
            original_path=saved.path,
            redacted_path=saved.path,
            redaction_performed=False,
            redaction_error=None,
        )

    # 병합 + 패딩
    x_gap = max(12, int(0.02 * pil.width))
    y_tol = max(10, int(0.01 * pil.height))
    boxes = _merge_horiz_boxes_px(boxes, x_gap=x_gap, y_tol=y_tol)
    boxes = _pad_boxes_px(boxes, pad_px=2)

    # 레스터 마스킹
    red = _redact_image(pil, boxes)

    # 원본과 동일한 확장자로 저장
    ext = saved.path.suffix.lower()
    fmt_map = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".tif": "TIFF",
        ".tiff": "TIFF",
        ".bmp": "BMP",
        ".webp": "WEBP",
    }
    fmt = fmt_map.get(ext, None)
    redacted_path = saved.path.with_name(f"{saved.path.stem}.redacted{ext}")

    save_kwargs = {}
    try:
        if fmt == "JPEG" and isinstance(pil.info, dict) and "exif" in pil.info:
            # EXIF 있으면 가능하면 보존
            save_kwargs["exif"] = pil.info["exif"]
    except Exception:
        pass

    red.save(redacted_path, format=fmt, **save_kwargs)

    return RedactedFileInfo(
        ext=saved.ext,
        mime=saved.mime,
        original_path=saved.path,
        redacted_path=redacted_path,
        redaction_performed=True,
        redaction_error=None,
    )


# ------------------------------------
# PDF용 OCR + 레댁션 (regex_rules 기반)
# ------------------------------------

def _pdf_page_has_text(page) -> bool:
    txt = page.get_text("text") or ""
    return bool(txt.strip())


def _pdf_sensitive_boxes(page) -> List["fitz.Rect"]:
    """
    PDF 텍스트 레이어에서
    regex_rules.PATTERNS(토큰형 라벨들)에 매칭되는 단어들의 좌표(포인트 단위)를 반환.
    """
    rects: List["fitz.Rect"] = []
    try:
        words = page.get_text("words") or []
        # words: [(x0, y0, x1, y1, "word", block_no, line_no, word_no), ...]
        for x0, y0, x1, y1, word, *_ in words:
            s = str(word or "").strip()
            if not s:
                continue
            for label in TOKEN_LABELS:
                rx = REGEX_PATTERNS.get(label)
                if rx and rx.search(s):
                    rects.append(fitz.Rect(x0, y0, x1, y1))  # type: ignore[arg-type]
                    break
    except Exception:
        pass
    return rects


def _pad_rects_pt(rects: List["fitz.Rect"], pad_pt: float = 1.5) -> List["fitz.Rect"]:
    return [
        fitz.Rect(r.x0 - pad_pt, r.y0 - pad_pt, r.x1 + pad_pt, r.y1 + pad_pt)  # type: ignore[arg-type]
        for r in rects
    ]


def _px_boxes_to_pt_rects(
    px_boxes: List[Tuple[int, int, int, int]],
    pix_w: int,
    pix_h: int,
    page_w_pt: float,
    page_h_pt: float,
) -> List["fitz.Rect"]:
    """
    px → pt (축별 실제 스케일 사용).
    PyMuPDF 좌표계와 pixmap은 둘 다 (0,0)=왼쪽-위, y는 아래로 증가.
    """
    sx = page_w_pt / float(pix_w)
    sy = page_h_pt / float(pix_h)
    rects: List["fitz.Rect"] = []
    for x1, y1, x2, y2 in px_boxes:
        X1 = x1 * sx
        X2 = x2 * sx
        Y0 = y1 * sy
        Y1 = y2 * sy
        rects.append(fitz.Rect(X1, Y0, X2, Y1))  # type: ignore[arg-type]
    return rects


def _redact_pdf_page(page, rects: List["fitz.Rect"]):
    for r in rects:
        page.add_redact_annot(r, fill=(0, 0, 0))
    page.apply_redactions()


def _redact_pdf_file(saved: SavedFileInfo) -> RedactedFileInfo:
    if fitz is None:
        return RedactedFileInfo(
            ext=saved.ext,
            mime=saved.mime,
            original_path=saved.path,
            redacted_path=saved.path,
            redaction_performed=False,
            redaction_error="pymupdf_not_available",
        )

    # OCR 사용 가능 여부 체크 (스캔 페이지 대응)
    ocr_err = _ensure_ocr_available()
    # EAST는 한 번만 로딩해서 재사용
    east_net = _load_east_model()

    any_redacted = False
    redacted_path = saved.path

    with fitz.open(saved.path) as doc:  # type: ignore[arg-type]
        work = fitz.open(stream=doc.tobytes(), filetype="pdf")  # type: ignore[arg-type]

        for i in range(len(work)):
            page = work.load_page(i)

            # 1) 텍스트 레이어가 있는 페이지: 토큰형 PATTERNS + PRIVATE_KEY(페이지 전체) 처리
            if _pdf_page_has_text(page):
                page_rects: List["fitz.Rect"] = []

                # 토큰형 PATTERNS
                token_rects = _pdf_sensitive_boxes(page)
                if token_rects:
                    page_rects.extend(token_rects)

                # PRIVATE_KEY 같이 블록성 패턴은 페이지 전체를 가린다.
                full_text = page.get_text("text") or ""
                for label in PAGE_ONLY_LABELS:
                    rx = REGEX_PATTERNS.get(label)
                    if rx and rx.search(full_text):
                        page_rects.append(page.rect)  # 전체 페이지
                        break

                if page_rects:
                    page_rects = _pad_rects_pt(page_rects, pad_pt=1.0)
                    _redact_pdf_page(page, page_rects)
                    any_redacted = True

            # 2) 텍스트 레이어가 없는 스캔/이미지 페이지
            else:
                if ocr_err:
                    # OCR 라이브러리가 없으면 이 페이지는 건너뛴다.
                    continue

                zoom = PDF_DPI / 72.0
                pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
                pil_raw = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                if _mpixels_of_img(pil_raw) < MIN_MP:
                    continue

                # === EAST: 텍스트 존재 여부 확인 ===
                if east_net is not None and not _east_has_text(east_net, pil_raw):
                    continue
                # =================================

                text, data_tmp = _tesseract_ocr(pil_raw)
                boxes = _ocr_sensitive_boxes(data_tmp)

                # PRIVATE_KEY 등 페이지 전체 패턴
                for label in PAGE_ONLY_LABELS:
                    rx = REGEX_PATTERNS.get(label)
                    if rx and rx.search(text):
                        boxes.append((0, 0, pix.width, pix.height))
                        break

                if not boxes:
                    continue

                # 병합 + 패딩
                x_gap = max(12, int(0.02 * pix.width))
                y_tol = max(10, int(0.01 * pix.height))
                boxes = _merge_horiz_boxes_px(boxes, x_gap=x_gap, y_tol=y_tol)
                boxes = _pad_boxes_px(boxes, pad_px=2)

                # px → pt
                page_w_pt = page.rect.width
                page_h_pt = page.rect.height
                pt_rects = _px_boxes_to_pt_rects(
                    boxes, pix.width, pix.height, page_w_pt, page_h_pt
                )
                pt_rects = _pad_rects_pt(pt_rects, pad_pt=1.5)
                _redact_pdf_page(page, pt_rects)
                any_redacted = True

        if any_redacted:
            redacted_path = saved.path.with_name(
                f"{saved.path.stem}.redacted{saved.path.suffix}"
            )
            work.save(redacted_path, deflate=True)
        work.close()

    return RedactedFileInfo(
        ext=saved.ext,
        mime=saved.mime,
        original_path=saved.path,
        redacted_path=redacted_path,
        redaction_performed=any_redacted,
        redaction_error=None if any_redacted else None,
    )


# ------------------------------------
# 외부에서 호출하는 진입점
# ------------------------------------

def redact_saved_file(saved: SavedFileInfo) -> RedactedFileInfo:
    """
    SavedFileInfo(다운로드된 파일)에 대해:
    - 이미지면: regex_rules.PATTERNS 기반으로 민감정보 영역 레스터 마스킹
      * OCR 전에 EAST로 텍스트 존재 여부를 확인해 쓸데없는 OCR을 줄임
    - PDF면: 텍스트 레이어 + 스캔 페이지 모두 regex_rules.PATTERNS 기반으로 레댁션/마스킹
      * 스캔 페이지에서도 OCR 전에 EAST로 텍스트 존재 여부를 확인
      * PRIVATE_KEY 같이 블록 패턴은 페이지 전체를 가리는 보수적 처리
    - 기타 확장자는 레댁션 없이 그대로 반환
    """
    # 실제 파일 경로 기준으로 확장자 normalize
    suffix = saved.path.suffix.lower().lstrip(".") if saved.path.suffix else ""
    ext = suffix or (saved.ext or "").lower().lstrip(".")

    if ext in IMAGE_EXTS:
        return _redact_image_file(saved)
    if ext in PDF_EXTS:
        return _redact_pdf_file(saved)

    # 지원 대상이 아닌 확장자는 그대로 반환
    return RedactedFileInfo(
        ext=saved.ext,
        mime=saved.mime,
        original_path=saved.path,
        redacted_path=saved.path,
        redaction_performed=False,
        redaction_error=None,
    )
