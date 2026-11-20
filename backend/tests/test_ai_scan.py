import copy
import json
from types import SimpleNamespace

import pytest

from app import ai
from app.scan_service import build_dishes, validate_scan_result


@pytest.mark.parametrize(
    "payload",
    [
        {"dishes": "Phở gà"},
        {"dishes": [None]},
        {"dishes": [{"candidate_labels": "Phở gà"}]},
        {"dishes": [{"candidate_labels": [1]}]},
        {"dishes": [{"candidate_labels": ["Phở gà"], "visible_ingredients": "Thịt gà"}]},
        {"dishes": [], "warning": []},
        {"dishes": [{"candidate_labels": ["Phở gà"], "confidence": 1.1}]},
        {"dishes": [{"candidate_labels": ["Phở gà"], "confidence": True}]},
        {"dishes": [{"candidate_labels": ["Phở gà"], "estimated_nutrition_1g": []}]},
    ],
)
def test_invalid_scan_structure_is_a_controlled_error(monkeypatch, payload):
    monkeypatch.setattr(ai, "client", lambda: SimpleNamespace(models=FakeModels([payload])))
    with pytest.raises(ai.AIResponseError, match="sai cấu trúc"):
        ai.scan_image(b"image", "image/jpeg")


def test_valid_empty_scan_remains_unknown():
    result = validate_scan_result({"dishes": [], "warning": "Không thấy món ăn"})
    dishes = build_dishes(result, [], lambda food: food)
    assert dishes[0]["candidates"] == []
    assert dishes[0]["uncertainty_reason"] == "Không thấy món ăn"


@pytest.mark.parametrize("change", ["number", "id", "structure"])
def test_language_rewrite_cannot_change_data(monkeypatch, change):
    original = {"items": [{"food_id": "F_0001", "name": "Chicken rice", "kcal": 400}]}
    rewritten = copy.deepcopy(original)
    rewritten["items"][0]["name"] = "Cơm gà"
    if change == "number":
        rewritten["items"][0]["kcal"] = 500
    elif change == "id":
        rewritten["items"][0]["food_id"] = "F_0002"
    else:
        rewritten["items"] = []
    fake = SimpleNamespace(models=FakeModels([rewritten]))
    with pytest.raises(ai.AIResponseError, match="thay đổi cấu trúc"):
        ai.rewrite_vietnamese(fake, original, {"type": "object"})


def test_language_rewrite_preserves_ids_and_numbers():
    original = {"food_id": "F_0001", "name": "Chicken rice", "kcal": 400}
    translated = {"food_id": "F_0001", "name": "Cơm gà", "kcal": 400.0}
    fake = SimpleNamespace(models=FakeModels([translated]))
    assert ai.rewrite_vietnamese(fake, original, {"type": "object"}) == translated


def test_short_unaccented_food_names_are_rewritten(monkeypatch):
    original = {
        "dishes": [{"candidate_labels": ["Pho ga"], "visible_ingredients": ["Thit ga"]}],
        "warning": "",
    }
    translated = {
        "dishes": [{"candidate_labels": ["Phở gà"], "visible_ingredients": ["Thịt gà"]}],
        "warning": "",
    }
    models = FakeModels([original, translated])
    monkeypatch.setattr(ai, "client", lambda: SimpleNamespace(models=models))
    assert ai.scan_image(b"image", "image/jpeg") == translated
    assert len(models.calls) == 2


def test_only_primary_label_can_select_a_catalog_dish():
    foods = [
        SimpleNamespace(id="pho", name="Phở gà", display_name=None, aliases=[], avoid_tags=[]),
        SimpleNamespace(id="com", name="Cơm gà", display_name=None, aliases=[], avoid_tags=[]),
    ]
    result = {"dishes": [{"candidate_labels": ["Phở gà", "Cơm gà"], "confidence": 0.9}]}
    dishes = build_dishes(result, foods, lambda food: {"id": food.id})
    assert dishes[0]["candidates"] == [{"id": "pho"}]


def test_low_confidence_requires_manual_review():
    food = SimpleNamespace(id="pho", name="Phở gà", display_name=None, aliases=[], avoid_tags=[])
    result = {"dishes": [{"candidate_labels": ["Phở gà"], "confidence": 0.4}]}
    dishes = build_dishes(result, [food], lambda item: {"id": item.id})
    assert dishes[0]["suggested_labels"] == ["Phở gà"]
    assert dishes[0]["candidates"] == []


class FakeModels:
    def __init__(self, payloads):
        self.payloads = iter(payloads)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(text=json.dumps(next(self.payloads), ensure_ascii=False))


def test_scan_requests_per_gram_estimate_for_out_of_catalog_dish(monkeypatch):
    models = FakeModels([{"dishes": [], "warning": ""}])
    monkeypatch.setattr(ai, "client", lambda: SimpleNamespace(models=models))
    ai.scan_image(b"image", "image/jpeg")
    prompt = models.calls[0]["contents"][1]
    assert "ĐÚNG 1 g" in prompt
    assert "MÓN NGOÀI DANH MỤC" in prompt
    schema = models.calls[0]["config"].response_schema
    assert "estimated_nutrition_1g" in schema["properties"]["dishes"]["items"]["required"]


