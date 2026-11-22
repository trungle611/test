"""Giáo án theo tiến độ và lịch đi tập, luôn giới hạn theo tài khoản đăng nhập."""

import calendar
import hashlib
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import WorkoutProgress, WorkoutSelection, WorkoutVisit
from .schemas import AttendanceIn, WorkoutSelectIn
from .workout_plans import PLANS, public_plan, session_items

router = APIRouter(prefix="/api/workouts", tags=["Tập luyện"])


def local_today():
    return datetime.now(ZoneInfo("Asia/Ho_Chi_Minh")).date()


def owned_key(db, value):
    # Giữ khóa nội bộ có namespace để tương thích unique constraint của DB demo cũ.
    return hashlib.sha1(f"{db.info['user_id']}:{value}".encode()).hexdigest()


def selection_record(db):
    return db.scalar(select(WorkoutSelection).where(WorkoutSelection.user_id == db.info["user_id"]))


def visits_for(db, plan_id):
    return db.scalars(
        select(WorkoutVisit).where(
            WorkoutVisit.user_id == db.info["user_id"],
            WorkoutVisit.plan_id == owned_key(db, plan_id),
        )
    ).all()


def progress_key(db, plan_id, ordinal, exercise_id):
    # Một chu kỳ mới không được dùng lại trạng thái hoàn thành của chu kỳ trước.
    return owned_key(db, f"workout:{plan_id}:{ordinal}:{exercise_id}")


def workout_data(db):
    day = local_today().isoformat()
    selection = selection_record(db)
    plan = next((p for p in PLANS if selection and p["id"] == selection.plan_id), None)
    if not plan:
        return {
            "date": day,
            "selected_plan": None,
            "session_name": None,
            "session_number": None,
            "attendance": None,
            "items": [],
            "completed_sessions": 0,
            "session_ordinal": 0,
        }
    visits = visits_for(db, plan["id"])
    today_visit = next((v for v in visits if v.day == day), None)
    completed = sum(v.status == "completed" and v.day <= day for v in visits)
    ordinal = today_visit.session_index if today_visit else completed
    index = ordinal % len(plan["sessions"])
    items = session_items(plan, index)
    keys = [progress_key(db, plan["id"], ordinal, item["id"]) for item in items]
    progress = {
        row.workout_id: row
        for row in db.scalars(
            select(WorkoutProgress).where(
                WorkoutProgress.user_id == db.info["user_id"],
                WorkoutProgress.workout_id.in_(keys),
            )
        ).all()
    }
    return {
        "date": day,
        "selected_plan": public_plan(plan),
        "session_name": plan["schedule"][index],
        "session_number": index + 1,
        "session_ordinal": ordinal,
        "completed_sessions": completed,
        "attendance": today_visit.status if today_visit else None,
        "items": [
            {**item, "status": progress[key].status if key in progress else "not_started"}
            for item, key in zip(items, keys)
        ],
    }


@router.get("/plans")
def plans(db: Session = Depends(get_db)):
    return [public_plan(plan) for plan in PLANS]


@router.post("/select")
def select_plan(payload: WorkoutSelectIn, db: Session = Depends(get_db)):
    if payload.plan_id not in {p["id"] for p in PLANS}:
        raise HTTPException(404, "Không tìm thấy giáo án")
    selection = selection_record(db)
    if not selection:
        selection = WorkoutSelection(user_id=db.info["user_id"], plan_id=payload.plan_id)
        db.add(selection)
    else:
        selection.plan_id = payload.plan_id
    db.commit()
    return workout_data(db)


@router.get("/today")
def today(db: Session = Depends(get_db)):
    return workout_data(db)


