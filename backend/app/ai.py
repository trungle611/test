import json
import math
import os
import re
import time
from contextvars import ContextVar
from functools import wraps
from pathlib import Path

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

from .scan_service import validate_scan_result

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

SCAN_PROMPT_VERSION = "scan-v7-nutrition-per-gram"
PLAN_PROMPT_VERSION = "plan-v1"
GUIDANCE_PROMPT_VERSION = "profile-guidance-v7-kcal-fit"
DEFAULT_MODEL = "gemini-3.5-flash-lite"
REQUEST_BUDGET_SECONDS = 45
ATTEMPT_TIMEOUT_MS = 20000
MAX_ATTEMPTS = 3
_request_deadline = ContextVar("gemini_request_deadline", default=None)


class AIConfigurationError(RuntimeError):
    """Thiếu cấu hình cần thiết để gọi Gemini."""


class AIResponseError(RuntimeError):
    """Gemini trả dữ liệu không đáp ứng hợp đồng của ứng dụng."""


class AIServiceError(RuntimeError):
    """Lỗi dịch vụ đã được phân loại, không chứa key hoặc phản hồi nhạy cảm."""

    def __init__(self, reason):
        self.reason = reason
        messages = {
            "timeout": "AI phản hồi quá lâu. Hãy thử lại sau hoặc chọn món thủ công",
            "network": "Không kết nối được với dịch vụ AI. Hãy thử lại sau hoặc chọn món thủ công",
            "quota": "AI đang chạm giới hạn lượt dùng. Hãy đợi một lúc hoặc chọn món thủ công",
            "overloaded": "Dịch vụ AI đang quá tải. Hãy thử lại sau hoặc chọn món thủ công",
            "authentication": "Cấu hình truy cập AI không hợp lệ. Hãy liên hệ người quản trị",
        }
        super().__init__(messages[reason])


def bounded_request(fn):
    """Dùng chung thời gian chờ cho cả nhận diện, dự phòng và sửa tiếng Việt."""

    @wraps(fn)
    def wrapped(*args, **kwargs):
        token = _request_deadline.set(time.monotonic() + REQUEST_BUDGET_SECONDS)
        try:
            return fn(*args, **kwargs)
        finally:
            _request_deadline.reset(token)

    return wrapped


def client(key=None):
    key = (key if key is not None else os.getenv("GEMINI_API_KEY", "")).strip()
    return (
        genai.Client(api_key=key, http_options=types.HttpOptions(timeout=ATTEMPT_TIMEOUT_MS))
        if key
        else None
    )


def require_client():
    ai = client()
    if ai is None:
        raise AIConfigurationError("Chưa cấu hình GEMINI_API_KEY")
    return ai


def _reject_json_constant(_value):
    raise ValueError("JSON chứa số không hữu hạn")


def _finite_json_float(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON chứa số vượt giới hạn")
    return number


def generate_json(ai, contents, schema):
    """Tối đa ba lượt gọi; timeout/mạng cũng được chuyển sang project dự phòng."""
    deadline = _request_deadline.get() or time.monotonic() + REQUEST_BUDGET_SECONDS
    active_client = ai
    fallback_key = os.getenv("GEMINI_FALLBACK_API_KEY", "").strip()
    primary_key = os.getenv("GEMINI_API_KEY", "").strip()
    has_fallback = bool(fallback_key and fallback_key != primary_key)
    reason = "timeout"
    for attempt in range(MAX_ATTEMPTS):
        remaining_ms = int((deadline - time.monotonic()) * 1000)
        if remaining_ms <= 0:
            raise AIServiceError("timeout")
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            http_options=types.HttpOptions(timeout=min(ATTEMPT_TIMEOUT_MS, remaining_ms)),
        )
        try:
            response = active_client.models.generate_content(
                model=os.getenv("GEMINI_MODEL", DEFAULT_MODEL), contents=contents, config=config
            )
        except (httpx.TimeoutException, TimeoutError):
            reason = "timeout"
        except httpx.TransportError:
            reason = "network"
        except errors.APIError as exc:
            if exc.code in (401, 403):
                reason = "authentication"
            elif exc.code == 429:
                reason = "quota"
            elif exc.code in (408, 504):
                reason = "timeout"
            elif exc.code in (500, 502, 503):
                reason = "overloaded"
            else:
                raise
            if reason == "authentication" and (attempt > 0 or not has_fallback):
                raise AIServiceError(reason) from None
        else:
            try:
                result = json.loads(
                    response.text,
                    parse_constant=_reject_json_constant,
                    parse_float=_finite_json_float,
                )
                if not isinstance(result, dict):
                    raise ValueError("Kết quả AI phải là một JSON object")
                return result
            except (ValueError, TypeError):
                raise AIResponseError(
                    "AI trả kết quả không hợp lệ. Hãy thử nhận diện lại"
                ) from None

        if attempt == MAX_ATTEMPTS - 1:
            break
        if attempt == 0 and has_fallback:
            active_client = client(fallback_key)
        delay = min(0.5 * 2**attempt, max(0, deadline - time.monotonic()))
        time.sleep(delay)
    raise AIServiceError(reason)


