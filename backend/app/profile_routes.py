"""Xem thử mục tiêu và lựa chọn gợi ý cá nhân, chỉ lưu sau thao tác xác nhận."""

import logging
import os
from datetime import datetime, timezone
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from . import ai
from .core import find_avoid_matches
from .db import get_db
from .goals import daily_targets
from .guidance_service import build_food_checklist, scaled_food_examples
from .models import AiRun, Food, WorkoutSelection
from .profile_service import (
    GOAL_ANALYSIS_VERSION,
    guidance_record,
    local_today,
    preview_targets,
    profile_data,
    profile_record,
)
from .schemas import GuidanceChoiceIn, ProfileIn
from .workout_plans import PLANS
from .workout_routes import selection_record

router = APIRouter(prefix="/api/profile", tags=["Mục tiêu cá nhân"])
logger = logging.getLogger(__name__)


def signature(profile, guidance):
    return (
        profile.age,
        profile.height_cm,
        profile.weight_kg,
        profile.sex,
        profile.activity_level,
        profile.protein_mode,
        profile.goal,
        tuple(profile.avoid_tags or []),
        guidance.target_weight_kg,
        guidance.target_date,
    )


def normalize_options(generated, dishes, targets):
    if not isinstance(generated, dict) or any(
        not isinstance(generated.get(k), str) or not generated[k].strip()
        for k in ("summary", "ppl_note", "ul_note")
    ):
        raise ValueError("Thiếu nội dung gợi ý")
    options = generated.get("food_options")
    if not isinstance(options, list) or len(options) != 2:
        raise ValueError("Thiếu hai phương án")
    lookup = {food.id: food for food in dishes}
    result = []
    for n, option in enumerate(options, 1):
        if not isinstance(option, dict) or any(
            not isinstance(option.get(k), str) or not option[k].strip() for k in ("title", "detail")
        ):
            raise ValueError("Phương án không hợp lệ")
        examples = option.get("examples")
        if (
            not isinstance(examples, list)
            or not 3 <= len(examples) <= 6
            or any(
                not isinstance(e, dict)
                or not isinstance(e.get("food_id"), str)
                or e["food_id"] not in lookup
                for e in examples
            )
        ):
            raise ValueError("Món nằm ngoài danh mục được phép")
        if {e.get("meal_type") for e in examples} != {"breakfast", "lunch", "dinner"} or len(
            {e["food_id"] for e in examples}
        ) != len(examples):
            raise ValueError("Cần đủ ba bữa và không lặp món")
        meals, totals = scaled_food_examples(examples, lookup, targets["kcal"])
        if abs(totals["kcal"] - targets["kcal"]) > targets["kcal"] * 0.15:
            raise ValueError("Khẩu phần gợi ý chưa gần mục tiêu năng lượng")
        result.append(
            {
                "id": f"food_{n}",
                "title": option["title"][:100],
                "detail": option["detail"][:500],
                "examples": meals,
                "estimated_totals": totals,
            }
        )
    return result


