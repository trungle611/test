import re
import unicodedata
from difflib import SequenceMatcher

AVOID_VARIANTS = {
    "thịt": {
        "thịt",
        "bò",
        "heo",
        "lợn",
        "gà",
        "vịt",
        "ngan",
        "dê",
        "cừu",
        "trâu",
        "sườn",
        "ba chỉ",
        "giò",
        "chả",
        "xúc xích",
    },
    "hải sản": {"hải sản", "tôm", "cua", "ghẹ", "mực", "bạch tuộc", "sò", "ốc", "ngao", "hàu"},
    "cá": {"cá"},
    "tôm": {"tôm"},
    "trứng": {"trứng"},
    "sữa": {"sữa", "phô mai", "bơ sữa", "kem sữa", "whey"},
    "đậu phộng": {"đậu phộng", "lạc"},
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", text.casefold())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text)).strip()


def normalize_spelling(text: str) -> str:
    """Chuẩn hóa cách viết nhưng giữ dấu để ưu tiên tên tiếng Việt chính xác."""
    text = unicodedata.normalize("NFC", text.casefold())
    return re.sub(r"\s+", " ", "".join(ch if ch.isalnum() else " " for ch in text)).strip()


def find_avoid_matches(avoid_tags, texts):
    """Đối chiếu thành phần cần tránh với tên món và thành phần AI nhìn thấy."""
    haystack = " ".join(normalize_spelling(str(text)) for text in texts if text)
    matches = []
    for raw_tag in avoid_tags or []:
        tag = str(raw_tag).strip()
        normalized_tag = normalize_spelling(tag)
        if not normalized_tag:
            continue
        variants = {
            normalize_spelling(value)
            for value in AVOID_VARIANTS.get(normalized_tag, {normalized_tag})
        }
        if any(re.search(rf"(?:^| ){re.escape(variant)}(?: |$)", haystack) for variant in variants):
            matches.append(tag)
    return matches


def match_foods(labels, foods, limit=3):
    found = {}
    names_by_food = {
        food.id: [getattr(food, "display_name", None) or food.name]
        + [alias.alias for alias in food.aliases]
        for food in foods
    }
    for rank, label in enumerate(labels):
        query = normalize(label)
        if not query:
            continue
        exact_ids = {
            food_id
            for food_id, names in names_by_food.items()
            if any(normalize_spelling(name) == normalize_spelling(label) for name in names)
        }
        candidates = [food for food in foods if not exact_ids or food.id in exact_ids]
        for food in candidates:
            names = names_by_food[food.id]
            score = max(
                (
                    1.0
                    if normalize(name) == query
                    else SequenceMatcher(None, query, normalize(name)).ratio()
                )
                for name in names
            )
            # Chỉ chấp nhận lỗi viết rất nhỏ. Ngưỡng cũ 0,74 thường biến món khác
            # có vài từ giống nhau thành lựa chọn sai trên giao diện.
            if score >= 0.90:
                current = found.get(food.id)
                value = score - rank * 0.01
                if current is None or value > current[0]:
                    found[food.id] = (value, food)
    return [item[1] for item in sorted(found.values(), key=lambda x: x[0], reverse=True)[:limit]]


def nutrition(food, amount):
    if amount <= 0 or amount > 2000:
        raise ValueError("Khẩu phần phải lớn hơn 0 và không quá 2000 đơn vị")
    basis_amount = getattr(food, "basis_amount", 100) or 100
    factor = amount / basis_amount
    return {
        key: round(getattr(food, key + "_100g") * factor, 1)
        for key in ("kcal", "protein", "carb", "fat")
    }


def is_discrete_unit(unit):
    """Đơn vị đếm theo món phải dùng số nguyên; g và ml là đơn vị đo liên tục."""
    return (unit or "g").casefold() not in {"g", "ml"}


def validate_quantity(food, amount):
    if amount <= 0 or amount > 2000:
        raise ValueError("Khẩu phần phải lớn hơn 0 và không quá 2000 đơn vị")
    unit = getattr(food, "basis_unit", "g") or "g"
    if is_discrete_unit(unit) and not float(amount).is_integer():
        raise ValueError(f"Định lượng theo đơn vị {unit} phải là số nguyên")


SLOTS = ("breakfast", "lunch", "dinner")


def validate_plan(days, allowed_ids, foods, avoid_tags, target_kcal):
    if len(days) != 7:
        raise ValueError("Thực đơn phải có đúng 7 ngày")
    allowed = set(allowed_ids)
    lookup = {food.id: food for food in foods}
    forbidden = set(avoid_tags)
    result = []
    for expected_day, day in enumerate(days, 1):
        if day.get("day") != expected_day:
            raise ValueError("Ngày trong kế hoạch không hợp lệ")
        meals = day.get("meals", [])
        if len(meals) != 3 or {meal.get("meal_slot") for meal in meals} != set(SLOTS):
            raise ValueError("Mỗi ngày cần ba bữa đúng cấu trúc")
        total = 0.0
        checked = []
        for meal in meals:
            food_id = meal.get("food_id")
            grams = meal.get("grams")
            if food_id not in allowed or food_id not in lookup:
                raise ValueError("Food ID nằm ngoài danh mục được phép")
            food = lookup[food_id]
            if set(food.avoid_tags or []) & forbidden:
                raise ValueError("Món có thành phần cần tránh")
            if not isinstance(grams, (int, float)) or isinstance(grams, bool):
                raise ValueError("Khối lượng không hợp lệ")
            validate_quantity(food, grams)
            values = nutrition(food, grams)
            total += values["kcal"]
            checked.append({**meal, "name": food.name, "nutrition": values})
        if not 0.8 * target_kcal <= total <= 1.2 * target_kcal:
            raise ValueError("Tổng năng lượng ngoài khoảng mục tiêu")
        result.append({"day": expected_day, "meals": checked, "total_kcal": round(total, 1)})
    return result


def fallback_plan(foods, target_kcal):
    if len(foods) < 3:
        raise ValueError("Cần tối thiểu 3 món đủ điều kiện")
    continuous_foods = [
        food for food in foods if not is_discrete_unit(getattr(food, "basis_unit", "g"))
    ]
    if len(continuous_foods) >= 3:
        foods = continuous_foods
    days = []
    for day in range(1, 8):
        meals = []
        for index, slot in enumerate(SLOTS):
            food = foods[(day - 1 + index) % len(foods)]
            raw_amount = (
                (target_kcal / 3) / food.kcal_100g * (getattr(food, "basis_amount", 100) or 100)
            )
            unit = getattr(food, "basis_unit", "g")
            grams = (
                round(raw_amount) if unit == "g" or is_discrete_unit(unit) else round(raw_amount, 2)
            )
            minimum = 1 if unit == "g" else 0.01
            if not minimum <= grams <= 2000:
                raise ValueError("Danh mục không đáp ứng mục tiêu năng lượng")
            meals.append({"meal_slot": slot, "food_id": food.id, "grams": grams})
        days.append({"day": day, "meals": meals})
    return days
