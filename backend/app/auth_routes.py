"""Các route tài khoản tối thiểu để xác minh chủ sở hữu dữ liệu."""

import unicodedata
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .auth import create_token, hash_password, verify_password
from .db import get_db, public_db
from .models import User
from .schemas import LoginIn, RegisterIn

router = APIRouter(prefix="/api/auth", tags=["Tài khoản"])


def normalized_username(value):
    username = unicodedata.normalize("NFC", value.strip().casefold())
    if (
        not 3 <= len(username) <= 30
        or not username.replace("_", "").replace("-", "").replace(".", "").isalnum()
    ):
        raise HTTPException(
            422, "Tên đăng nhập cần 3-30 ký tự chữ, số, dấu chấm, gạch ngang hoặc gạch dưới"
        )
    return username


def user_data(user):
    return {"id": user.id, "username": user.username, "full_name": user.full_name}


def auth_response(user):
    return {"access_token": create_token(user.id), "token_type": "bearer", "user": user_data(user)}


@router.post("/register", status_code=201)
def register(payload: RegisterIn, db: Session = Depends(public_db)):
    username = normalized_username(payload.username)
    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(409, "Tên đăng nhập này đã được sử dụng")
    user = User(
        id=str(uuid.uuid4()),
        full_name=username,
        username=username,
        password_hash=hash_password(payload.password),
    )
    # Xác minh cấu hình khóa trước khi lưu, tránh tạo tài khoản mà không trả được phiên.
    result = auth_response(user)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Tên đăng nhập này đã được sử dụng") from None
    return result


@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(public_db)):
    user = db.scalar(select(User).where(User.username == normalized_username(payload.username)))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "Tên đăng nhập hoặc mật khẩu không đúng")
    return auth_response(user)


@router.get("/me")
def me(db: Session = Depends(get_db)):
    return user_data(db.get(User, db.info["user_id"]))
