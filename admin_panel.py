import os
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship, sessionmaker

# Инициализация FastAPI приложения
app = FastAPI(title="Banana Boom Admin Panel", version="1.0.0")

# Настройка Jinja2 шаблонов
templates = Jinja2Templates(directory="templates")

# Настройка статических файлов
app.mount("/static", StaticFiles(directory="static"), name="static")

# Настройка базы данных
DATABASE_URL = "sqlite:///vkbanana.db"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Модели данных
class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, index=True)
    balance = Column(Integer, default=10)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.utcnow)
    is_blocked = Column(Boolean, default=False)
    block_reason = Column(String)


class GenerationTask(Base):
    __tablename__ = "generation_tasks"
    task_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    task_type = Column(String)
    model = Column(String)
    prompt = Column(Text)
    reference_photos = Column(Text)
    status = Column(String, default="pending")
    cost = Column(Integer)
    result_url = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    error_message = Column(String)
    api_task_id = Column(String)


class Transaction(Base):
    __tablename__ = "transactions"
    transaction_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    amount = Column(Integer)
    reason = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"))
    order_id = Column(String, unique=True)
    tbank_payment_id = Column(String)
    amount_rub = Column(Integer)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)


# Создание таблиц в базе данных
Base.metadata.create_all(bind=engine)


# Зависимость для получения сессии БД
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Маршруты админ-панели
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    # Статистика
    total_users = db.query(User).count()
    active_users = (
        db.query(User)
        .filter(User.last_activity >= datetime.utcnow() - timedelta(days=7))
        .count()
    )
    blocked_users = db.query(User).filter_by(is_blocked=True).count()
    total_tasks = db.query(GenerationTask).count()
    completed_tasks = db.query(GenerationTask).filter_by(status="completed").count()
    total_balance = db.query(func.sum(User.balance)).scalar() or 0
    total_transactions = db.query(Transaction).count()

    return templates.TemplateResponse(
        "admin/index.html",
        {
            "request": request,
            "total_users": total_users,
            "active_users": active_users,
            "blocked_users": blocked_users,
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "total_balance": total_balance,
            "total_transactions": total_transactions,
        },
    )


@app.get("/users", response_class=HTMLResponse)
async def users(request: Request, db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.created_at.desc()).all()
    return templates.TemplateResponse(
        "admin/users.html", {"request": request, "users": users}
    )


@app.get("/users/{user_id}", response_class=HTMLResponse)
async def user_details(request: Request, user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).get_or_404(user_id)
    tasks = (
        db.query(GenerationTask)
        .filter_by(user_id=user_id)
        .order_by(GenerationTask.created_at.desc())
        .all()
    )
    transactions = (
        db.query(Transaction)
        .filter_by(user_id=user_id)
        .order_by(Transaction.created_at.desc())
        .all()
    )
    payments = (
        db.query(Payment)
        .filter_by(user_id=user_id)
        .order_by(Payment.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "admin/user_details.html",
        {
            "request": request,
            "user": user,
            "tasks": tasks,
            "transactions": transactions,
            "payments": payments,
        },
    )


@app.post("/users/{user_id}/block")
async def block_user(user_id: int, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).get_or_404(user_id)
    form = await request.form()
    reason = form.get("reason", "Без указания причины")
    user.is_blocked = True
    user.block_reason = reason
    db.commit()
    return RedirectResponse(
        url=url_for("user_details", user_id=user_id), status_code=303
    )


@app.post("/users/{user_id}/unblock")
async def unblock_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).get_or_404(user_id)
    user.is_blocked = False
    user.block_reason = None
    db.commit()
    return RedirectResponse(
        url=url_for("user_details", user_id=user_id), status_code=303
    )


@app.get("/broadcasts", response_class=HTMLResponse)
async def broadcasts(request: Request, db: Session = Depends(get_db)):
    broadcasts = (
        db.query(GenerationTask)
        .filter_by(task_type="broadcast")
        .order_by(GenerationTask.created_at.desc())
        .all()
    )
    return templates.TemplateResponse(
        "admin/broadcasts.html", {"request": request, "broadcasts": broadcasts}
    )


@app.get("/broadcasts/create", response_class=HTMLResponse)
async def create_broadcast(request: Request):
    return templates.TemplateResponse(
        "admin/create_broadcast.html", {"request": request}
    )


@app.post("/broadcasts/create")
async def create_broadcast_post(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    title = form.get("title")
    message = form.get("message")
    # TODO: Реализовать рассылку
    return RedirectResponse(url=url_for("broadcasts"), status_code=303)


@app.get("/stats", response_class=HTMLResponse)
async def stats(request: Request, db: Session = Depends(get_db)):
    # Подробная статистика
    users_by_month = (
        db.query(
            func.strftime("%Y-%m", User.created_at).label("month"),
            func.count(User.user_id).label("count"),
        )
        .group_by("month")
        .order_by("month")
        .all()
    )

    tasks_by_type = (
        db.query(
            GenerationTask.task_type, func.count(GenerationTask.task_id).label("count")
        )
        .group_by(GenerationTask.task_type)
        .all()
    )

    return templates.TemplateResponse(
        "admin/stats.html",
        {
            "request": request,
            "users_by_month": users_by_month,
            "tasks_by_type": tasks_by_type,
        },
    )


@app.get("/tasks", response_class=HTMLResponse)
async def tasks(request: Request, db: Session = Depends(get_db)):
    tasks = db.query(GenerationTask).order_by(GenerationTask.created_at.desc()).all()
    return templates.TemplateResponse(
        "admin/tasks.html", {"request": request, "tasks": tasks}
    )


@app.get("/tasks/{task_id}", response_class=HTMLResponse)
async def task_details(request: Request, task_id: int, db: Session = Depends(get_db)):
    task = db.query(GenerationTask).get_or_404(task_id)
    user = db.query(User).get(task.user_id)
    return templates.TemplateResponse(
        "admin/task_details.html", {"request": request, "task": task, "user": user}
    )


@app.get("/transactions", response_class=HTMLResponse)
async def transactions(request: Request, db: Session = Depends(get_db)):
    transactions = db.query(Transaction).order_by(Transaction.created_at.desc()).all()
    return templates.TemplateResponse(
        "admin/transactions.html", {"request": request, "transactions": transactions}
    )


@app.get("/payments", response_class=HTMLResponse)
async def payments(request: Request, db: Session = Depends(get_db)):
    payments = db.query(Payment).order_by(Payment.created_at.desc()).all()
    return templates.TemplateResponse(
        "admin/payments.html", {"request": request, "payments": payments}
    )


# Запуск админ-панели
def run_admin_panel():
    # Создаем директорию для шаблонов
    os.makedirs("templates/admin", exist_ok=True)

    # Создаем таблицы в базе данных
    Base.metadata.create_all(bind=engine)

    # Запуск FastAPI сервера
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=5000)


if __name__ == "__main__":
    run_admin_panel()
