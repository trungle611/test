import pytest

from app.scan_service import build_dishes


@pytest.mark.parametrize(
    "values",
    [
        {"kcal": 185, "protein": 15, "carb": 5, "fat": 12},
        {"kcal": 1.85, "protein": -0.1, "carb": 0.05, "fat": 0.12},
        {"kcal": 1.85, "protein": float("inf"), "carb": 0.05, "fat": 0.12},
        {"kcal": float("nan"), "protein": 0.15, "carb": 0.05, "fat": 0.12},
        {"kcal": 0, "protein": 0, "carb": 0, "fat": 0},
        {"kcal": True, "protein": 0.15, "carb": 0.05, "fat": 0.12},
        {"kcal": 1.85, "protein": "0.15", "carb": 0.05, "fat": 0.12},
        {"kcal": 10**400, "protein": 0.15, "carb": 0.05, "fat": 0.12},
    ],
)
def test_invalid_per_gram_estimate_is_not_used(values):
    result = build_dishes(
        {"dishes": [{"candidate_labels": ["Món chưa biết"], "estimated_nutrition_1g": values}]},
        [],
        lambda food: food,
    )
    assert result[0]["estimated_nutrition_1g"] is None
    assert result[0]["estimated_nutrition_100g"] is None


def test_small_per_gram_macros_are_preserved():
    values = {"kcal": 0.375, "protein": 0.00123, "carb": 0.05, "fat": 0.01}
    dish = build_dishes(
        {"dishes": [{"candidate_labels": ["Món mới"], "estimated_nutrition_1g": values}]},
        [],
        lambda food: food,
    )[0]
    assert dish["estimated_nutrition_1g"] == values
    assert dish["estimated_nutrition_100g"]["protein"] == 0.123