ENGLISH_SCAN_WORDS = {
    "and",
    "beef",
    "broth",
    "chicken",
    "egg",
    "exact",
    "fish",
    "fried",
    "ingredient",
    "ingredients",
    "meat",
    "noodle",
    "noodles",
    "pork",
    "recipe",
    "rice",
    "sauce",
    "slice",
    "slices",
    "soup",
    "steak",
    "unclear",
    "vegetable",
    "vegetables",
    "with",
}

# Các từ đủ đặc trưng để nhận ra một câu tiếng Việt đang bị Gemini bỏ dấu.
# Chỉ kết luận khi có nhiều từ cùng xuất hiện, tránh nhầm tên thương hiệu hoặc ID.
VIETNAMESE_ASCII_MARKERS = {
    "an",
    "bao",
    "ban",
    "bua",
    "can",
    "cach",
    "chat",
    "chia",
    "chieu",
    "chon",
    "co",
    "com",
    "dam",
    "dang",
    "danh",
    "de",
    "deu",
    "dinh",
    "don",
    "du",
    "duong",
    "giup",
    "giam",
    "hay",
    "khau",
    "khong",
    "lau",
    "len",
    "lich",
    "luong",
    "luyen",
    "mon",
    "muc",
    "ngay",
    "nguoi",
    "nhom",
    "phu",
    "phuong",
    "rau",
    "tang",
    "tap",
    "theo",
    "thuc",
    "tieu",
    "trong",
    "voi",
}

FOOD_ASCII_MARKERS = {
    "banh",
    "bo",
    "bun",
    "ca",
    "canh",
    "cha",
    "chien",
    "com",
    "cuon",
    "ga",
    "heo",
    "hu",
    "kho",
    "mien",
    "nuong",
    "pho",
    "sot",
    "sua",
    "tam",
    "thit",
    "tieu",
    "tom",
    "trung",
    "xao",
    "rau",
    "muong",
    "luoc",
    "cai",
    "khoai",
    "lang",
    "dau",
    "phu",
    "xoi",
    "gio",
    "lon",
    "vit",
    "hap",
    "ham",
    "sup",
}


def scan_contains_english(value):
    """Phát hiện các từ tiếng Anh thường bị Gemini để sót trong kết quả quét."""
    if isinstance(value, dict):
        return any(scan_contains_english(item) for item in value.values())
    if isinstance(value, list):
        return any(scan_contains_english(item) for item in value)
    if not isinstance(value, str):
        return False
    words = set(re.findall(r"[a-z]+", value.casefold()))
    return bool(words & ENGLISH_SCAN_WORDS)