@router.post("/preview")
def preview(payload: ProfileIn, db: Session = Depends(get_db)):
    try:
        return {"daily_targets": preview_targets(payload, local_today())}
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/analyze")
async def analyze(db: Session = Depends(get_db)):
    uid = db.info["user_id"]
    profile, guidance = profile_record(db), guidance_record(db)
    targets = daily_targets(profile, guidance, local_today()) if profile and guidance else None
    if not targets:
        raise HTTPException(
            422, "Hãy lưu đủ hồ sơ và thời hạn để tính mục tiêu trước khi nhận gợi ý"
        )
    original = signature(profile, guidance)
    plans = [
        p for p in PLANS if p["goal"] == (profile.goal if profile.goal != "maintain" else "gain")
    ]
    dishes = [
        food
        for food in db.scalars(
            select(Food).where(Food.owner_id.is_(None), Food.catalog_kind == "dish")
        ).all()
        if not find_avoid_matches(
            profile.avoid_tags, [food.display_name or food.name] + (food.avoid_tags or [])
        )
    ]
    catalog = [
        {
            "food_id": f.id,
            "name": f.display_name or f.name,
            "portion": f.basis_label,
            "kcal": f.kcal_100g,
            "protein_g": f.protein_100g,
            "carb_g": f.carb_100g,
            "fat_g": f.fat_100g,
        }
        for f in dishes
    ]
    started, status = perf_counter(), "error"
    try:
        generated = await run_in_threadpool(
            ai.generate_profile_guidance,
            profile,
            guidance.target_weight_kg,
            [p["name"] for p in plans],
            targets,
            catalog,
        )
        options = normalize_options(generated, dishes, targets)
        analysis = {
            "target_version": GOAL_ANALYSIS_VERSION,
            "summary": generated["summary"][:700],
            "food_options": options,
            "workout_options": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "detail": generated["ppl_note" if p["method"] == "PPL" else "ul_note"][:500],
                }
                for p in plans
            ],
            "model": os.getenv("GEMINI_MODEL", ai.DEFAULT_MODEL),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        # Không ghi kết quả theo hồ sơ cũ nếu người dùng thay mục tiêu khi AI đang chạy.
        db.rollback()
        profile, guidance = profile_record(db), guidance_record(db)
        if not profile or not guidance or signature(profile, guidance) != original:
            status = "profile_changed"
            raise HTTPException(409, "Hồ sơ đã thay đổi. Hãy tạo lại gợi ý cho mục tiêu mới")
        guidance.analysis = analysis
        guidance.food_choice = guidance.food_checklist = guidance.workout_choice = None
        db.commit()
        status = "ok"
    except HTTPException:
        raise
    except (ai.AIConfigurationError, ai.AIResponseError, ai.AIServiceError) as exc:
        db.rollback()
        raise HTTPException(503, str(exc)) from None
    except Exception as exc:
        db.rollback()
        logger.warning("profile guidance error_type=%s", type(exc).__name__)
        raise HTTPException(
            503, "Chưa tạo được gợi ý phù hợp. Hãy thử lại sau; mục tiêu đã lưu vẫn được giữ"
        ) from None
    finally:
        db.add(
            AiRun(
                user_id=uid,
                purpose="profile",
                prompt_version=ai.GUIDANCE_PROMPT_VERSION,
                model_id=os.getenv("GEMINI_MODEL", ai.DEFAULT_MODEL),
                latency_ms=round((perf_counter() - started) * 1000),
                status=status,
            )
        )
        db.commit()
    return profile_data(profile, guidance)


@router.post("/choice")
def choose(payload: GuidanceChoiceIn, db: Session = Depends(get_db)):
    profile, guidance = profile_record(db), guidance_record(db)
    if (
        not profile
        or not guidance
        or not guidance.analysis
        or guidance.analysis.get("target_version") != GOAL_ANALYSIS_VERSION
        or not daily_targets(profile, guidance, local_today())
    ):
        raise HTTPException(409, "Hãy tạo gợi ý cho mục tiêu hiện tại trước")
    if not payload.food_choice and not payload.workout_choice:
        raise HTTPException(422, "Hãy chọn một phương án")
    food = None
    if payload.food_choice:
        food = next(
            (f for f in guidance.analysis["food_options"] if f["id"] == payload.food_choice), None
        )
        if not food:
            raise HTTPException(422, "Phương án ăn uống không hợp lệ")
    if payload.workout_choice and payload.workout_choice not in {
        p["id"] for p in guidance.analysis["workout_options"]
    }:
        raise HTTPException(422, "Giáo án không hợp lệ")
    if food:
        if guidance.food_choice != payload.food_choice or not guidance.food_checklist:
            guidance.food_checklist = build_food_checklist(food, local_today())
        guidance.food_choice = payload.food_choice
    if payload.workout_choice:
        selection = selection_record(db)
        if not selection:
            selection = WorkoutSelection(user_id=db.info["user_id"], plan_id=payload.workout_choice)
            db.add(selection)
        selection.plan_id = payload.workout_choice
        guidance.workout_choice = payload.workout_choice
    db.commit()
    return profile_data(profile, guidance)
