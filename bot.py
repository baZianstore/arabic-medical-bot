"""منطق بوت تيليغرام العربي ومهمة النشر اليومية."""

from __future__ import annotations

import asyncio
import html
import logging
from datetime import datetime
from typing import Any

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import Forbidden, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from config import Settings
from database import Database, DatabaseError

logger = logging.getLogger(__name__)
TELEGRAM_SAFE_MESSAGE_LIMIT = 3900

WELCOME_TEXT = (
    "مرحبًا بك في بوت التعليم الطبي للطب الباطني.\n\n"
    "ستجد هنا مرض اليوم، وبحثًا سريعًا، وأسئلة قصيرة للمراجعة. "
    "المحتوى تعليمي عام ولا يُعد بديلًا عن التقييم الطبي أو الإرشادات المحلية.\n\n"
    "اكتب /help لعرض الأوامر."
)

HELP_TEXT = (
    "الأوامر المتاحة:\n"
    "/today — عرض مرض اليوم\n"
    "/search اسم المرض — البحث بالعربية أو الإنجليزية\n"
    "/quiz — سؤال اختيار من متعدد\n"
    "/systems — عرض أجهزة وتخصصات المحتوى\n"
    "/stats — إحصاءات البوت\n"
    "/help — عرض هذه المساعدة"
)


def _escape_with_budget(value: Any, budget: int) -> str:
    """تشفير HTML مع حد طول لا يقطع كيان HTML في منتصفه."""
    result: list[str] = []
    used = 0
    for character in str(value or "غير متوفر"):
        escaped = html.escape(character)
        if used + len(escaped) > budget:
            result.append("…")
            break
        result.append(escaped)
        used += len(escaped)
    return "".join(result)


def format_disease(disease: dict[str, Any]) -> str:
    """تنسيق ملخص مرض آمن وضمن حد رسالة Telegram."""
    message = (
        f"<b>{_escape_with_budget(disease.get('name_ar'), 220)}</b>\n"
        f"<i>{_escape_with_budget(disease.get('name_en'), 220)}</i>\n\n"
        f"<b>التعريف:</b>\n{_escape_with_budget(disease.get('definition'), 900)}\n\n"
        f"<b>الأعراض:</b>\n{_escape_with_budget(disease.get('symptoms'), 1000)}\n\n"
        f"<b>العلاج:</b>\n{_escape_with_budget(disease.get('treatment'), 1200)}\n\n"
        "<i>تنبيه: هذا محتوى تعليمي عام، وليس تشخيصًا أو وصفة علاجية فردية.</i>"
    )
    return message[:TELEGRAM_SAFE_MESSAGE_LIMIT]


