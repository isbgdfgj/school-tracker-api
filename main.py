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