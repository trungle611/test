"""Dựng checklist và tính khẩu phần, độc lập với HTTP và database."""

from .core import is_discrete_unit, nutrition


def build_food_checklist(option, today):
    items = []
    for index, example in enumerate(option.get("examples", []), start=1):
        if not isinstance(example, dict) or not example.get("food_id"):
            continue
        items.append(
            {
                "id": f"{option['id']}_{index}",
                "text": example["name"][:240],
                "food_id": example["food_id"],
                "meal_type": example["meal_type"],
                "amount": example["default_amount"],
                "unit": example["unit"],
                "basis_label": example["basis_label"],
                "completed": False,
                "log_id": None,
            }
        )
    return {"date": today.isoformat(), "items": items}


def scaled_food_examples(examples, food_lookup, target_kcal):
    """Chọn 1–6 khẩu phần mỗi món sao cho tổng kcal gần mục tiêu nhất."""
    foods = [food_lookup[item["food_id"]] for item in examples]
    if any(food.kcal_100g <= 0 for food in foods):
        raise ValueError("Danh mục món không đủ số liệu kcal")
    states = {0: []}
    for food in foods:
        next_states = {}
        for total, quantities in states.items():
            for quantity in range(1, 7):
                candidate = round(total + food.kcal_100g * quantity, 1)
                if candidate <= target_kcal * 1.75:
                    next_states.setdefault(candidate, quantities + [quantity])
        states = next_states
    if not states:
        raise ValueError("Không tìm được tổ hợp khẩu phần phù hợp")
    _, quantities = min(states.items(), key=lambda state: abs(state[0] - target_kcal))
    result = []
    totals = {key: 0.0 for key in ("kcal", "protein", "carb", "fat")}
    for item, quantity in zip(examples, quantities):
        food = food_lookup[item["food_id"]]
        amount = food.basis_amount * quantity
        amount = round(amount) if is_discrete_unit(food.basis_unit) else round(amount, 2)
        if amount <= 0 or amount > 2000:
            raise ValueError("Định lượng gợi ý nằm ngoài giới hạn")
        for key, value in nutrition(food, amount).items():
            totals[key] += value
        result.append(
            {
                "meal_type": item["meal_type"],
                "food_id": food.id,
                "name": food.display_name or food.name,
                "default_amount": amount,
                "unit": food.basis_unit,
                "basis_label": food.basis_label,
            }
        )
    return result, {key: round(value, 1) for key, value in totals.items()}
