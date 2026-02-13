import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

BOT_TOKEN = "8347460912:AAFVQET48RfNvabIuYpBcKQS-rD9q9AN5Ao"
SERVER_URL = "http://127.0.0.1:8000"
VERCEL_URL = "https://school-tracker-frontend.vercel.app"


# =========================
# /start — кнопка Mini App
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Открыть трекер", web_app=WebAppInfo(url=VERCEL_URL))]
    ]
    await update.message.reply_text(
        "Открой мини-приложение кнопкой ниже:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================
# /stats — получить статистику
# =========================
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    try:
        r = requests.get(f"{SERVER_URL}/stats/{user_id}", timeout=10)
    except Exception as e:
        await update.message.reply_text(f"Ошибка соединения с сервером: {e}")
        return

    if r.status_code != 200:
        await update.message.reply_text(f"Ошибка сервера: {r.status_code}\n{r.text}")
        return

    data = r.json()
    subjects = data.get("subjects", [])

    if not subjects:
        await update.message.reply_text("Пока нет предметов. Добавь так:\n/add Математика 3 20")
        return

    lines = ["📊 *Твоя статистика:*"]
    total_missed = 0
    total_lessons = 0

    for s in subjects:
        name = s.get("name", "—")
        missed = int(s.get("missed", 0))
        total = int(s.get("total", 0))

        total_missed += missed
        total_lessons += total

        percent = round((missed / total) * 100, 1) if total else 0.0
        can_miss_more = max(0, int(total * 0.6) - missed)

        lines.append(
            f"\n📚 *{name}*\n"
            f"Пропуски: {missed}/{total} ({percent}%)\n"
            f"Можно ещё пропустить: {can_miss_more}"
        )

    overall = round((total_missed / total_lessons) * 100, 1) if total_lessons else 0.0
    lines.append(f"\n—\nВсего: {total_missed}/{total_lessons} ({overall}%)")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# =========================
# /add — добавить предмет
# =========================
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if len(args) < 3:
        await update.message.reply_text(
            "Использование:\n/add Математика 3 20"
        )
        return

    *name_parts, missed_str, total_str = args
    name = " ".join(name_parts)

    try:
        missed = int(missed_str)
        total = int(total_str)
    except ValueError:
        await update.message.reply_text("Пропуски и всего должны быть числами")
        return

    payload = {
        "user_id": user_id,
        "name": name,
        "missed": missed,
        "total": total
    }

    try:
        r = requests.post(f"{SERVER_URL}/add", json=payload, timeout=10)
    except Exception as e:
        await update.message.reply_text(f"Ошибка соединения: {e}")
        return

    if r.status_code != 200:
        await update.message.reply_text(f"Ошибка сервера: {r.status_code}\n{r.text}")
        return

    data = r.json()
    percent = data.get("percent")
    can = data.get("can_miss_more")

    msg = f"✅ {name}\nПропуски: {missed}/{total}"
    if percent is not None:
        msg += f"\nПроцент: {percent}%"
    if can is not None:
        msg += f"\nМожно ещё пропустить: {can}"

    await update.message.reply_text(msg)


# =========================
# /delete — удалить предмет
# =========================
async def delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    args = context.args

    if not args:
        await update.message.reply_text("Использование:\n/delete Математика")
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
        await update.message.reply_text(f"Ошибка: {r.text}")
        return

    await update.message.reply_text(f"🗑 Удалён предмет: {name}")


# =========================
# запуск
# =========================
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