def format_question(question: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    """إنشاء نص السؤال ولوحة الإجابات الأربع."""
    question_id = str(question["id"])
    text = html.escape(str(question["question"]))
    rows = []
    for letter in ("A", "B", "C", "D"):
        option = html.escape(str(question[f"option_{letter.lower()}"]))
        rows.append([InlineKeyboardButton(f"{letter}. {option}", callback_data=f"quiz|{question_id}|{letter}")])
    return f"<b>سؤال اليوم:</b>\n\n{text}", InlineKeyboardMarkup(rows)


async def _database_call(func: Any, *args: Any) -> Any:
    """تشغيل اتصال Supabase في خيط منفصل حتى لا تتوقف حلقة البوت."""
    return await asyncio.to_thread(func, *args)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ترحيب المستخدم وتفعيل اشتراكه في المحتوى اليومي."""
    if not update.effective_user or not update.effective_message:
        return
    database: Database = context.application.bot_data["database"]
    try:
        await _database_call(database.upsert_subscriber, update.effective_user.id)
        await update.effective_message.reply_text(WELCOME_TEXT)
    except DatabaseError:
        logger.exception("فشل تسجيل مشترك دون تسجيل بيانات المستخدم.")
        await update.effective_message.reply_text(
            "مرحبًا بك. تعذر تفعيل النشر اليومي مؤقتًا، لكن يمكنك استخدام الأوامر الآن."
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض قائمة الأوامر بالعربية."""
    if update.effective_message:
        await update.effective_message.reply_text(HELP_TEXT)


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض المرض المحدد لليوم."""
    if not update.effective_message:
        return
    database: Database = context.application.bot_data["database"]
    settings: Settings = context.application.bot_data["settings"]
    try:
        local_date = datetime.now(settings.timezone).date()
        disease = await _database_call(database.get_daily_disease, local_date)
        if not disease:
            await update.effective_message.reply_text("لا يوجد محتوى منشور حاليًا.")
            return
        await update.effective_message.reply_text(format_disease(disease), parse_mode=ParseMode.HTML)
    except DatabaseError:
        logger.exception("فشل تحميل مرض اليوم.")
        await update.effective_message.reply_text("تعذر تحميل مرض اليوم مؤقتًا. حاول لاحقًا.")


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """البحث عن مرض باسمه العربي أو الإنجليزي."""
    if not update.effective_message:
        return
    query = " ".join(context.args).strip()
    if not query:
        await update.effective_message.reply_text("اكتب اسم المرض بعد الأمر، مثل: /search السكري")
        return
    database: Database = context.application.bot_data["database"]
    try:
        results = await _database_call(database.search_diseases, query)
        if not results:
            await update.effective_message.reply_text("لم أجد مرضًا بهذا الاسم. جرّب كلمة أقصر أو الاسم الإنجليزي.")
        elif len(results) == 1:
            await update.effective_message.reply_text(format_disease(results[0]), parse_mode=ParseMode.HTML)
        else:
            names = "\n".join(
                f"• {html.escape(str(item['name_ar']))} — {html.escape(str(item['name_en']))}" for item in results
            )
            await update.effective_message.reply_text(
                f"<b>النتائج:</b>\n{names}\n\nأعد البحث باسم أكثر تحديدًا.", parse_mode=ParseMode.HTML
            )
    except DatabaseError:
        logger.exception("فشل البحث في المحتوى.")
        await update.effective_message.reply_text("تعذر البحث مؤقتًا. حاول لاحقًا.")


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال سؤال عشوائي بأربعة اختيارات."""
    if not update.effective_message:
        return
    database: Database = context.application.bot_data["database"]
    try:
        question = await _database_call(database.random_question)
        if not question:
            await update.effective_message.reply_text("لا توجد أسئلة متاحة حاليًا.")
            return
        text, keyboard = format_question(question)
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except DatabaseError:
        logger.exception("فشل تحميل الاختبار.")
        await update.effective_message.reply_text("تعذر تحميل سؤال الآن. حاول لاحقًا.")


async def quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تصحيح إجابة زر الاختبار وإرسال الشرح."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer("تم استلام إجابتك")
    try:
        prefix, question_id, selected = query.data.split("|", maxsplit=2)
        if prefix != "quiz" or selected not in {"A", "B", "C", "D"}:
            raise ValueError
    except ValueError:
        if query.message:
            await query.message.reply_text("هذه الإجابة غير صالحة.")
        return

    database: Database = context.application.bot_data["database"]
    try:
        question = await _database_call(database.get_question, question_id)
        if not question:
            if query.message:
                await query.message.reply_text("لم يعد هذا السؤال متاحًا.")
            return
        correct = str(question["correct_answer"]).upper()
        result = "إجابة صحيحة." if selected == correct else f"إجابة غير صحيحة. الإجابة الصحيحة هي {correct}."
        explanation = html.escape(str(question.get("explanation") or "لا يوجد شرح إضافي."))
        if query.message:
            await query.edit_message_reply_markup(reply_markup=None)
            await query.message.reply_text(
                f"<b>{result}</b>\n\n{explanation}", parse_mode=ParseMode.HTML
            )
    except DatabaseError:
        logger.exception("فشل تصحيح سؤال الاختبار.")
        if query.message:
            await query.message.reply_text("تعذر التحقق من الإجابة مؤقتًا.")


async def systems_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض أجهزة وتخصصات المحتوى المتاحة."""
    if not update.effective_message:
        return
    database: Database = context.application.bot_data["database"]
    try:
        diseases = await _database_call(database.list_diseases)
        systems = sorted({str(item.get("system", "")).strip() for item in diseases if item.get("system")})
        if not systems:
            await update.effective_message.reply_text("لا توجد أجهزة طبية مسجلة حاليًا.")
            return
        await update.effective_message.reply_text("الأجهزة والتخصصات المتاحة:\n" + "\n".join(f"• {s}" for s in systems))
    except DatabaseError:
        logger.exception("فشل تحميل الأجهزة الطبية.")
        await update.effective_message.reply_text("تعذر تحميل القائمة مؤقتًا.")


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض إحصاءات عامة بلا بيانات شخصية."""
    if not update.effective_message:
        return
    database: Database = context.application.bot_data["database"]
    try:
        stats = await _database_call(database.get_stats)
        await update.effective_message.reply_text(
            "إحصاءات البوت:\n"
            f"• الأمراض: {stats['diseases']}\n"
            f"• الأسئلة: {stats['questions']}\n"
            f"• المشتركون النشطون: {stats['subscribers']}"
        )
    except DatabaseError:
        logger.exception("فشل تحميل الإحصاءات.")
        await update.effective_message.reply_text("تعذر تحميل الإحصاءات مؤقتًا.")


async def publish_daily_content(bot: Any, database: Database, *, now: datetime | None = None) -> dict[str, int | bool]:
    """نشر مرض اليوم مرة واحدة وإرجاع ملخص غير شخصي للعملية."""
    current = now or datetime.now().astimezone()
    disease = await _database_call(database.get_daily_disease, current.date())
    if not disease:
        return {"published": False, "sent": 0, "failed": 0}
    claimed = await _database_call(database.claim_daily_publication, current.date(), str(disease["id"]))
    if not claimed:
        return {"published": False, "sent": 0, "failed": 0}

    subscribers = await _database_call(database.list_active_subscribers)
    sent = 0
    failed = 0
    message = "<b>المحتوى الطبي اليومي</b>\n\n" + format_disease(disease)
    for subscriber in subscribers:
        user_id = int(subscriber["user_id"])
        try:
            await bot.send_message(chat_id=user_id, text=message, parse_mode=ParseMode.HTML)
            sent += 1
        except Forbidden:
            failed += 1
            try:
                await _database_call(database.deactivate_subscriber, user_id)
            except DatabaseError:
                logger.exception("فشل تعطيل مشترك غير متاح دون تسجيل معرّفه.")
        except TelegramError:
            failed += 1
            logger.warning("فشل إرسال رسالة يومية إلى أحد المشتركين.")
    return {"published": True, "sent": sent, "failed": failed}


async def daily_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """مهمة APScheduler اليومية داخل عملية البوت."""
    database: Database = context.application.bot_data["database"]
    try:
        await publish_daily_content(context.bot, database)
    except DatabaseError:
        logger.exception("فشلت مهمة النشر اليومي.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إخفاء تفاصيل الخطأ وعدم تسجيل محتوى تحديث المستخدم."""
    error_name = context.error.__class__.__name__ if context.error else "UnknownError"
    logger.error("Unhandled Telegram error type=%s", error_name)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("حدث خطأ مؤقت. حاول مرة أخرى لاحقًا.")
        except TelegramError:
            logger.warning("تعذر إرسال رسالة الخطأ العامة.")


def schedule_daily_job(application: Application, settings: Settings) -> None:
    """جدولة مهمة الساعة المحددة حسب المنطقة الزمنية."""
    if application.job_queue is None:
        raise RuntimeError("ثبّت python-telegram-bot[job-queue] لتفعيل الجدولة.")
    local_time = settings.daily_post_time.replace(tzinfo=settings.timezone)
    application.job_queue.run_daily(daily_job, time=local_time, name="daily-medical-content")


def create_bot_application(settings: Settings, database: Database) -> Application:
    """بناء تطبيق تيليغرام وتسجيل جميع المعالجات."""
    application = Application.builder().token(settings.bot_token).post_init(configure_bot_commands).build()
    application.bot_data["database"] = database
    application.bot_data["settings"] = settings
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("today", today_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("systems", systems_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CallbackQueryHandler(quiz_answer, pattern=r"^quiz\|[0-9a-fA-F-]{36}\|[A-D]$"))
    application.add_error_handler(error_handler)
    schedule_daily_job(application, settings)
    return application


async def configure_bot_commands(application: Application) -> None:
    """عرض قائمة الأوامر العربية داخل واجهة تيليغرام."""
    await application.bot.set_my_commands(
        [
            BotCommand("today", "مرض اليوم"),
            BotCommand("search", "البحث عن مرض"),
            BotCommand("quiz", "سؤال للمراجعة"),
            BotCommand("systems", "الأجهزة الطبية"),
            BotCommand("stats", "إحصاءات البوت"),
            BotCommand("help", "المساعدة"),
        ]
    )
