"""Kiểu dữ liệu đầu vào cho các API HBTNFIT.

Tách schema khỏi route giúp file API chỉ tập trung vào luồng xử lý và giúp cả
nhóm tìm quy tắc kiểm tra dữ liệu ở một nơi duy nhất.
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class RegisterIn(RequestModel):
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=8, max_length=128)


class LoginIn(RequestModel):
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=1, max_length=128)


class ProfileIn(RequestModel):
    age: int | None = Field(default=None, ge=18, le=120)
    height_cm: float | None = Field(default=None, ge=100, le=250)
    weight_kg: float | None = Field(default=None, ge=25, le=400)
    target_weight_kg: float | None = Field(default=None, ge=25, le=400)
    target_date: date | None = None
    sex: str | None = Field(default=None, pattern="^(female|male)$")
    activity_level: str | None = Field(default=None, pattern="^(sedentary|light|moderate|high)$")
    protein_mode: str = Field(default="balanced", pattern="^(balanced|strength)$")
    goal: str = Field(default="maintain", pattern="^(maintain|gain|lose)$")
    avoid_tags: list[str] = Field(default_factory=list)
    target_kcal: float = Field(default=1800, ge=900, le=5000)


class GuidanceChoiceIn(RequestModel):
    food_choice: str | None = None
    workout_choice: str | None = None


class ChecklistToggleIn(RequestModel):
    completed: bool
    amount: float | None = Field(default=None, gt=0, le=2000)


class CustomFoodIn(RequestModel):
    name: str = Field(min_length=2, max_length=160)
    kcal_100g: float = Field(default=0, ge=0, le=900)
    protein_100g: float = Field(default=0, ge=0, le=100)
    carb_100g: float = Field(default=0, ge=0, le=100)
    fat_100g: float = Field(default=0, ge=0, le=100)


class LogIn(RequestModel):
    food_id: str | None = None
    custom_food: CustomFoodIn | None = None
    grams: float = Field(gt=0, le=2000)
    meal_type: str = Field(pattern="^(breakfast|lunch|dinner|snack)$")
    eaten_at: datetime | None = None
    confirmed: bool


class BatchLogIn(RequestModel):
    items: list[LogIn] = Field(min_length=1, max_length=5)
    confirmation_id: str | None = Field(default=None, min_length=8, max_length=80)
    avoidance_acknowledged: bool = False


class LogUpdate(RequestModel):
    grams: float = Field(gt=0, le=2000)
    meal_type: str = Field(pattern="^(breakfast|lunch|dinner|snack)$")


class WorkoutSelectIn(RequestModel):
    plan_id: str


class AttendanceIn(RequestModel):
    status: str = Field(pattern="^(attended|missed)$")


class PlanIn(RequestModel):
    week_start: date
    target_kcal: float = Field(ge=900, le=5000)
    avoid_tags: list[str] = Field(default_factory=list)
