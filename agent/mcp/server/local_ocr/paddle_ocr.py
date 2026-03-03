"""Local OCR engine using RapidOCR (ONNX Runtime backend).

Uses pre-converted PaddleOCR ONNX models (from HuggingFace monkt/paddleocr-onnx)
with onnxruntime — no PaddlePaddle dependency required.

Models are stored in local_ocr/models/ and auto-downloaded on first use.
"""

import os
import logging

logger = logging.getLogger(__name__)

_MODELS_DIR = os.path.join(os.path.dirname(__file__), "models")

# Lazy-init singleton to avoid repeated model loading
_ocr_instance = None


def _ensure_models():
    """Download ONNX models from HuggingFace if not already present."""
    det_path = os.path.join(_MODELS_DIR, "detection", "v5", "det.onnx")
    rec_path = os.path.join(_MODELS_DIR, "languages", "chinese", "rec.onnx")
    dict_path = os.path.join(_MODELS_DIR, "languages", "chinese", "dict.txt")

    if os.path.isfile(det_path) and os.path.isfile(rec_path) and os.path.isfile(dict_path):
        return det_path, rec_path, dict_path

    logger.info("[local_ocr] Downloading ONNX models from HuggingFace...")
    from huggingface_hub import hf_hub_download
    repo = "monkt/paddleocr-onnx"
    det_path = hf_hub_download(repo, "detection/v5/det.onnx", local_dir=_MODELS_DIR)
    rec_path = hf_hub_download(repo, "languages/chinese/rec.onnx", local_dir=_MODELS_DIR)
    dict_path = hf_hub_download(repo, "languages/chinese/dict.txt", local_dir=_MODELS_DIR)
    logger.info("[local_ocr] ONNX models downloaded")
    return det_path, rec_path, dict_path


def _detect_gpu_provider():
    """Check which GPU execution providers are available in onnxruntime.
    Returns ('dml', True) for DirectML, ('cuda', True) for CUDA, or ('cpu', False)."""
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        if 'DmlExecutionProvider' in providers:
            return 'dml', True
        if 'CUDAExecutionProvider' in providers:
            return 'cuda', True
    except Exception:
        pass
    return 'cpu', False


def _get_ocr():
    """Get or create the RapidOCR singleton instance.
    Auto-detects GPU (DirectML or CUDA) and uses it if available."""
    global _ocr_instance
    if _ocr_instance is None:
        det_path, rec_path, dict_path = _ensure_models()
        provider, use_gpu = _detect_gpu_provider()
        logger.info(f"[local_ocr] Initializing RapidOCR — provider={provider}, gpu={use_gpu}")

        from rapidocr_onnxruntime import RapidOCR
        kwargs = dict(
            det_model_path=det_path,
            rec_model_path=rec_path,
            rec_keys_path=dict_path,
        )
        if provider == 'dml':
            kwargs.update(det_use_dml=True, cls_use_dml=True, rec_use_dml=True)
        elif provider == 'cuda':
            kwargs.update(det_use_cuda=True, cls_use_cuda=True, rec_use_cuda=True)

        _ocr_instance = RapidOCR(**kwargs)
        logger.info(f"[local_ocr] RapidOCR engine initialized ({provider})")
    return _ocr_instance


def _quad_to_rect(quad):
    """Convert a 4-point quadrilateral to an axis-aligned bounding rect.

    Args:
        quad: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    Returns:
        (x_min, y_min, x_max, y_max) as ints
    """
    xs = [pt[0] for pt in quad]
    ys = [pt[1] for pt in quad]
    return int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))