def test_scan_retries_translation_when_gemini_returns_english(monkeypatch):
    english = {
        "dishes": [
            {
                "candidate_labels": ["Beef noodle soup"],
                "visible_ingredients": ["Beef slices", "Rice noodles"],
                "uncertainty_reason": "Exact recipe is unclear",
                "estimated_nutrition_100g": {"kcal": 120, "protein": 8, "carb": 15, "fat": 3},
            }
        ],
        "warning": "",
    }
    vietnamese = {
        "dishes": [
            {
                "candidate_labels": ["Phở bò"],
                "visible_ingredients": ["Thịt bò thái lát", "Bánh phở"],
                "uncertainty_reason": "Chưa xác định được công thức chính xác",
                "estimated_nutrition_100g": {"kcal": 120, "protein": 8, "carb": 15, "fat": 3},
            }
        ],
        "warning": "",
    }
    models = FakeModels([english, vietnamese])
    monkeypatch.setattr(ai, "client", lambda: SimpleNamespace(models=models))

    result = ai.scan_image(b"image", "image/jpeg")

    assert result == vietnamese
    assert len(models.calls) == 2
    assert "Dịch toàn bộ" in models.calls[1]["contents"]


def test_scan_rejects_english_after_translation_retry(monkeypatch):
    english = {
        "dishes": [
            {
                "candidate_labels": ["Chicken rice"],
                "visible_ingredients": ["Chicken", "Rice"],
                "uncertainty_reason": "",
                "estimated_nutrition_100g": {"kcal": 150, "protein": 9, "carb": 18, "fat": 4},
            }
        ],
        "warning": "",
    }
    models = FakeModels([english, english])
    monkeypatch.setattr(ai, "client", lambda: SimpleNamespace(models=models))

    with pytest.raises(RuntimeError, match="tiếng Việt"):
        ai.scan_image(b"image", "image/jpeg")


def test_profile_guidance_rewrites_unaccented_vietnamese(monkeypatch):
    unaccented = {
        "summary": "Ban dang co muc tieu tang can va can an du chat dinh duong.",
        "food_options": [
            {
                "title": "Thuc don com va mon man",
                "detail": "Chon mon an phu hop voi muc tieu.",
                "examples": [
                    {"meal_type": "breakfast", "food_id": "F_0332"},
                    {"meal_type": "breakfast", "food_id": "F_0333"},
                    {"meal_type": "lunch", "food_id": "F_0334"},
                    {"meal_type": "lunch", "food_id": "F_0335"},
                    {"meal_type": "dinner", "food_id": "F_0336"},
                    {"meal_type": "dinner", "food_id": "F_0337"},
                ],
            },
            {
                "title": "Thuc don chia nho",
                "detail": "Chia bua an trong ngay de dap ung nang luong.",
                "examples": [
                    {"meal_type": "breakfast", "food_id": "F_0335"},
                    {"meal_type": "breakfast", "food_id": "F_0336"},
                    {"meal_type": "lunch", "food_id": "F_0337"},
                    {"meal_type": "lunch", "food_id": "F_0338"},
                    {"meal_type": "dinner", "food_id": "F_0339"},
                    {"meal_type": "dinner", "food_id": "F_0340"},
                ],
            },
        ],
        "ppl_note": "Phu hop de tap luyen nhieu buoi trong tuan.",
        "ul_note": "Giup tap deu cac nhom co tren va duoi.",
    }
    accented = {
        "summary": "Bạn đang có mục tiêu tăng cân và cần ăn đủ chất dinh dưỡng.",
        "food_options": [
            {
                "title": "Thực đơn cơm và món mặn",
                "detail": "Chọn món ăn phù hợp với mục tiêu.",
                "examples": [
                    {"meal_type": "breakfast", "food_id": "F_0332"},
                    {"meal_type": "breakfast", "food_id": "F_0333"},
                    {"meal_type": "lunch", "food_id": "F_0334"},
                    {"meal_type": "lunch", "food_id": "F_0335"},
                    {"meal_type": "dinner", "food_id": "F_0336"},
                    {"meal_type": "dinner", "food_id": "F_0337"},
                ],
            },
            {
                "title": "Thực đơn chia nhỏ",
                "detail": "Chia bữa ăn trong ngày để đáp ứng năng lượng.",
                "examples": [
                    {"meal_type": "breakfast", "food_id": "F_0335"},
                    {"meal_type": "breakfast", "food_id": "F_0336"},
                    {"meal_type": "lunch", "food_id": "F_0337"},
                    {"meal_type": "lunch", "food_id": "F_0338"},
                    {"meal_type": "dinner", "food_id": "F_0339"},
                    {"meal_type": "dinner", "food_id": "F_0340"},
                ],
            },
        ],
        "ppl_note": "Phù hợp để tập luyện nhiều buổi trong tuần.",
        "ul_note": "Giúp tập đều các nhóm cơ trên và dưới.",
    }
    models = FakeModels([unaccented, accented])
    monkeypatch.setattr(ai, "client", lambda: SimpleNamespace(models=models))
    profile = SimpleNamespace(
        age=22, height_cm=170, weight_kg=60, sex="male", activity_level="moderate", avoid_tags=[]
    )

    result = ai.generate_profile_guidance(profile, 65, ["PPL", "Upper/Lower"])

    assert result == accented
    assert len(models.calls) == 2
    assert "đầy đủ dấu tiếng Việt" in models.calls[1]["contents"]