def contains_unaccented_vietnamese(value):
    """Phát hiện câu tiếng Việt dài bị viết không dấu trong dữ liệu JSON."""
    if isinstance(value, dict):
        return any(contains_unaccented_vietnamese(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_unaccented_vietnamese(item) for item in value)
    if not isinstance(value, str):
        return False
    words = re.findall(r"[a-z]+", value.casefold())
    if value.isascii() and 2 <= len(words) <= 8:
        food_words = sum(word in FOOD_ASCII_MARKERS for word in words)
        if food_words >= 2 and food_words >= len(words) * 0.5:
            return True
    marker_count = sum(word in VIETNAMESE_ASCII_MARKERS for word in words)
    return marker_count >= 3 and marker_count >= len(words) * 0.25


def _preserves_data(before, after, field=None):
    if isinstance(before, dict):
        return (
            isinstance(after, dict)
            and before.keys() == after.keys()
            and all(_preserves_data(value, after[key], key) for key, value in before.items())
        )
    if isinstance(before, list):
        return (
            isinstance(after, list)
            and len(before) == len(after)
            and all(_preserves_data(a, b, field) for a, b in zip(before, after))
        )
    if isinstance(before, str):
        protected = {"id", "food_id", "meal_type", "meal_slot", "unit", "basis_unit"}
        return isinstance(after, str) and (field not in protected or before == after)
    if isinstance(before, bool) or before is None:
        return type(before) is type(after) and before == after
    return isinstance(after, (int, float)) and not isinstance(after, bool) and before == after


def rewrite_vietnamese(ai, result, schema):
    prompt = (
        "Dịch toàn bộ giá trị dạng chuỗi trong JSON sau và viết lại thành tiếng Việt tự nhiên, đầy đủ dấu tiếng Việt. "
        "Dịch mọi từ tiếng Anh thông thường sang tiếng Việt; chỉ giữ nguyên tên thương hiệu, mã ID và tên riêng cần thiết. "
        "Không thay đổi cấu trúc JSON, số liệu, ý nghĩa, thứ tự hoặc số phần tử trong các mảng. JSON: "
        f"{json.dumps(result, ensure_ascii=False)}"
    )
    rewritten = generate_json(ai, prompt, schema)
    if not _preserves_data(result, rewritten):
        raise AIResponseError(
            "AI thay đổi cấu trúc, mã món hoặc số liệu khi sửa tiếng Việt. Hãy thử lại hoặc nhập tay"
        )
    return rewritten


def _checked_scan_result(result):
    try:
        return validate_scan_result(result)
    except ValueError:
        raise AIResponseError("AI trả kết quả món ăn sai cấu trúc. Hãy thử nhận diện lại") from None


@bounded_request
def scan_image(image_bytes: bytes, mime_type: str, catalog=None, avoid_tags=None):
    ai = require_client()
    catalog = catalog or []
    avoid_tags = avoid_tags or []
    catalog_text = json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
    prompt = (
        "Hãy nhận diện từng món ăn riêng biệt thực sự nhìn thấy trong ảnh, tối đa 5 món. "
        "Với mỗi món, trả tối đa 3 tên theo thứ tự khả năng. Các tên thay thế phải mô tả cùng một món, "
        "không được liệt kê những món khác nhau chỉ vì có hình dáng gần giống. Không gộp các món khác nhau. "
        "Ưu tiên dùng nguyên văn tên tiếng Việt trong danh mục CSV tham chiếu bên dưới khi hình ảnh phù hợp. "
        "Không ép khớp nếu ảnh không giống mục nào; khi đó vẫn trả tên tiếng Việt hợp lý để người dùng nhập tay. "
        "Trả confidence từ 0 đến 1 dựa trên mức nhìn rõ món và nguyên liệu. Nếu không nhìn đủ bằng chứng để phân biệt, "
        "confidence phải dưới 0.65 và uncertainty_reason phải nói rõ phần nào không nhìn thấy. "
        "Nếu ảnh mờ hoặc không phải đồ ăn thì trả dishes là mảng rỗng và nêu cảnh báo. "
        "MÓN NGOÀI DANH MỤC: vẫn trả tên món đúng theo ảnh, không ép chọn món gần giống trong CSV. "
        "Với mỗi món có thể nhận diện, kể cả không có trong CSV, trả estimated_nutrition_1g: "
        "ước tính kcal, protein, carbohydrate (carb), chất béo (fat) trong ĐÚNG 1 g món đã chế biến. "
        "kcal có đơn vị kcal/g; ba chất còn lại có đơn vị g/g. Không trả số liệu của cả đĩa hoặc 100 g vào trường này. "
        "Giữ số thập phân đủ nhỏ, không làm tròn macro về số nguyên. "
        "Ví dụ 100 g có 200 kcal và 15 g protein thì 1 g có 2 kcal và 0.15 g protein. "
        "Nêu trong uncertainty_reason những điểm chưa rõ về cách nấu, dầu, sốt hoặc tỷ lệ nguyên liệu. "
        "Các số chỉ để người dùng sửa và xác nhận, không xem là dữ liệu đo chính xác. "
        "Nếu ảnh không đủ rõ để ước tính, trả 0 cho cả bốn số. Không đoán khối lượng khẩu phần từ ảnh. Không tạo food_id. "
        "QUY TẮC NGÔN NGỮ BẮT BUỘC: mọi chuỗi trong JSON phải là tiếng Việt tự nhiên, có dấu. "
        "Tên món, candidate_labels, visible_ingredients, uncertainty_reason và warning tuyệt đối không được viết tiếng Anh; "
        "hãy dịch cả tên nguyên liệu sang tiếng Việt, chỉ giữ nguyên tên thương hiệu riêng nếu thật sự cần thiết. "
        f"Người dùng cần tránh {json.dumps(avoid_tags, ensure_ascii=False)}. Hãy quan sát kỹ và ghi rõ trong "
        "visible_ingredients nếu thấy thành phần liên quan; không được khẳng định món an toàn chỉ dựa vào ảnh. "
        "Mọi kết quả đều cần người dùng xác nhận trước khi lưu. "
        f"DANH MỤC CSV THAM CHIẾU (tên và khẩu phần chuẩn): {catalog_text}"
    )
    dish_schema = {
        "type": "object",
        "properties": {
            "candidate_labels": {"type": "array", "items": {"type": "string"}},
            "confidence": {"type": "number"},
            "visible_ingredients": {"type": "array", "items": {"type": "string"}},
            "uncertainty_reason": {"type": "string"},
            "estimated_nutrition_1g": {
                "type": "object",
                "properties": {
                    "kcal": {"type": "number"},
                    "protein": {"type": "number"},
                    "carb": {"type": "number"},
                    "fat": {"type": "number"},
                },
                "required": ["kcal", "protein", "carb", "fat"],
            },
        },
        "required": [
            "candidate_labels",
            "confidence",
            "visible_ingredients",
            "uncertainty_reason",
            "estimated_nutrition_1g",
        ],
    }
    schema = {
        "type": "object",
        "properties": {
            "dishes": {"type": "array", "items": dish_schema},
            "warning": {"type": "string"},
        },
        "required": ["dishes", "warning"],
    }
    result = _checked_scan_result(
        generate_json(
            ai, [types.Part.from_bytes(data=image_bytes, mime_type=mime_type), prompt], schema
        )
    )
    if scan_contains_english(result) or contains_unaccented_vietnamese(result):
        result = _checked_scan_result(rewrite_vietnamese(ai, result, schema))
    if scan_contains_english(result) or contains_unaccented_vietnamese(result):
        raise AIResponseError(
            "Gemini chưa trả kết quả hoàn toàn bằng tiếng Việt. Hãy thử nhận diện lại"
        )
    return result


def generate_plan(foods, target_kcal):
    ai = require_client()
    catalog = [
        {
            "food_id": f.id,
            "name": f.display_name or f.name,
            "energy_per_basis": f.kcal_100g,
            "basis_amount": f.basis_amount,
            "basis_unit": f.basis_unit,
        }
        for f in foods
    ]
    prompt = (
        "Lập thực đơn đúng 7 ngày, mỗi ngày đúng 3 bữa breakfast, lunch, dinner. "
        "Chỉ dùng food_id trong danh mục. Trường grams là số lượng theo basis_unit của món tương ứng; "
        "chọn giá trị lớn hơn 0 và không quá 2000 để tổng năng lượng mỗi ngày "
        "nằm trong khoảng 80%-120% mục tiêu. Không tự đưa số macro. "
        f"Mục tiêu {target_kcal} kcal/ngày. Danh mục: {json.dumps(catalog, ensure_ascii=False)}"
    )
    schema = {
        "type": "object",
        "properties": {
            "days": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "day": {"type": "integer"},
                        "meals": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "meal_slot": {"type": "string"},
                                    "food_id": {"type": "string"},
                                    "grams": {"type": "number"},
                                },
                                "required": ["meal_slot", "food_id", "grams"],
                            },
                        },
                    },
                    "required": ["day", "meals"],
                },
            }
        },
        "required": ["days"],
    }
    return generate_json(ai, prompt, schema)["days"]


