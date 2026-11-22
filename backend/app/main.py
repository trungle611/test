import hashlib
import json
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from time import perf_counter
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from starlette.concurrency import run_in_threadpool

from . import ai
from .auth_routes import router as auth_router
from .core import (
    normalize,
    nutrition,
    validate_quantity,
)
from .db import get_db, initialize_database
from .goals import assess_daily_intake, daily_targets
from .guidance_service import build_food_checklist
from .models import (
    AiRun,
    BatchSubmission,
    DailyNutritionGoal,
    Food,
    FoodLog,
    Profile,
    ProfileGuidance,
    ScanHistory,
)
from .scan_service import (
    MAX_IMAGE_BYTES,
    build_dishes,
    save_thumbnail,
    stored_image_path,
    validate_image,
)
from .schemas import (
    BatchLogIn,
    ChecklistToggleIn,
    LogIn,
    LogUpdate,
    ProfileIn,
)

LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")


GOAL_ANALYSIS_VERSION = "macro-targets-v3-kcal-fit"


MEAL_TYPES = {"breakfast", "lunch", "dinner", "snack"}


logger = logging.getLogger(__name__)


def local_today():
    return datetime.now(LOCAL_TZ).date()


def local_date(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(LOCAL_TZ).date()


def utc_timestamp(value):
    """SQLite trả datetime không kèm timezone; timestamp lưu trong DB là UTC."""
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


@asynccontextmanager
async def lifespan(app):
    initialize_database()
    yield


app = FastAPI(title="HBTNFIT API", version="0.1.0", lifespan=lifespan)
app.include_router(auth_router)


LOCAL_ORIGINS = [
    f"http://{host}:{port}" for host in ("localhost", "127.0.0.1") for port in (5173, 5174, 5175)
]


PUBLIC_ORIGINS = [
    origin.strip() for origin in os.getenv("FRONTEND_ORIGINS", "").split(",") if origin.strip()
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=LOCAL_ORIGINS + PUBLIC_ORIGINS,
    allow_origin_regex=r"https://[a-z0-9-]+\.vercel\.app"
    if os.getenv("ALLOW_VERCEL_PREVIEWS") == "1"
    else None,
    allow_methods=["*"],
    allow_headers=["*"],
)


def current_user_id(db):
    return db.info["user_id"]


def scoped_key(db, value):
    return hashlib.sha1(f"{current_user_id(db)}:{value}".encode()).hexdigest()


def visible_food(food, db):
    return food is not None and (food.owner_id is None or food.owner_id == current_user_id(db))


def accessible_foods(db, include_aliases=False):
    query = select(Food).where((Food.owner_id.is_(None)) | (Food.owner_id == current_user_id(db)))
    if include_aliases:
        query = query.options(selectinload(Food.aliases))
    return db.scalars(query).all()


def profile_record(db):
    return db.scalar(select(Profile).where(Profile.user_id == current_user_id(db)))


def guidance_record(db):
    return db.scalar(select(ProfileGuidance).where(ProfileGuidance.user_id == current_user_id(db)))


def save_today_nutrition_goal(db, profile=None, guidance=None):
    profile = profile if profile is not None else profile_record(db)
    guidance = guidance if guidance is not None else guidance_record(db)
    targets = daily_targets(profile, guidance, local_today()) if profile else None
    day = local_today().isoformat()
    key = scoped_key(db, f"nutrition-goal:{day}")
    snapshot = db.get(DailyNutritionGoal, key)
    if targets:
        values = {**targets, "goal": profile.goal, "target_weight_kg": guidance.target_weight_kg}
        if snapshot:
            snapshot.targets = values
        else:
            db.add(DailyNutritionGoal(id=key, user_id=current_user_id(db), day=day, targets=values))
    elif snapshot:
        db.delete(snapshot)


def food_data(food):
    return {
        "id": food.id,
        "name": food.display_name or food.name,
        "kcal_100g": food.kcal_100g,
        "protein_100g": food.protein_100g,
        "carb_100g": food.carb_100g,
        "fat_100g": food.fat_100g,
        "source_type": food.source_type,
        "source_reference": food.source_reference,
        "reference_mass_g": food.reference_mass_g,
        "basis_amount": food.basis_amount,
        "basis_unit": food.basis_unit,
        "basis_label": food.basis_label,
        "catalog_kind": food.catalog_kind,
        "data_version": food.data_version,
        "is_verified": food.is_verified,
        "avoid_tags": food.avoid_tags or [],
        "aliases": [a.alias for a in food.aliases],
    }


def scan_history_data(record):
    return {
        "id": record.id,
        "meal_type": record.meal_type,
        "status": record.status,
        "dishes": record.result.get("dishes", []),
        "created_at": utc_timestamp(record.created_at),
        "confirmed_at": utc_timestamp(record.confirmed_at),
        "image_url": f"/api/scan-history/{record.id}/image",
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "application": "HBTNFIT",
        "stage": "food",
        "ai_configured": bool(os.getenv("GEMINI_API_KEY")),
    }


def food_checklist_for(guidance):
    """Trả checklist đã lưu hoặc dựng lại cho lựa chọn được tạo trước tính năng này."""
    if not guidance:
        return {"date": None, "items": []}
    if guidance.food_checklist:
        return guidance.food_checklist
    options = (guidance.analysis or {}).get("food_options", [])
    selected = next((item for item in options if item.get("id") == guidance.food_choice), None)
    return build_food_checklist(selected or {"id": guidance.food_choice}, local_today())


def sync_checklist_log(db, log, deleted=False):
    """Đồng bộ checklist khi sửa hoặc xóa món đã tick trong thực đơn."""
    guidance = guidance_record(db)
    if not guidance or not guidance.food_checklist:
        return
    checklist = guidance.food_checklist
    items = []
    for original in checklist.get("items", []):
        item = dict(original)
        if item.get("log_id") == log.id:
            if deleted:
                item.update(completed=False, log_id=None)
            else:
                item.update(amount=log.grams, meal_type=log.meal_type)
        items.append(item)
    guidance.food_checklist = {**checklist, "items": items}


def profile_data(profile, guidance=None):
    analysis = (
        guidance.analysis
        if guidance
        and guidance.analysis
        and guidance.analysis.get("target_version") == GOAL_ANALYSIS_VERSION
        else None
    )
    checklist = food_checklist_for(guidance)
    checklist_items = [
        {
            **item,
            "completed": item.get("completed", False)
            if checklist.get("date") == local_today().isoformat()
            else False,
            "log_id": item.get("log_id")
            if checklist.get("date") == local_today().isoformat()
            else None,
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
        "daily_targets": daily_targets(profile, guidance, local_today()),
        "analysis": analysis,
        "food_choice": guidance.food_choice if analysis else None,
        "food_checklist": checklist_items if analysis else [],
        "workout_choice": guidance.workout_choice if analysis else None,
    }


@app.get("/api/profile")
def get_profile(db: Session = Depends(get_db)):
    profile = profile_record(db)
    return (
        profile_data(profile, guidance_record(db))
        if profile
        else ProfileIn().model_dump(mode="json")
        | {
            "daily_targets": None,
            "analysis": None,
            "food_choice": None,
            "food_checklist": [],
            "workout_choice": None,
        }
    )


@app.put("/api/profile")
def save_profile(payload: ProfileIn, db: Session = Depends(get_db)):
    if payload.target_date and payload.target_date <= local_today():
        raise HTTPException(422, "Ngày hoàn thành mục tiêu phải sau hôm nay")
    if payload.weight_kg is not None and payload.target_weight_kg is not None:
        difference = payload.target_weight_kg - payload.weight_kg
        expected_goal = "gain" if difference > 0.1 else "lose" if difference < -0.1 else "maintain"
        if payload.goal != expected_goal:
            labels = {"gain": "Tăng cân", "lose": "Giảm cân", "maintain": "Duy trì"}
            raise HTTPException(
                422,
                f"Cân nặng mong muốn phù hợp với mục tiêu {labels[expected_goal]}. Hãy chọn lại mục tiêu",
            )
    profile = profile_record(db) or Profile(user_id=current_user_id(db))
    guidance = guidance_record(db) or ProfileGuidance(user_id=current_user_id(db))
    if (
        profile.weight_kg != payload.weight_kg
        or guidance.target_weight_kg != payload.target_weight_kg
        or guidance.target_date
        != (payload.target_date.isoformat() if payload.target_date else None)
        or profile.avoid_tags != payload.avoid_tags
        or profile.age != payload.age
        or profile.height_cm != payload.height_cm
        or profile.goal != payload.goal
        or profile.sex != payload.sex
        or profile.activity_level != payload.activity_level
        or (profile.protein_mode or "balanced") != payload.protein_mode
        or (guidance.analysis and guidance.analysis.get("target_version") != GOAL_ANALYSIS_VERSION)
    ):
        guidance.analysis = None
        guidance.food_choice = None
        guidance.food_checklist = None
        guidance.workout_choice = None
    guidance.target_weight_kg = payload.target_weight_kg
    guidance.target_date = payload.target_date.isoformat() if payload.target_date else None
    for key, value in payload.model_dump(exclude={"target_weight_kg", "target_date"}).items():
        setattr(profile, key, value)
    db.add(profile)
    db.add(guidance)
    save_today_nutrition_goal(db, profile, guidance)
    db.commit()
    return profile_data(profile, guidance)


@app.patch("/api/profile/food-checklist/{item_id}")
def toggle_food_checklist(item_id: str, payload: ChecklistToggleIn, db: Session = Depends(get_db)):
    profile = profile_record(db)
    guidance = guidance_record(db)
    if not profile or not guidance or not guidance.analysis or not guidance.food_choice:
        raise HTTPException(409, "Hãy chọn phương án ăn uống trước")
    checklist = food_checklist_for(guidance)
    # Tạo object mới để SQLAlchemy nhận biết thay đổi trong cột JSON.
    items = [{**item} for item in checklist.get("items", [])]
    if checklist.get("date") != local_today().isoformat():
        items = [{**item, "completed": False, "log_id": None} for item in items]
    found = False
    for item in items:
        if item.get("id") == item_id:
            amount = payload.amount if payload.amount is not None else item.get("amount")
            if not isinstance(amount, (int, float)) or amount <= 0 or amount > 2000:
                raise HTTPException(422, "Định lượng phải lớn hơn 0 và không quá 2000 đơn vị")
            food = db.get(Food, item.get("food_id"))
            if not visible_food(food, db):
                raise HTTPException(404, "Món gợi ý không còn trong danh mục")
            try:
                validate_quantity(food, amount)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
            if payload.completed and not item.get("completed"):
                log = FoodLog(
                    food_id=food.id,
                    user_id=current_user_id(db),
                    grams=amount,
                    meal_type=item["meal_type"],
                    eaten_at=datetime.now(timezone.utc),
                )
                db.add(log)
                db.flush()
                item.update({"completed": True, "amount": amount, "log_id": log.id})
            elif not payload.completed and item.get("completed"):
                log = db.get(FoodLog, item.get("log_id")) if item.get("log_id") else None
                if log and log.user_id == current_user_id(db):
                    db.delete(log)
                item.update({"completed": False, "amount": amount, "log_id": None})
            found = True
            break
    if not found:
        raise HTTPException(404, "Không tìm thấy mục trong kế hoạch ăn uống")
    guidance.food_checklist = {"date": local_today().isoformat(), "items": items}
    save_today_nutrition_goal(db)
    db.commit()
    return profile_data(profile, guidance)


@app.get("/api/foods")
def foods(q: str = "", db: Session = Depends(get_db)):
    records = accessible_foods(db, include_aliases=True)
    if q:
        query = normalize(q)
        records = [
            f
            for f in records
            if any(
                query in normalize(n)
                for n in [f.display_name or f.name] + [a.alias for a in f.aliases]
            )
        ]
    return [food_data(f) for f in records[:500]]


@app.get("/api/foods/{food_id}")
def get_food(food_id: str, db: Session = Depends(get_db)):
    food = db.scalar(select(Food).where(Food.id == food_id).options(selectinload(Food.aliases)))
    if not visible_food(food, db):
        raise HTTPException(404, "Không tìm thấy món")
    return food_data(food)


@app.post("/api/scan")
async def scan(
    file: UploadFile = File(...), meal_type: str = Form("lunch"), db: Session = Depends(get_db)
):
    if meal_type not in MEAL_TYPES:
        raise HTTPException(422, "Bữa ăn không hợp lệ")
    request_id = str(uuid.uuid4())
    raw = await file.read(MAX_IMAGE_BYTES + 1)
    validate_image(raw, file.content_type)
    started = perf_counter()
    status = "ok"
    records = accessible_foods(db, include_aliases=True)
    scan_records = [
        food
        for food in records
        if food.catalog_kind in {"dish", "beverage"}
        or food.source_type in {"user_entered", "test_fixture", "demo_synthetic"}
    ]
    catalog = [
        {"food_id": food.id, "name": food.display_name or food.name, "portion": food.basis_label}
        for food in scan_records
        if food.owner_id is None and food.source_type == "team_csv"
    ]
    profile = profile_record(db)
    avoid_tags = profile.avoid_tags if profile else []
    try:
        result = await run_in_threadpool(ai.scan_image, raw, file.content_type, catalog, avoid_tags)
    except ai.AIConfigurationError as exc:
        status = "not_configured"
        raise HTTPException(503, str(exc))
    except ai.AIResponseError as exc:
        status = "invalid_response"
        raise HTTPException(503, str(exc))
    except ai.AIServiceError as exc:
        status = exc.reason
        logger.warning("scan request=%s reason=%s", request_id, status)
        raise HTTPException(503, str(exc)) from None
    except Exception as exc:
        status = "service_error"
        logger.warning("scan request=%s error_type=%s", request_id, type(exc).__name__)
        raise HTTPException(503, "Dịch vụ nhận diện tạm thời không khả dụng")
    finally:
        db.add(
            AiRun(
                user_id=current_user_id(db),
                purpose="scan",
                prompt_version=ai.SCAN_PROMPT_VERSION,
                model_id=os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"),
                latency_ms=round((perf_counter() - started) * 1000),
                status=status,
            )
        )
        db.commit()
    dishes = build_dishes(result, scan_records, food_data, avoid_tags)
    recognition_status = (
        "needs_confirmation"
        if any(
            d["candidates"] or (d["suggested_labels"] and d.get("estimated_nutrition_1g"))
            for d in dishes
        )
        else "unknown"
    )
    image_key = save_thumbnail(raw, request_id, current_user_id(db))
    history_dishes = [
        {
            "labels": dish["suggested_labels"],
            "confidence": dish.get("confidence", 0),
            "visible_ingredients": dish.get("visible_ingredients", []),
            "uncertainty_reason": dish.get("uncertainty_reason", ""),
            "avoid_matches": dish.get("avoid_matches", []),
        }
        for dish in dishes
    ]
    db.add(
        ScanHistory(
            id=request_id,
            user_id=current_user_id(db),
            image_key=image_key,
            meal_type=meal_type,
            status=recognition_status,
            result={"dishes": history_dishes},
        )
    )
    db.commit()
    return {
        "request_id": request_id,
        "status": recognition_status,
        "dishes": dishes,
        "warnings": [result["warning"]] if result.get("warning") else [],
        "prompt_version": ai.SCAN_PROMPT_VERSION,
    }


@app.get("/api/scan-history")
def get_scan_history(
    limit: int = Query(12, ge=1, le=50), offset: int = Query(0, ge=0), db: Session = Depends(get_db)
):
    records = db.scalars(
        select(ScanHistory)
        .where(ScanHistory.user_id == current_user_id(db), ScanHistory.confirmed_at.is_not(None))
        .order_by(ScanHistory.created_at.desc())
        .offset(offset)
        .limit(limit + 1)
    ).all()
    return {
        "items": [scan_history_data(record) for record in records[:limit]],
        "has_more": len(records) > limit,
    }


@app.get("/api/scan-history/{history_id}/image")
def get_scan_history_image(history_id: str, db: Session = Depends(get_db)):
    record = db.scalar(
        select(ScanHistory).where(
            ScanHistory.id == history_id,
            ScanHistory.user_id == current_user_id(db),
            ScanHistory.confirmed_at.is_not(None),
        )
    )
    if not record:
        raise HTTPException(404, "Không tìm thấy ảnh trong lịch sử")
    image_path = stored_image_path(record.image_key)
    if not image_path:
        raise HTTPException(404, "Ảnh lịch sử không còn tồn tại")
    return FileResponse(image_path, media_type="image/webp")


def log_response(log, food):
    return {
        "id": log.id,
        "food_id": food.id,
        "name": food.display_name or food.name,
        "grams": log.grams,
        "amount": log.grams,
        "unit": food.basis_unit,
        "basis_amount": food.basis_amount,
        "basis_label": food.basis_label,
        "meal_type": log.meal_type,
        "nutrition": nutrition(food, log.grams),
        "source_reference": food.source_reference,
        "is_verified": food.is_verified,
    }


@app.post("/api/food-logs/batch", status_code=201)
def add_logs_batch(payload: BatchLogIn, db: Session = Depends(get_db)):
    request_hash = hashlib.sha256(
        json.dumps(
            [item.model_dump(mode="json") for item in payload.items],
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    submission_key = scoped_key(db, payload.confirmation_id) if payload.confirmation_id else None
    if submission_key:
        prior = db.get(BatchSubmission, submission_key)
        if prior:
            logs = [db.get(FoodLog, log_id) for log_id in prior.log_ids]
            if prior.user_id not in {None, current_user_id(db)} or any(
                log and log.user_id != current_user_id(db) for log in logs
            ):
                raise HTTPException(404, "Không tìm thấy lần xác nhận")
            if prior.request_hash != request_hash:
                raise HTTPException(409, "Mã xác nhận đã dùng với nội dung khác")
            if prior.user_id is None:
                prior.user_id = current_user_id(db)
                db.commit()
            return {
                "entries": [
                    log_response(log, db.get(Food, log.food_id))
                    for log in logs
                    if log and log.user_id == current_user_id(db)
                ]
            }
    records = []
    history = None
    if payload.confirmation_id:
        existing_history = db.get(ScanHistory, payload.confirmation_id)
        if existing_history and existing_history.user_id != current_user_id(db):
            raise HTTPException(404, "Không tìm thấy ảnh nhận diện")
        history = db.scalar(
            select(ScanHistory).where(
                ScanHistory.id == payload.confirmation_id,
                ScanHistory.user_id == current_user_id(db),
            )
        )
        avoid_matches = sorted(
            {
                match
                for dish in (history.result.get("dishes", []) if history else [])
                for match in dish.get("avoid_matches", [])
            }
        )
        if avoid_matches and not payload.avoidance_acknowledged:
            raise HTTPException(
                422,
                "Món có thành phần cần tránh: "
                + ", ".join(avoid_matches)
                + ". Hãy kiểm tra và xác nhận cảnh báo trước khi lưu",
            )
    for item in payload.items:
        if not item.confirmed:
            raise HTTPException(422, "Cần xác nhận từng món và khẩu phần trước khi lưu")
        if bool(item.food_id) == bool(item.custom_food):
            raise HTTPException(422, "Chọn món trong danh mục hoặc nhập một món mới")
        food = db.get(Food, item.food_id) if item.food_id else None
        if item.food_id and not visible_food(food, db):
            raise HTTPException(404, f"Food ID không tồn tại: {item.food_id}")
        if food:
            try:
                validate_quantity(food, item.grams)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
        records.append((item, food))
    created = []
    for item, food in records:
        if item.custom_food:
            custom = item.custom_food
            name = custom.name.strip()
            if len(name) < 2:
                raise HTTPException(422, "Tên món phải có ít nhất 2 ký tự")
            normalized_name = normalize(name)
            catalog_food = next(
                (
                    candidate
                    for candidate in db.scalars(select(Food).where(Food.owner_id.is_(None))).all()
                    if candidate.basis_unit == "g"
                    and candidate.basis_amount == 100
                    and normalize(candidate.display_name or candidate.name) == normalized_name
                ),
                None,
            )
            if catalog_food:
                food = catalog_food
            else:
                food = db.scalar(
                    select(Food).where(
                        Food.owner_id == current_user_id(db), Food.display_name == name
                    )
                )
                if food and food.kcal_100g == 0 and custom.kcal_100g > 0:
                    food.kcal_100g = custom.kcal_100g
                    food.protein_100g = custom.protein_100g
                    food.carb_100g = custom.carb_100g
                    food.fat_100g = custom.fat_100g
                    food.source_reference = (
                        "Người dùng tự nhập/điều chỉnh ước tính; chưa kiểm chứng"
                    )
                if not food:
                    food = Food(
                        id=f"user-{uuid.uuid4().hex[:32]}",
                        name=f"{name[:130]} [{uuid.uuid4().hex[:12]}]",
                        display_name=name,
                        owner_id=current_user_id(db),
                        kcal_100g=custom.kcal_100g,
                        protein_100g=custom.protein_100g,
                        carb_100g=custom.carb_100g,
                        fat_100g=custom.fat_100g,
                        source_type="user_entered",
                        source_reference="Người dùng tự nhập; chưa kiểm chứng",
                        reference_mass_g=100,
                        basis_amount=100,
                        basis_unit="g",
                        basis_label="100 g",
                        catalog_kind="custom",
                        data_version="user-v1",
                        is_verified=False,
                        avoid_tags=[],
                    )
                    db.add(food)
                    db.flush()
        log = FoodLog(
            food_id=food.id,
            user_id=current_user_id(db),
            grams=item.grams,
            meal_type=item.meal_type,
            eaten_at=item.eaten_at or datetime.now(timezone.utc),
        )
        db.add(log)
        created.append((log, food))
    db.flush()
    if submission_key:
        db.add(
            BatchSubmission(
                confirmation_id=submission_key,
                user_id=current_user_id(db),
                request_hash=request_hash,
                log_ids=[log.id for log, _ in created],
            )
        )
    if history:
        history.confirmed_at = datetime.now(timezone.utc)
        history.meal_type = payload.items[0].meal_type
    save_today_nutrition_goal(db)
    db.commit()
    return {"entries": [log_response(log, food) for log, food in created]}


@app.post("/api/food-logs", status_code=201)
def add_log(payload: LogIn, db: Session = Depends(get_db)):
    if not payload.confirmed:
        raise HTTPException(422, "Cần xác nhận món và khẩu phần trước khi lưu")
    food = db.get(Food, payload.food_id)
    if not visible_food(food, db):
        raise HTTPException(404, "Food ID không tồn tại")
    try:
        validate_quantity(food, payload.grams)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    record = FoodLog(
        food_id=food.id,
        user_id=current_user_id(db),
        grams=payload.grams,
        meal_type=payload.meal_type,
        eaten_at=payload.eaten_at or datetime.now(timezone.utc),
    )
    db.add(record)
    save_today_nutrition_goal(db)
    db.commit()
    db.refresh(record)
    return log_response(record, food)


@app.patch("/api/food-logs/{log_id}")
def update_log(log_id: int, payload: LogUpdate, db: Session = Depends(get_db)):
    log = db.get(FoodLog, log_id)
    if not log or log.user_id != current_user_id(db):
        raise HTTPException(404, "Không tìm thấy món trong nhật ký")
    food = db.get(Food, log.food_id)
    try:
        validate_quantity(food, payload.grams)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    log.grams = payload.grams
    log.meal_type = payload.meal_type
    sync_checklist_log(db, log)
    db.commit()
    db.refresh(log)
    return log_response(log, food)


@app.delete("/api/food-logs/{log_id}", status_code=204)
def delete_log(log_id: int, db: Session = Depends(get_db)):
    log = db.get(FoodLog, log_id)
    if not log or log.user_id != current_user_id(db):
        raise HTTPException(404, "Không tìm thấy món trong nhật ký")
    sync_checklist_log(db, log, deleted=True)
    db.delete(log)
    db.commit()


@app.get("/api/dashboard")
def dashboard(day: date = Query(default_factory=local_today), db: Session = Depends(get_db)):
    logs = db.scalars(
        select(FoodLog)
        .where(FoodLog.user_id == current_user_id(db))
        .options(selectinload(FoodLog.food))
    ).all()
    entries = []
    totals = {key: 0.0 for key in ("kcal", "protein", "carb", "fat")}
    for log in logs:
        if local_date(log.eaten_at) != day:
            continue
        entry = log_response(log, log.food)
        values = entry["nutrition"]
        entries.append(entry)
        for key, value in values.items():
            totals[key] += value
    return {
        "date": day.isoformat(),
        "totals": {k: round(v, 1) for k, v in totals.items()},
        "entries": entries,
    }


@app.get("/api/food-history")
def food_history(days: int = Query(30, ge=1, le=180), db: Session = Depends(get_db)):
    """Tổng hợp nhật ký món đã ăn theo ngày trong khoảng gần đây."""
    cutoff = local_today() - timedelta(days=days - 1)
    snapshots = {
        row.day: row.targets
        for row in db.scalars(
            select(DailyNutritionGoal).where(
                DailyNutritionGoal.user_id == current_user_id(db),
                DailyNutritionGoal.day >= cutoff.isoformat(),
            )
        ).all()
    }
    profile = profile_record(db)
    guidance = guidance_record(db)
    current_targets = daily_targets(profile, guidance, local_today()) if profile else None
    logs = db.scalars(
        select(FoodLog)
        .where(FoodLog.user_id == current_user_id(db))
        .options(selectinload(FoodLog.food))
        .order_by(FoodLog.eaten_at.desc())
    ).all()
    grouped = {}
    for log in logs:
        eaten_day = local_date(log.eaten_at)
        if eaten_day < cutoff or eaten_day > local_today():
            continue
        entry = log_response(log, log.food)
        day_data = grouped.setdefault(
            eaten_day.isoformat(),
            {
                "date": eaten_day.isoformat(),
                "totals": {key: 0.0 for key in ("kcal", "protein", "carb", "fat")},
                "entries": [],
            },
        )
        day_data["entries"].append(entry)
        for key, value in entry["nutrition"].items():
            day_data["totals"][key] += value
    result = []
    for day_data in sorted(grouped.values(), key=lambda item: item["date"], reverse=True):
        day_data["totals"] = {key: round(value, 1) for key, value in day_data["totals"].items()}
        day_data["is_today"] = day_data["date"] == local_today().isoformat()
        targets = snapshots.get(day_data["date"])
        if not targets and day_data["is_today"]:
            targets = (
                {
                    **current_targets,
                    "goal": profile.goal,
                    "target_weight_kg": guidance.target_weight_kg,
                }
                if current_targets
                else None
            )
        day_data["targets"] = targets
        day_data["assessment"] = assess_daily_intake(
            day_data["totals"],
            targets,
            any(entry["nutrition"]["kcal"] <= 0 for entry in day_data["entries"]),
        )
        result.append(day_data)
    return {"period_days": days, "days": result}
