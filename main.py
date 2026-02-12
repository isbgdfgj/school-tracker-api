from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, Column, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import declarative_base, sessionmaker

# 🔹 SQLite база (файл tracker.db в папке проекта)
DATABASE_URL = "sqlite:///./tracker.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


# 🔹 Таблица предметов
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


# 🔹 Модель входных данных
class SubjectIn(BaseModel):
    user_id: int
    name: str = Field(min_length=1, max_length=100)
    missed: int = Field(ge=0)
    total: int = Field(ge=1)


app = FastAPI()
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # для разработки можно *
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 🔹 Создание таблиц при старте
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


# 🔹 Добавление/обновление предмета
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
            # предмет уже есть — обновляем числа, а имя можно оставить как было в базе
            subj.missed = payload.missed
            subj.total = payload.total
        else:
            # предмета нет — создаём и сохраняем "красивое" имя (как ввели, но без пробелов)
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

        return {
            "percent": percent,
            "can_miss_more": can_miss_more
        }

    finally:
        db.close()


# 🔹 Получение статистики
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
            "subjects": [
                {
                    "name": s.name,
                    "missed": s.missed,
                    "total": s.total
                }
                for s in subjects
            ]
        }

    finally:
        db.close()
from sqlalchemy import func
from fastapi import Query

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

        deleted_name = subj.name  # как было в базе (красиво вернуть)
        db.delete(subj)
        db.commit()
        return {"ok": True, "deleted": deleted_name}
    finally:
        db.close()
import os, time, hmac, hashlib, json
from urllib.parse import parse_qsl
from fastapi import Header, HTTPException

def verify_telegram_init_data(init_data: str, bot_token: str):
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs.keys()))
    secret_key = hashlib.sha256(bot_token.encode()).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if computed_hash != received_hash:
        raise HTTPException(status_code=401, detail="Invalid initData")

    if "user" in pairs:
        pairs["user"] = json.loads(pairs["user"])

    return pairs

def get_user_id(init_data: str):
    bot_token = os.environ.get("BOT_TOKEN")
    data = verify_telegram_init_data(init_data, bot_token)
    return data["user"]["id"]
@app.get("/tg/stats")
def tg_stats(x_telegram_init_data: str = Header(default="")):
    user_id = get_user_id(x_telegram_init_data)

    db = SessionLocal()
    subjects = db.query(Subject).filter(Subject.user_id == user_id).all()

    return {
        "user_id": user_id,
        "subjects": [
            {"name": s.name, "missed": s.missed, "total": s.total}
            for s in subjects
        ]
    }
@app.post("/tg/add")
def tg_add(data: SubjectIn, x_telegram_init_data: str = Header(default="")):
    user_id = get_user_id(x_telegram_init_data)

    db = SessionLocal()

    subject = Subject(
        user_id=user_id,
        name=data.name,
        missed=data.missed,
        total=data.total
    )

    db.add(subject)
    db.commit()

    percent = round((data.missed / data.total) * 100, 1)

    return {
        "percent": percent
    }