def scale_ocr_coordinates(ocr_data, scale_x, scale_y):
    """Scale all coordinates in normalized OCR data by the given factors.

    Used to convert coordinates from a resized image back to the original
    image resolution.  Must be called BEFORE _apply_window_offset.

    Args:
        ocr_data: list of dicts in remote OCR format
        scale_x: horizontal scale factor (original_width / resized_width)
        scale_y: vertical scale factor (original_height / resized_height)
    Returns:
        ocr_data (mutated in-place) with scaled coordinates
    """
    if not ocr_data or (scale_x == 1.0 and scale_y == 1.0):
        return ocr_data
    for item in ocr_data:
        loc = item.get('loc')
        if isinstance(loc, list) and len(loc) == 4:
            loc[0] = int(loc[0] * scale_y)  # y1
            loc[1] = int(loc[1] * scale_x)  # x1
            loc[2] = int(loc[2] * scale_y)  # y2
            loc[3] = int(loc[3] * scale_x)  # x2
        for ts in item.get('txt_struct', []):
            if not isinstance(ts, dict):
                continue
            for box in [ts.get('box')] + [w.get('box') for w in ts.get('words', []) if isinstance(w, dict)]:
                if isinstance(box, list) and len(box) == 4:
                    box[0] = int(box[0] * scale_x)  # x1
                    box[1] = int(box[1] * scale_y)  # y1
                    box[2] = int(box[2] * scale_x)  # x2
                    box[3] = int(box[3] * scale_y)  # y2
    return ocr_data


def normalize_to_remote_format(raw_result):
    """Convert RapidOCR output to the remote OCR server format.

    Each RapidOCR line (quad_box, text, confidence) becomes one paragraph item:
        {
            "name": "paragraph",
            "text": <text>,
            "loc": [y1, x1, y2, x2],
            "type": "paragraph",
            "txt_struct": [{
                "num": 0,
                "text": <text>,
                "box": [x1, y1, x2, y2],
                "words": [{"num": 0, "text": <text>, "box": [x1, y1, x2, y2]}]
            }]
        }

    Args:
        raw_result: list of (quad_box, text, confidence) from RapidOCR
    Returns:
        list of dicts in remote OCR format
    """
    if not raw_result:
        return []

    ocr_data = []
    for line in raw_result:
        quad = line[0]
        text = line[1]
        x_min, y_min, x_max, y_max = _quad_to_rect(quad)
        loc = [y_min, x_min, y_max, x_max]       # [y1, x1, y2, x2]

        # IMPORTANT: each box must be a separate list object because
        # _apply_window_offset mutates lists in-place; sharing would
        # cause the offset to be applied twice.
        ts_box = [x_min, y_min, x_max, y_max]    # [x1, y1, x2, y2]
        w_box  = [x_min, y_min, x_max, y_max]    # [x1, y1, x2, y2]

        ocr_data.append({
            "name": "paragraph",
            "text": text,
            "loc": loc,
            "type": "paragraph",
            "txt_struct": [{
                "num": 0,
                "text": text,
                "box": ts_box,
                "words": [{"num": 0, "text": text, "box": w_box}],
            }],
        })

    return ocr_data


def run_ocr_on_image(image_path: str) -> dict:
    """Run OCR on an image file and return raw results.

    Args:
        image_path: Absolute path to an image file (PNG, JPG, BMP, etc.)

    Returns:
        dict with keys:
            - status: "success" or "error"
            - image_path: the input path
            - results: list of detected text items, each with:
                - text: recognized text string
                - confidence: float 0-1
                - box: [[x1,y1],[x2,y2],[x3,y3],[x4,y4]] quadrilateral
            - error: error message if status is "error"
    """
    if not os.path.isfile(image_path):
        return {
            "status": "error",
            "image_path": image_path,
            "results": [],
            "error": f"File not found: {image_path}",
        }

    try:
        ocr = _get_ocr()
        logger.info(f"[local_ocr] Running OCR on: {image_path}")
        raw_result, elapsed = ocr(image_path)

        # RapidOCR returns list of (box, text, confidence)
        # box is [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
        items = []
        if raw_result:
            for line in raw_result:
                box = [[float(c) for c in pt] for pt in line[0]]
                text = line[1]
                conf = line[2]
                items.append({
                    "text": text,
                    "confidence": round(float(conf), 4),
                    "box": box,
                })

        # Normalize to remote OCR server format
        ocr_data = normalize_to_remote_format(raw_result)

        logger.info(f"[local_ocr] OCR completed: {len(items)} text items detected, "
                    f"elapsed={elapsed}")
        return {
            "status": "success",
            "image_path": image_path,
            "results": items,
            "ocr_data": ocr_data,
            "error": "",
        }

    except Exception as e:
        import traceback
        err = traceback.format_exc()
        logger.error(f"[local_ocr] OCR failed: {err}")
        return {
            "status": "error",
            "image_path": image_path,
            "results": [],
            "error": str(e),
        }
