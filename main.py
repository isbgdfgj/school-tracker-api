from fastapi import FastAPI, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import declarative_base, sessionmaker
import os
import hmac
import hashlib
import json
from urllib.parse import parse_qsl

# =========================
# DB (SQLite)
# =========================
DATABASE_URL = "sqlite:///./tracker.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


class Subject(Base):
    __tablename__ = "subjects"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)
    name = Column(String, nullable=False)
    missed = Column(Integer, nullable=False)
    total = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_subject_user_name"),
    )


# =========================
# Pydantic models
# =========================
class SubjectIn(BaseModel):
    # Для старого API (бота/локалки), где user_id приходит явно
    user_id: int
    name: str = Field(min_length=1, max_length=100)
    missed: int = Field(ge=0)
    total: int = Field(ge=1)


class SubjectInTG(BaseModel):
    # Для Mini App (tg.initData), user_id НЕ присылаем
    name: str = Field(min_length=1, max_length=100)
    missed: int = Field(ge=0)
    total: int = Field(ge=1)


# =========================
# FastAPI
# =========================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # для разработки можно *
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


# =========================
# Telegram initData verify
# =========================
def verify_telegram_init_data(init_data: str, bot_token: str) -> dict:
    if not bot_token:
        raise HTTPException(status_code=500, detail="BOT_TOKEN is not set on server")
    if not init_data:
        raise HTTPException(status_code=401, detail="Missing initData")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise HTTPException(status_code=401, detail="Missing hash in initData")

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs.keys()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise HTTPException(status_code=401, detail="Invalid initData")

    # user приходит JSON-строкой
    if "user" in pairs:
        try:
            pairs["user"] = json.loads(pairs["user"])
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid user JSON in initData")

    return pairs


def get_user_id_from_init_data(init_data: str) -> int:
    bot_token = os.environ.get("BOT_TOKEN")
    data = verify_telegram_init_data(init_data, bot_token)
    user = data.get("user")
    if not user or "id" not in user:
        raise HTTPException(status_code=401, detail="User not found in initData")
    return int(user["id"])


# =========================
# OLD API (works with explicit user_id)
# =========================
@app.post("/add")
def add_subject(payload: SubjectIn):
    db = SessionLocal()
    try:
        name_norm = payload.name.strip()

        subj = (
            db.query(Subject)
            .filter(
                Subject.user_id == payload.user_id,
                func.lower(Subject.name) == name_norm.lower()
            )
            .one_or_none()
        )

        if subj:
            subj.missed = payload.missed
            subj.total = payload.total
        else:
            subj = Subject(
                user_id=payload.user_id,
                name=name_norm,
                missed=payload.missed,
                total=payload.total,
            )
            db.add(subj)

        db.commit()

        percent = round((payload.missed / payload.total) * 100, 2)
        max_missed = int(payload.total * 0.6)
        can_miss_more = max(0, max_missed - payload.missed)

        return {"percent": percent, "can_miss_more": can_miss_more}
    finally:
        db.close()


@app.get("/stats/{user_id}")
def get_stats(user_id: int):
    db = SessionLocal()
    try:
        subjects = (
            db.query(Subject)
            .filter(Subject.user_id == user_id)
            .order_by(Subject.name.asc())
            .all()
        )
        return {
            "user_id": user_id,
            "subjects": [{"name": s.name, "missed": s.missed, "total": s.total} for s in subjects],
        }
    finally:
        db.close()


@app.delete("/subjects/{user_id}")
def delete_subject(user_id: int, name: str = Query(..., min_length=1)):
    db = SessionLocal()
    try:
        name_norm = name.strip().lower()

        subj = (
            db.query(Subject)
            .filter(
                Subject.user_id == user_id,
                func.lower(Subject.name) == name_norm
            )
            .one_or_none()
        )

        if not subj:
            raise HTTPException(status_code=404, detail="Subject not found")

        deleted_name = subj.name
        db.delete(subj)
        db.commit()
        return {"ok": True, "deleted": deleted_name}
    finally:
        db.close()


# =========================
# TG API (Mini App) - secure via initData
# =========================
@app.get("/tg/stats")
def tg_stats(x_telegram_init_data: str = Header(default="")):
    user_id = get_user_id_from_init_data(x_telegram_init_data)

    db = SessionLocal()
    try:
        subjects = (
            db.query(Subject)
            .filter(Subject.user_id == user_id)
            .order_by(Subject.name.asc())
            .all()
        )

        return {
            "user_id": user_id,
            "subjects": [{"name": s.name, "missed": s.missed, "total": s.total} for s in subjects],
        }
    finally:
        db.close()


@app.post("/tg/add")
def tg_add(data: SubjectInTG, x_telegram_init_data: str = Header(default="")):
    user_id = get_user_id_from_init_data(x_telegram_init_data)

    db = SessionLocal()
    try:
        name_norm = data.name.strip()

        subj = (
            db.query(Subject)
            .filter(
                Subject.user_id == user_id,
                func.lower(Subject.name) == name_norm.lower()
            )
            .one_or_none()
        )

        if subj:
            subj.missed = data.missed
            subj.total = data.total
        else:
            subj = Subject(user_id=user_id, name=name_norm, missed=data.missed, total=data.total)
            db.add(subj)

        db.commit()

        percent = round((data.missed / data.total) * 100, 2)
        max_missed = int(data.total * 0.6)
        can_miss_more = max(0, max_missed - data.missed)

        return {"percent": percent, "can_miss_more": can_miss_more}
    finally:
        db.close()


@app.delete("/tg/subject")
def tg_delete(name: str = Query(..., min_length=1), x_telegram_init_data: str = Header(default="")):
    user_id = get_user_id_from_init_data(x_telegram_init_data)

    db = SessionLocal()
    try:
        name_norm = name.strip().lower()

        subj = (
            db.query(Subject)
            .filter(
                Subject.user_id == user_id,
                func.lower(Subject.name) == name_norm
            )
            .one_or_none()
        )

        if not subj:
            raise HTTPException(status_code=404, detail="Subject not found")

        deleted_name = subj.name
        db.delete(subj)
        db.commit()
        return {"ok": True, "deleted": deleted_name}
    finally:
        db.close()