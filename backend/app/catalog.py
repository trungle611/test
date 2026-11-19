"""Nạp danh mục thực phẩm và món ăn do nhóm cung cấp từ CSV."""

import csv
from pathlib import Path

from .db import SessionLocal
from .models import Food, FoodAlias

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
FOODS_CSV = DATA_DIR / "foods_team_unverified.csv"
SERVING_ITEMS_CSV = DATA_DIR / "serving_items_team_unverified.csv"
_loaded = False


def _number(row, field, *, maximum=None):
    try:
        value = float(row[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{row.get('id', '?')}: {field} không hợp lệ") from exc
    if value < 0 or (maximum is not None and value > maximum):
        raise ValueError(f"{row.get('id', '?')}: {field} ngoài giới hạn")
    return value


def _aliases(value):
    return [item.strip() for item in (value or "").split(";") if item.strip()]


def _common(row):
    source_reference = row.get("source_reference", "").strip()
    if not source_reference:
        raise ValueError(f"{row.get('id', '?')}: thiếu nguồn dữ liệu")
    return {
        "source_type": row.get("source_type", "team_csv").strip() or "team_csv",
        "source_reference": source_reference,
        "data_version": row.get("data_version", "team-v1").strip() or "team-v1",
        "is_verified": row.get("is_verified", "false").strip().lower() == "true",
        "avoid_tags": _aliases(row.get("avoid_tags", "")),
    }


def _food_values(row):
    return {
        "id": row["id"].strip(),
        "name": row["name"].strip(),
        "display_name": None,
        "kcal_100g": _number(row, "kcal_100g", maximum=900),
        "protein_100g": _number(row, "protein_100g", maximum=100),
        "carb_100g": _number(row, "carb_100g", maximum=100),
        "fat_100g": _number(row, "fat_100g", maximum=100),
        "reference_mass_g": 100,
        "basis_amount": 100,
        "basis_unit": "g",
        "basis_label": "100 g",
        "catalog_kind": "food",
        **_common(row),
    }


def _serving_values(row):
    item_id = row["id"].strip()
    display_name = row["name"].strip()
    basis_amount = _number(row, "basis_amount")
    basis_unit = row["basis_unit"].strip()
    if not display_name or not basis_unit or basis_amount <= 0:
        raise ValueError(f"{item_id}: thiếu tên hoặc đơn vị khẩu phần")
    reference_mass = row.get("reference_mass_g", "").strip()
    return {
        "id": item_id,
        # Tên nội bộ có ID để không vi phạm unique khi món trùng tên một thực phẩm.
        "name": f"{display_name} [{item_id}]",
        "display_name": display_name,
        "kcal_100g": _number(row, "kcal_basis", maximum=3000),
        "protein_100g": _number(row, "protein_basis", maximum=300),
        "carb_100g": _number(row, "carb_basis", maximum=500),
        "fat_100g": _number(row, "fat_basis", maximum=300),
        "reference_mass_g": float(reference_mass) if reference_mass else 0,
        "basis_amount": basis_amount,
        "basis_unit": basis_unit,
        "basis_label": row["basis_label"].strip(),
        "catalog_kind": row["item_type"].strip(),
        **_common(row),
    }


def _read(path, converter):
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as file:
        return [(converter(row), _aliases(row.get("aliases", ""))) for row in csv.DictReader(file)]


def load_catalog(force=False):
    """Nạp hoặc cập nhật catalog hệ thống; không chạm vào món riêng của người dùng."""
    global _loaded
    if _loaded and not force:
        return 0
    rows = _read(FOODS_CSV, _food_values) + _read(SERVING_ITEMS_CSV, _serving_values)
    with SessionLocal() as db:
        for values, aliases in rows:
            food = db.get(Food, values["id"])
            if food and food.owner_id is not None:
                raise ValueError(f"{values['id']}: trùng ID món riêng của người dùng")
            if food is None:
                food = Food(**values, owner_id=None)
                db.add(food)
            else:
                for field, value in values.items():
                    if field != "id":
                        setattr(food, field, value)
                food.owner_id = None
                food.aliases.clear()
            food.aliases.extend(FoodAlias(alias=alias) for alias in aliases)
        db.commit()
    _loaded = True
    return len(rows)
