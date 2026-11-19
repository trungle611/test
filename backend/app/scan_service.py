"""Xử lý file ảnh và chuẩn hóa kết quả nhận diện món ăn."""

import hashlib
import math
import os
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from .core import find_avoid_matches, match_foods

MAX_IMAGE_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
SCAN_UPLOAD_DIR = Path(
    os.getenv("SCAN_UPLOAD_DIR", Path(__file__).resolve().parents[1] / "uploads" / "scans")
)


def validate_image(raw: bytes, content_type: str | None):
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "Ảnh vượt quá 5 MB")
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(415, "Chỉ hỗ trợ JPG, PNG, WEBP")
    try:
        with Image.open(BytesIO(raw)) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(422, "File ảnh không hợp lệ") from exc


def _nutrition_estimate(item):
    # Giữ chuẩn 100 g trong database/API cũ, nhưng Gemini mới trả trên 1 g.
    per_gram = item.get("estimated_nutrition_1g")
    raw = per_gram if per_gram is not None else item.get("estimated_nutrition_100g")
    if not isinstance(raw, dict):
        return None
    factor = 100 if per_gram is not None else 1
    try:
        values = {key: float(raw[key]) * factor for key in ("kcal", "protein", "carb", "fat")}
    except (KeyError, TypeError, ValueError):
        return None
    valid = (
        all(math.isfinite(value) for value in values.values())
        and 0 < values["kcal"] <= 900
        and all(0 <= values[key] <= 100 for key in ("protein", "carb", "fat"))
    )
    return {key: round(value, 4) for key, value in values.items()} if valid else None


def build_dishes(result, foods, serialize_food, avoid_tags=None):
    dishes = []
    for item in result.get("dishes", [])[:5]:
        labels = [label for label in item.get("candidate_labels", [])[:3] if isinstance(label, str)]
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 1.0))))
        except (TypeError, ValueError):
            confidence = 0.0
        # Chỉ nhãn có khả năng cao nhất được dùng để tạo nút chọn tự động.
        # Các nhãn phụ vẫn hiển thị để người dùng tham khảo nhưng không kéo theo món CSV khác.
        candidates = match_foods(labels[:1], foods, limit=1) if confidence >= 0.65 else []
        visible_ingredients = item.get("visible_ingredients", [])
        avoid_texts = labels + visible_ingredients
        for food in candidates:
            avoid_texts.extend([food.display_name or food.name, *(food.avoid_tags or [])])
        estimate = _nutrition_estimate(item)
        dishes.append(
            {
                "suggested_labels": labels,
                "confidence": round(confidence, 2),
                "candidates": [serialize_food(food) for food in candidates],
                "estimated_nutrition_100g": estimate,
                "estimated_nutrition_1g": {
                    key: round(value / 100, 6) for key, value in estimate.items()
                }
                if estimate
                else None,
                "visible_ingredients": visible_ingredients,
                "uncertainty_reason": item.get("uncertainty_reason", ""),
                "avoid_matches": find_avoid_matches(avoid_tags or [], avoid_texts),
            }
        )
    if dishes:
        return dishes
    return [
        {
            "suggested_labels": [],
            "confidence": 0.0,
            "candidates": [],
            "visible_ingredients": [],
            "uncertainty_reason": result.get("warning") or "Không nhận diện được món ăn",
            "avoid_matches": [],
        }
    ]


def save_thumbnail(raw: bytes, history_id: str, visitor_id: str):
    owner_key = hashlib.sha1(visitor_id.encode("utf-8")).hexdigest()[:16]
    folder = SCAN_UPLOAD_DIR / owner_key
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{history_id}.webp"
    with Image.open(BytesIO(raw)) as image:
        image = image.convert("RGB")
        image.thumbnail((640, 640))
        image.save(target, "WEBP", quality=80, method=6)
    return f"{owner_key}/{history_id}.webp"


def stored_image_path(image_key: str):
    base = SCAN_UPLOAD_DIR.resolve()
    image_path = (SCAN_UPLOAD_DIR / image_key).resolve()
    if base not in image_path.parents or not image_path.is_file():
        return None
    return image_path