@router.get("/attendance")
def attendance(
    month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), db: Session = Depends(get_db)
):
    try:
        first = date.fromisoformat(f"{month}-01")
    except ValueError:
        raise HTTPException(422, "Tháng không hợp lệ") from None
    count = calendar.monthrange(first.year, first.month)[1]
    # Lịch tổng hợp mọi giáo án của tài khoản, không biến mất khi đổi giáo án.
    visits = db.scalars(
        select(WorkoutVisit).where(
            WorkoutVisit.user_id == db.info["user_id"],
            WorkoutVisit.day >= f"{month}-01",
            WorkoutVisit.day <= f"{month}-{count:02d}",
        )
    ).all()
    rank = {"missed": 1, "attended": 2, "completed": 3}
    statuses = {}
    for visit in visits:
        if rank[visit.status] > rank.get(statuses.get(visit.day), 0):
            statuses[visit.day] = visit.status
    days = [
        {"day": f"{month}-{n:02d}", "status": statuses.get(f"{month}-{n:02d}")}
        for n in range(1, count + 1)
    ]
    return {
        "month": month,
        "first_weekday": first.weekday(),
        "days": days,
        "attended_count": sum(d["status"] in {"attended", "completed"} for d in days),
        "missed_count": sum(d["status"] == "missed" for d in days),
    }


@router.post("/attendance")
def mark_attendance(payload: AttendanceIn, db: Session = Depends(get_db)):
    data = workout_data(db)
    if not data["selected_plan"]:
        raise HTTPException(409, "Hãy chọn giáo án trước")
    day = data["date"]
    visit = db.scalar(
        select(WorkoutVisit).where(
            WorkoutVisit.user_id == db.info["user_id"],
            WorkoutVisit.plan_id == owned_key(db, data["selected_plan"]["id"]),
            WorkoutVisit.day == day,
        )
    )
    if visit and visit.status == "completed":
        if payload.status == "attended":
            return data
        raise HTTPException(409, "Buổi tập đã hoàn thành, không thể chuyển thành nghỉ")
    if not visit:
        visit = WorkoutVisit(
            user_id=db.info["user_id"],
            plan_id=owned_key(db, data["selected_plan"]["id"]),
            day=day,
            session_index=data["session_ordinal"],
            status=payload.status,
        )
        db.add(visit)
    else:
        visit.status = payload.status
    db.commit()
    return workout_data(db)


@router.post("/{exercise_id}/{action}")
def exercise_action(exercise_id: str, action: str, db: Session = Depends(get_db)):
    data = workout_data(db)
    item = next((i for i in data["items"] if i["id"] == exercise_id), None)
    if not item:
        raise HTTPException(404, "Không tìm thấy bài tập trong buổi hiện tại")
    if action not in {"start", "complete"}:
        raise HTTPException(422, "Thao tác không hợp lệ")
    if item["status"] == "completed":
        return data
    if data["attendance"] != "attended":
        raise HTTPException(409, "Hãy ghi nhận có đi tập hôm nay trước")
    if action == "complete" and item["status"] != "started":
        raise HTTPException(409, "Hãy bắt đầu bài tập trước khi đánh dấu hoàn thành")
    key = progress_key(db, data["selected_plan"]["id"], data["session_ordinal"], exercise_id)
    progress = db.scalar(
        select(WorkoutProgress).where(
            WorkoutProgress.user_id == db.info["user_id"],
            WorkoutProgress.workout_id == key,
        )
    )
    now = datetime.now(timezone.utc)
    if not progress:
        progress = WorkoutProgress(
            user_id=db.info["user_id"],
            workout_id=key,
            day=data["date"],
            status="started",
            started_at=now,
        )
        db.add(progress)
    if action == "complete":
        progress.status = "completed"
        progress.completed_at = now
    db.flush()
    updated = workout_data(db)
    if all(i["status"] == "completed" for i in updated["items"]):
        visit = db.scalar(
            select(WorkoutVisit).where(
                WorkoutVisit.user_id == db.info["user_id"],
                WorkoutVisit.plan_id == owned_key(db, data["selected_plan"]["id"]),
                WorkoutVisit.day == data["date"],
            )
        )
        visit.status = "completed"
    db.commit()
    return workout_data(db)
