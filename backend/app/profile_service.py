"""Hồ sơ và mục tiêu dinh dưỡng dùng chung cho các API."""

from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from sqlalchemy import select

from .goals import daily_targets
from .guidance_service import build_food_checklist
from .models import Profile, ProfileGuidance

GOAL_ANALYSIS_VERSION = "macro-targets-v3-kcal-fit"


def local_today():
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()


def current_user_id(db):
    return db.info["user_id"]


def profile_record(db):
    return db.scalar(select(Profile).where(Profile.user_id == current_user_id(db)))


def guidance_record(db):
    return db.scalar(select(ProfileGuidance).where(ProfileGuidance.user_id == current_user_id(db)))


def food_checklist_for(guidance, today=None):
    """Trả checklist đã lưu hoặc dựng lại cho lựa chọn được tạo trước tính năng này."""
    today = today or local_today()
    if not guidance:
        return {"date": None, "items": []}
    if guidance.food_checklist:
        return guidance.food_checklist
    options = (guidance.analysis or {}).get("food_options", [])
    selected = next((item for item in options if item.get("id") == guidance.food_choice), None)
    return build_food_checklist(selected or {"id": guidance.food_choice}, today)


def profile_data(profile, guidance=None, today=None):
    today = today or local_today()
    analysis = (
        guidance.analysis
        if guidance
        and guidance.analysis
        and guidance.analysis.get("target_version") == GOAL_ANALYSIS_VERSION
        else None
    )
    checklist = food_checklist_for(guidance, today)
    checklist_items = [
        {
            **item,
            "completed": item.get("completed", False)
            if checklist.get("date") == today.isoformat()
            else False,
            "log_id": item.get("log_id") if checklist.get("date") == today.isoformat() else None,
        }
        for item in checklist.get("items", [])
    ]
    return {
        "age": profile.age,
        "height_cm": profile.height_cm,
        "weight_kg": profile.weight_kg,
        "sex": profile.sex,
        "activity_level": profile.activity_level,
        "protein_mode": profile.protein_mode or "balanced",
        "goal": profile.goal,
        "avoid_tags": profile.avoid_tags or [],
        "target_kcal": profile.target_kcal,
        "target_weight_kg": guidance.target_weight_kg if guidance else None,
        "target_date": guidance.target_date if guidance else None,
        "daily_targets": daily_targets(profile, guidance, today),
        "analysis": analysis,
        "food_choice": guidance.food_choice if analysis else None,
        "food_checklist": checklist_items if analysis else [],
        "workout_choice": guidance.workout_choice if analysis else None,
    }


def validate_profile(payload, today):
    if payload.target_date and payload.target_date <= today:
        raise ValueError("Ngày hoàn thành mục tiêu phải sau hôm nay")
    if payload.weight_kg is not None and payload.target_weight_kg is not None:
        difference = payload.target_weight_kg - payload.weight_kg
        expected = "gain" if difference > 0.1 else "lose" if difference < -0.1 else "maintain"
        if payload.goal != expected:
            labels = {"gain": "Tăng cân", "lose": "Giảm cân", "maintain": "Duy trì"}
            raise ValueError(
                f"Cân nặng mong muốn phù hợp với mục tiêu {labels[expected]}. Hãy chọn lại mục tiêu"
            )


def preview_targets(payload, today):
    validate_profile(payload, today)
    profile = SimpleNamespace(**payload.model_dump())
    guidance = SimpleNamespace(
        target_weight_kg=payload.target_weight_kg,
        target_date=payload.target_date.isoformat() if payload.target_date else None,
    )
    targets = daily_targets(profile, guidance, today)
    if not targets:
        raise ValueError(
            "Hãy điền đủ tuổi, chiều cao, cân nặng, mục tiêu, thời hạn, thông số sinh học và mức vận động"
        )
    return targets
