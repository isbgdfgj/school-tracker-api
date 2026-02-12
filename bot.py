import requests
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

BOT_TOKEN = "8347460912:AAFBQ5C7x94NtkMWceDKGTaQFvsuueLC6vA"
SERVER_URL = "http://127.0.0.1:8000"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот-трекер успеваемости 📚")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    try:
        r = requests.get(f"{SERVER_URL}/stats/{user_id}", timeout=10)
    except Exception as e:
        await update.message.reply_text(f"Не удалось подключиться к серверу: {e}")
        return

    if r.status_code != 200:
        await update.message.reply_text(f"Ошибка при получении статистики (HTTP {r.status_code})\n{r.text}")
        return

    data = r.json()
    subjects = data.get("subjects", [])

    if not subjects:
        await update.message.reply_text("Пока нет предметов. Добавь так:\n/add Математика 3 20")
        return

    lines = ["📊 *Твоя статистика по предметам:*"]
    total_missed = 0
    total_lessons = 0

    for s in subjects:
        name = s.get("name", "—")
        missed = int(s.get("missed", 0))
        total = int(s.get("total", 0))

        total_missed += missed
        total_lessons += total

        percent = round((missed / total) * 100, 1) if total else 0.0
        max_missed = int(total * 0.6)
        can_miss_more = max(0, max_missed - missed)

        lines.append(
            f"\n📚 *{name}*\n"
            f"Пропуски: {missed}/{total} ({percent}%)\n"
            f"Ещё можно пропустить (60%): {can_miss_more}"
        )

    overall_percent = round((total_missed / total_lessons) * 100, 1) if total_lessons else 0.0
    lines.append(f"\n—\nИтого пропусков: {total_missed}/{total_lessons} ({overall_percent}%)")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

 
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await update.message.reply_text("Использование: /delete <предмет>")
        return

    name = " ".join(args)

    try:
        r = requests.delete(
            f"{SERVER_URL}/subjects/{user_id}",
            params={"name": name},
            timeout=10
        )
    except Exception as e:
        await update.message.reply_text(f"Ошибка соединения: {e}")
        return

    if r.status_code == 404:
        await update.message.reply_text(f"Не найден предмет: {name}")
        return

    if r.status_code != 200:
        await update.message.reply_text(f"Ошибка удаления: {r.text}")
        return

    await update.message.reply_text(f"🗑 Удалён предмет: {name}")
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Формат:
    /add Математика 3 20
    где 3 = пропуски, 20 = всего занятий
    """
    user_id = update.effective_user.id
    args = context.args

    if len(args) < 3:
        await update.message.reply_text(
            "Использование: /add <предмет> <пропуски> <всего>\n"
            "Пример: /add Математика 3 20"
        )
        return

    # предмет может быть из нескольких слов
    *name_parts, missed_str, total_str = args
    name = " ".join(name_parts)

    try:
        missed = int(missed_str)
        total = int(total_str)
    except ValueError:
        await update.message.reply_text("Пропуски и всего должны быть числами. Пример: /add Математика 3 20")
        return

    payload = {"user_id": user_id, "name": name, "missed": missed, "total": total}

    try:
        r = requests.post(f"{SERVER_URL}/add", json=payload, timeout=10)
    except Exception as e:
        await update.message.reply_text(f"Не удалось подключиться к серверу: {e}")
        return

    if r.status_code != 200:
        await update.message.reply_text(f"Сервер вернул ошибку: {r.status_code}\n{r.text}")
        return

    data = r.json()

    # под разные варианты ответа сервера (чтобы не падало)
    percent = data.get("percent") or data.get("missed_percent")
    can_miss_more = data.get("can_miss_more") or data.get("remaining_misses")

    msg = f"✅ {name}\nПропуски: {missed}/{total}"
    if percent is not None:
        msg += f"\nПроцент пропусков: {percent}%"
    if can_miss_more is not None:
        msg += f"\nЕщё можно пропустить: {can_miss_more}"

    await update.message.reply_text(msg)

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("delete", delete))

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()