@bounded_request
def generate_profile_guidance(
    profile, target_weight_kg, plan_names, targets=None, food_catalog=None
):
    ai = require_client()
    context = {
        "age": profile.age,
        "height_cm": profile.height_cm,
        "current_weight_kg": profile.weight_kg,
        "target_weight_kg": target_weight_kg,
        "sex_for_estimate": profile.sex,
        "activity_level": profile.activity_level,
        "daily_targets_estimate": targets,
        "avoid_ingredients": profile.avoid_tags or [],
        "available_workouts": plan_names,
        "csv_food_catalog": food_catalog or [],
    }
    prompt = (
        "Bạn là trợ lý sức khỏe cho người trưởng thành. Đọc dữ liệu hồ sơ dưới đây và trả lời bằng tiếng Việt tự nhiên, đầy đủ dấu. "
        "Đưa ra phân tích ngắn và hai cách ăn uống khác nhau, phù hợp mục tiêu tăng/giảm/duy trì cân nặng. "
        "Trong MỖI phương án, examples phải có từ 3 đến 6 phần tử, mỗi bữa breakfast, lunch và dinner có ít nhất một món, không lặp food_id. "
        "Hãy phối hợp số món phù hợp để backend chọn số khẩu phần nguyên và đưa tổng kcal, macro gần daily_targets_estimate. "
        "Chỉ dùng food_id có trong csv_food_catalog; không tự tạo ID hoặc tên món. "
        "và một nhận xét ngắn cho PPL, một cho Upper/Lower để người dùng tự chọn. "
        "Ưu tiên ăn đủ chất và tập kháng lực phù hợp, không đề xuất ăn kiêng cực đoan, "
        "Nếu có daily_targets_estimate, gợi ý món phù hợp với kcal và các macro đó nhưng không tự đổi con số. "
        "Ưu tiên dùng đúng tên món trong csv_food_catalog và không tự bịa số dinh dưỡng ngoài catalog; "
        "nếu thiếu, không tự đưa kcal/ngày. Không hứa đạt cân nặng đúng hạn, không chẩn đoán. "
        "Tôn trọng thành phần cần tránh. Nếu mục tiêu có vẻ không phù hợp, nói cần tham khảo chuyên gia. "
        f"Hồ sơ: {json.dumps(context, ensure_ascii=False)}"
    )
    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "food_options": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "detail": {"type": "string"},
                        "examples": {
                            "type": "array",
                            "minItems": 3,
                            "maxItems": 6,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "meal_type": {
                                        "type": "string",
                                        "enum": ["breakfast", "lunch", "dinner"],
                                    },
                                    "food_id": {"type": "string"},
                                },
                                "required": ["meal_type", "food_id"],
                            },
                        },
                    },
                    "required": ["title", "detail", "examples"],
                },
            },
            "ppl_note": {"type": "string"},
            "ul_note": {"type": "string"},
        },
        "required": ["summary", "food_options", "ppl_note", "ul_note"],
    }
    result = generate_json(ai, prompt, schema)
    if scan_contains_english(result) or contains_unaccented_vietnamese(result):
        result = rewrite_vietnamese(ai, result, schema)
    if scan_contains_english(result) or contains_unaccented_vietnamese(result):
        raise AIResponseError(
            "Gemini chưa trả gợi ý hoàn toàn bằng tiếng Việt có dấu. Hãy thử phân tích lại"
        )
    return result
