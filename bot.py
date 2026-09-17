"""منطق بوت تيليغرام الطبي ثنائي اللغة ومهمة النشر اليومية."""

from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import re
import secrets
from datetime import datetime
from typing import Any

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import Forbidden, TelegramError
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from analytics import format_weekly_usage_report
from bilingual_content import (
    BILINGUAL_TOPICS,
    all_bilingual_topics,
    get_bilingual_topic,
)
from config import Settings
from database import Database, DatabaseError

logger = logging.getLogger(__name__)
TELEGRAM_SAFE_MESSAGE_LIMIT = 3900
REPORT_LINK_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{24,64}$")

WELCOME_TEXT = (
    "<b>Clinical English | التعليم الطبي الثنائي</b>\n\n"
    "Learn medicine in English with a clear Arabic explanation.\n"
    "تعلّم الطب بالإنجليزية مع شرح عربي واضح، وأسئلة قصيرة، وصور أصلية، ومراجع موثوقة.\n\n"
    "اختر من القائمة للبدء. المحتوى تعليمي عام ولا يستبدل التقييم الطبي أو الإرشادات المحلية."
)

HELP_TEXT = (
    "<b>Commands | الأوامر</b>\n\n"
    "/today — Topic of the day | موضوع اليوم\n"
    "/learn asthma — English topic + Arabic explanation\n"
    "/quiz_en — English MCQ + Arabic explanation\n"
    "/sources asthma — Official references | المراجع\n"
    "/search اسم المرض — البحث بالعربية أو الإنجليزية\n"
    "/quiz — سؤال مراجعة بالعربية\n"
    "/systems — الأجهزة والتخصصات\n"
    "/stats — إحصاءات البوت\n"
    "/menu — القائمة الرئيسية\n"
    "/help — المساعدة"
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


def _topic_for_disease(disease: dict[str, Any]) -> dict[str, Any] | None:
    """ربط سجل Supabase ببطاقة ثنائية بواسطة الاسم الإنجليزي ثم العربي."""
    return get_bilingual_topic(disease.get("name_en")) or get_bilingual_topic(disease.get("name_ar"))


def _topic_image_url(topic: dict[str, Any], settings: Settings | None) -> str | None:
    """بناء رابط HTTPS لصورة الموضوع عند توفر أصل عام للخدمة."""
    if not settings or not settings.webhook_url:
        return None
    image_path = str(topic.get("image_path") or "").lstrip("/")
    if not image_path.startswith("static/medical_topics/"):
        return None
    return f"{settings.webhook_url.rstrip('/')}/{image_path}"


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """إنشاء قائمة بداية مختصرة مناسبة للهاتف وiPad."""
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Topic of the day | موضوع اليوم", callback_data="menu|today")],
            [
                InlineKeyboardButton("English quiz | اختبار", callback_data="menu|quiz_en"),
                InlineKeyboardButton("Topics | الموضوعات", callback_data="menu|topics"),
            ],
            [
                InlineKeyboardButton("Statistics | الإحصاءات", callback_data="menu|stats"),
                InlineKeyboardButton("Help | المساعدة", callback_data="menu|help"),
            ],
        ]
    )


def topic_selection_keyboard() -> InlineKeyboardMarkup:
    """عرض الأمراض الثنائية المتاحة دون تخزين أي اختيار للمستخدم."""
    rows: list[list[InlineKeyboardButton]] = []
    topics = all_bilingual_topics()
    for index in range(0, len(topics), 2):
        row = [
            InlineKeyboardButton(
                f"{topic['name_en']} | {topic['name_ar']}",
                callback_data=f"topic|{topic['id']}",
            )
            for topic in topics[index : index + 2]
        ]
        rows.append(row)
    rows.append([InlineKeyboardButton("Main menu | القائمة", callback_data="menu|home")])
    return InlineKeyboardMarkup(rows)


def topic_actions_keyboard(topic: dict[str, Any]) -> InlineKeyboardMarkup:
    """إنشاء أزرار التعمق التدريجي في بطاقة الموضوع."""
    topic_id = str(topic["id"])
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("More details | شرح موسع", callback_data=f"detail|{topic_id}"),
                InlineKeyboardButton("Quiz | اختبار", callback_data=f"newquiz|{topic_id}"),
            ],
            [
                InlineKeyboardButton("Sources | المراجع", callback_data=f"refs|{topic_id}"),
                InlineKeyboardButton("All topics | كل الموضوعات", callback_data="menu|topics"),
            ],
        ]
    )


def reference_keyboard(topic: dict[str, Any]) -> InlineKeyboardMarkup:
    """تحويل المراجع الرسمية إلى أزرار URL مباشرة."""
    rows = []
    for reference in topic["references"]:
        label = f"{reference['publisher']} · {reference['year']}"
        rows.append([InlineKeyboardButton(label[:60], url=str(reference["url"]))])
    rows.append([InlineKeyboardButton("Main menu | القائمة", callback_data="menu|home")])
    return InlineKeyboardMarkup(rows)


def format_disease(disease: dict[str, Any]) -> str:
    """تنسيق ملخص عربي آمن وضمن حد رسالة Telegram كخيار احتياطي."""
    message = (
        f"<b>{_escape_with_budget(disease.get('name_ar'), 220)}</b>\n"
        f"<i>{_escape_with_budget(disease.get('name_en'), 220)}</i>\n\n"
        f"<b>التعريف:</b>\n{_escape_with_budget(disease.get('definition'), 900)}\n\n"
        f"<b>الأعراض:</b>\n{_escape_with_budget(disease.get('symptoms'), 1000)}\n\n"
        f"<b>العلاج:</b>\n{_escape_with_budget(disease.get('treatment'), 1200)}\n\n"
        "<i>تنبيه: هذا محتوى تعليمي عام، وليس تشخيصًا أو وصفة علاجية فردية.</i>"
    )
    return message[:TELEGRAM_SAFE_MESSAGE_LIMIT]


def _paired_points(english: list[str], arabic: list[str], *, limit: int = 4) -> str:
    """تنسيق نقاط إنجليزية يتبع كلًا منها تفسير عربي."""
    lines = []
    for index, (english_item, arabic_item) in enumerate(zip(english[:limit], arabic[:limit], strict=False), start=1):
        lines.append(
            f"{index}. {_escape_with_budget(english_item, 210)}\n"
            f"   ↳ {_escape_with_budget(arabic_item, 230)}"
        )
    return "\n".join(lines)


def format_bilingual_topic(topic: dict[str, Any]) -> tuple[str, str]:
    """تنسيق بطاقة ثنائية في جزأين آمنين ضمن حدود Telegram."""
    summary = (
        f"<b>{_escape_with_budget(topic['name_en'], 180)}</b>\n"
        f"<b>{_escape_with_budget(topic['name_ar'], 180)}</b>\n\n"
        "<b>Clinical overview | نظرة سريرية</b>\n"
        f"{_escape_with_budget(topic['overview_en'], 680)}\n\n"
        "<b>الشرح بالعربية</b>\n"
        f"{_escape_with_budget(topic['explanation_ar'], 760)}\n\n"
        "<b>Key points | النقاط الأساسية</b>\n"
        f"{_paired_points(topic['key_points_en'], topic['key_points_ar'])}\n\n"
        "<i>Educational content only | محتوى تعليمي عام فقط</i>"
    )
    details = (
        f"<b>{_escape_with_budget(topic['name_en'], 180)} — Details | التفاصيل</b>\n\n"
        "<b>Diagnosis</b>\n"
        f"{_escape_with_budget(topic['diagnosis_en'], 620)}\n"
        f"↳ {_escape_with_budget(topic['diagnosis_ar'], 700)}\n\n"
        "<b>Management</b>\n"
        f"{_escape_with_budget(topic['management_en'], 620)}\n"
        f"↳ {_escape_with_budget(topic['management_ar'], 700)}\n\n"
        "<b>Red flags | علامات الإنذار</b>\n"
        f"{_paired_points(topic['red_flags_en'], topic['red_flags_ar'], limit=2)}\n\n"
        "<b>Clinical pearl | لؤلؤة سريرية</b>\n"
        f"{_escape_with_budget(topic['clinical_pearl_en'], 360)}\n"
        f"↳ {_escape_with_budget(topic['clinical_pearl_ar'], 420)}\n\n"
        "<i>لا تستخدم هذه الرسالة للتشخيص أو لتغيير علاج موصوف.</i>"
    )
    return summary[:TELEGRAM_SAFE_MESSAGE_LIMIT], details[:TELEGRAM_SAFE_MESSAGE_LIMIT]


def format_sources(topic: dict[str, Any]) -> str:
    """تنسيق قائمة مراجع رسمية قابلة للنقر."""
    lines = [
        (
            f"<b>Official sources | المراجع الرسمية</b>\n"
            f"{_escape_with_budget(topic['name_en'], 180)} | "
            f"{_escape_with_budget(topic['name_ar'], 180)}\n"
        )
    ]
    for index, reference in enumerate(topic["references"], start=1):
        title = _escape_with_budget(reference["title"], 320)
        publisher = _escape_with_budget(reference["publisher"], 180)
        year = _escape_with_budget(reference["year"], 60)
        url = html.escape(str(reference["url"]), quote=True)
        lines.append(f'{index}. <a href="{url}">{title}</a>\n   {publisher} · {year}')
    lines.append("\n<i>تُراجع المعلومة مع أحدث إرشاد محلي قبل التطبيق السريري.</i>")
    return "\n\n".join(lines)[:TELEGRAM_SAFE_MESSAGE_LIMIT]


def format_question(question: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    """إنشاء سؤال عربي ولوحة الإجابات الأربع."""
    question_id = str(question["id"])
    text = html.escape(str(question["question"]))
    rows = []
    for letter in ("A", "B", "C", "D"):
        option = html.escape(str(question[f"option_{letter.lower()}"]))
        rows.append([InlineKeyboardButton(f"{letter}. {option}", callback_data=f"quiz|{question_id}|{letter}")])
    return f"<b>سؤال اليوم:</b>\n\n{text}", InlineKeyboardMarkup(rows)


def format_bilingual_question(topic: dict[str, Any]) -> tuple[str, InlineKeyboardMarkup]:
    """إنشاء سؤال إنجليزي مع خيارات إنجليزية وتصحيح عربي لاحقًا."""
    question = topic["mcq"]
    rows = []
    for index, option in enumerate(question["options_en"]):
        letter = chr(ord("A") + index)
        rows.append(
            [
                InlineKeyboardButton(
                    f"{letter}. {_escape_with_budget(option, 56)}",
                    callback_data=f"biquiz|{topic['id']}|{letter}",
                )
            ]
        )
    text = (
        "<b>English medical question</b>\n"
        "<i>سؤال طبي باللغة الإنجليزية</i>\n\n"
        f"{_escape_with_budget(question['question_en'], 900)}"
    )
    return text, InlineKeyboardMarkup(rows)


async def _database_call(func: Any, *args: Any) -> Any:
    """تشغيل اتصال Supabase في خيط منفصل حتى لا تتوقف حلقة البوت."""
    return await asyncio.to_thread(func, *args)


async def _record_usage(
    context: ContextTypes.DEFAULT_TYPE,
    event_type: str,
    topic_id: str | None = None,
) -> None:
    """تسجيل عداد يومي مجمع دون معرف مستخدم أو نص رسالة."""
    database: Database = context.application.bot_data["database"]
    settings: Settings = context.application.bot_data["settings"]
    metric_date = datetime.now(settings.timezone).date()
    try:
        await _database_call(database.record_usage_event, metric_date, event_type, topic_id)
    except (DatabaseError, ValueError):
        logger.warning("تعذر تحديث عداد استخدام مجمع event=%s.", event_type)


async def _send_topic_card(message: Any, topic: dict[str, Any], settings: Settings | None) -> None:
    """إرسال الصورة ثم الملخص؛ فشل الصورة لا يمنع وصول المحتوى."""
    image_url = _topic_image_url(topic, settings)
    if image_url:
        try:
            await message.reply_photo(
                photo=image_url,
                caption=(
                    f"{topic['name_en']} | {topic['name_ar']}\n"
                    "Original educational visual | صورة تعليمية أصلية"
                ),
            )
        except TelegramError:
            logger.warning("تعذر إرسال صورة تعليمية؛ سيستمر إرسال النص.")
    summary, _ = format_bilingual_topic(topic)
    await message.reply_text(summary, parse_mode=ParseMode.HTML, reply_markup=topic_actions_keyboard(topic))


async def _send_random_bilingual_quiz(message: Any) -> str:
    """اختيار سؤال إنجليزي عشوائي من البطاقات المراجعة."""
    topic = secrets.choice(all_bilingual_topics())
    text, keyboard = format_bilingual_question(topic)
    await message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    return str(topic["id"])


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ترحيب المستخدم وتفعيل اشتراكه مع قائمة تفاعلية."""
    if not update.effective_user or not update.effective_message:
        return
    database: Database = context.application.bot_data["database"]
    warning = ""
    try:
        await _database_call(database.upsert_subscriber, update.effective_user.id)
    except DatabaseError:
        logger.exception("فشل تسجيل مشترك دون تسجيل بيانات المستخدم.")
        warning = "\n\nتعذر تفعيل النشر اليومي مؤقتًا، لكن جميع أوامر التعلم متاحة الآن."
    await update.effective_message.reply_text(
        WELCOME_TEXT + warning,
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu_keyboard(),
    )
    await _record_usage(context, "start")


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إظهار القائمة الرئيسية عند الطلب."""
    if update.effective_message:
        await update.effective_message.reply_text(
            "<b>Main menu | القائمة الرئيسية</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(),
        )
        await _record_usage(context, "menu_open")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض قائمة الأوامر بالعربية والإنجليزية."""
    if update.effective_message:
        await update.effective_message.reply_text(
            HELP_TEXT,
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(),
        )
        await _record_usage(context, "help_view")


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض موضوع اليوم ثنائي اللغة، مع fallback عربي."""
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
        topic = _topic_for_disease(disease)
        if topic:
            await _send_topic_card(update.effective_message, topic, settings)
            await _record_usage(context, "today_view", str(topic["id"]))
        else:
            await update.effective_message.reply_text(format_disease(disease), parse_mode=ParseMode.HTML)
            await _record_usage(context, "today_view")
    except DatabaseError:
        logger.exception("فشل تحميل مرض اليوم.")
        await update.effective_message.reply_text("تعذر تحميل مرض اليوم مؤقتًا. حاول لاحقًا.")


async def learn_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض بطاقة ثنائية بالاسم أو قائمة الموضوعات عند غياب الاسم."""
    if not update.effective_message:
        return
    requested = " ".join(context.args).strip()
    if not requested:
        await update.effective_message.reply_text(
            "Choose a topic | اختر موضوعًا",
            reply_markup=topic_selection_keyboard(),
        )
        return
    topic = get_bilingual_topic(requested)
    if not topic:
        await update.effective_message.reply_text(
            "لم أجد بطاقة ثنائية بهذا الاسم. جرّب: /learn asthma أو اختر من القائمة.",
            reply_markup=topic_selection_keyboard(),
        )
        return
    settings: Settings = context.application.bot_data["settings"]
    await _send_topic_card(update.effective_message, topic, settings)
    await _record_usage(context, "topic_view", str(topic["id"]))


async def sources_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض مراجع موضوع محدد، أو موضوع اليوم عند غياب الاسم."""
    if not update.effective_message:
        return
    requested = " ".join(context.args).strip()
    topic = get_bilingual_topic(requested) if requested else None
    if not requested:
        database: Database = context.application.bot_data["database"]
        settings: Settings = context.application.bot_data["settings"]
        try:
            disease = await _database_call(database.get_daily_disease, datetime.now(settings.timezone).date())
            topic = _topic_for_disease(disease) if disease else None
        except DatabaseError:
            logger.exception("فشل تحديد مراجع موضوع اليوم.")
    if not topic:
        await update.effective_message.reply_text(
            "اختر موضوعًا لعرض مراجعِه.",
            reply_markup=topic_selection_keyboard(),
        )
        return
    await update.effective_message.reply_text(
        format_sources(topic),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=reference_keyboard(topic),
    )
    await _record_usage(context, "sources_view", str(topic["id"]))


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """البحث عن مرض باسمه العربي أو الإنجليزي."""
    if not update.effective_message:
        return
    query = " ".join(context.args).strip()
    if not query:
        await update.effective_message.reply_text("اكتب اسم المرض بعد الأمر، مثل: /search السكري")
        return
    database: Database = context.application.bot_data["database"]
    settings: Settings = context.application.bot_data["settings"]
    try:
        results = await _database_call(database.search_diseases, query)
        if not results:
            await update.effective_message.reply_text("لم أجد مرضًا بهذا الاسم. جرّب كلمة أقصر أو الاسم الإنجليزي.")
            await _record_usage(context, "search_empty")
        elif len(results) == 1:
            topic = _topic_for_disease(results[0])
            if topic:
                await _send_topic_card(update.effective_message, topic, settings)
            else:
                await update.effective_message.reply_text(format_disease(results[0]), parse_mode=ParseMode.HTML)
            await _record_usage(context, "search_success")
        else:
            names = "\n".join(
                f"• {html.escape(str(item['name_ar']))} — {html.escape(str(item['name_en']))}" for item in results
            )
            await update.effective_message.reply_text(
                f"<b>النتائج:</b>\n{names}\n\nأعد البحث باسم أكثر تحديدًا.", parse_mode=ParseMode.HTML
            )
            await _record_usage(context, "search_success")
    except DatabaseError:
        logger.exception("فشل البحث في المحتوى.")
        await update.effective_message.reply_text("تعذر البحث مؤقتًا. حاول لاحقًا.")


async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال سؤال عربي عشوائي بأربعة اختيارات."""
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
        await _record_usage(context, "quiz_ar_started")
    except DatabaseError:
        logger.exception("فشل تحميل الاختبار.")
        await update.effective_message.reply_text("تعذر تحميل سؤال الآن. حاول لاحقًا.")


async def quiz_en_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال سؤال إنجليزي مع شرح عربي بعد الإجابة."""
    if update.effective_message:
        topic_id = await _send_random_bilingual_quiz(update.effective_message)
        await _record_usage(context, "quiz_en_started", topic_id)


async def quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تصحيح إجابة السؤال العربي وإرسال الشرح."""
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
            await query.message.reply_text(f"<b>{result}</b>\n\n{explanation}", parse_mode=ParseMode.HTML)
        await _record_usage(context, "quiz_ar_answered")
        if selected == correct:
            await _record_usage(context, "quiz_ar_correct")
    except DatabaseError:
        logger.exception("فشل تصحيح سؤال الاختبار.")
        if query.message:
            await query.message.reply_text("تعذر التحقق من الإجابة مؤقتًا.")


async def bilingual_quiz_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تصحيح السؤال الإنجليزي وشرح السبب بالعربية."""
    query = update.callback_query
    if not query or not query.data:
        return
    await query.answer("Answer received | تم استلام الإجابة")
    try:
        prefix, topic_id, selected = query.data.split("|", maxsplit=2)
        topic = BILINGUAL_TOPICS.get(topic_id)
        if prefix != "biquiz" or selected not in {"A", "B", "C", "D"} or not topic:
            raise ValueError
    except ValueError:
        if query.message:
            await query.message.reply_text("Invalid answer | إجابة غير صالحة")
        return

    question = topic["mcq"]
    correct = chr(ord("A") + int(question["correct_index"]))
    result = (
        "Correct | إجابة صحيحة"
        if selected == correct
        else f"Not correct | غير صحيحة — Correct answer: {correct}"
    )
    if query.message:
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            f"<b>{result}</b>\n\n<b>الشرح بالعربية</b>\n"
            f"{_escape_with_budget(question['explanation_ar'], 1500)}",
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("Another question | سؤال آخر", callback_data="menu|quiz_en")],
                    [InlineKeyboardButton("Topic | الموضوع", callback_data=f"topic|{topic_id}")],
                ]
            ),
        )
    await _record_usage(context, "quiz_en_answered", topic_id)
    if selected == correct:
        await _record_usage(context, "quiz_en_correct", topic_id)


async def topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """فتح موضوع من قائمة الأزرار."""
    query = update.callback_query
    if not query or not query.data or not query.message:
        return
    await query.answer()
    topic = BILINGUAL_TOPICS.get(query.data.partition("|")[2])
    if not topic:
        await query.message.reply_text("لم يعد هذا الموضوع متاحًا.")
        return
    settings: Settings = context.application.bot_data["settings"]
    await _send_topic_card(query.message, topic, settings)
    await _record_usage(context, "topic_view", str(topic["id"]))


async def detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض التفاصيل الموسعة لبطاقة ثنائية."""
    query = update.callback_query
    if not query or not query.data or not query.message:
        return
    await query.answer()
    topic = BILINGUAL_TOPICS.get(query.data.partition("|")[2])
    if not topic:
        await query.message.reply_text("لم يعد هذا الموضوع متاحًا.")
        return
    _, details = format_bilingual_topic(topic)
    await query.message.reply_text(details, parse_mode=ParseMode.HTML, reply_markup=topic_actions_keyboard(topic))
    await _record_usage(context, "topic_detail_view", str(topic["id"]))


async def references_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """عرض مراجع الموضوع من زر البطاقة."""
    query = update.callback_query
    if not query or not query.data or not query.message:
        return
    await query.answer()
    topic = BILINGUAL_TOPICS.get(query.data.partition("|")[2])
    if not topic:
        await query.message.reply_text("لم تعد المراجع متاحة.")
        return
    await query.message.reply_text(
        format_sources(topic),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=reference_keyboard(topic),
    )
    await _record_usage(context, "sources_view", str(topic["id"]))


async def new_quiz_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """بدء سؤال إنجليزي مرتبط بموضوع محدد."""
    query = update.callback_query
    if not query or not query.data or not query.message:
        return
    await query.answer()
    topic = BILINGUAL_TOPICS.get(query.data.partition("|")[2])
    if not topic:
        await query.message.reply_text("لم يعد هذا السؤال متاحًا.")
        return
    text, keyboard = format_bilingual_question(topic)
    await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    await _record_usage(context, "quiz_en_started", str(topic["id"]))


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """تنفيذ أزرار القائمة عبر نفس منطق الأوامر."""
    query = update.callback_query
    if not query or not query.data or not query.message:
        return
    await query.answer()
    action = query.data.partition("|")[2]
    if action == "today":
        await today_command(update, context)
    elif action == "quiz_en":
        topic_id = await _send_random_bilingual_quiz(query.message)
        await _record_usage(context, "quiz_en_started", topic_id)
    elif action == "topics":
        await query.message.reply_text("Choose a topic | اختر موضوعًا", reply_markup=topic_selection_keyboard())
        await _record_usage(context, "menu_open")
    elif action == "stats":
        await stats_command(update, context)
    elif action == "help":
        await query.message.reply_text(HELP_TEXT, parse_mode=ParseMode.HTML, reply_markup=main_menu_keyboard())
        await _record_usage(context, "help_view")
    else:
        await query.message.reply_text(
            "<b>Main menu | القائمة الرئيسية</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_keyboard(),
        )
        await _record_usage(context, "menu_open")


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
        await _record_usage(context, "systems_view")
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
            "<b>Bot statistics | إحصاءات البوت</b>\n"
            f"• Diseases | الأمراض: {stats['diseases']}\n"
            f"• Arabic questions | الأسئلة العربية: {stats['questions']}\n"
            f"• Bilingual topics | الموضوعات الثنائية: {len(BILINGUAL_TOPICS)}\n"
            f"• Active subscribers | المشتركون النشطون: {stats['subscribers']}",
            parse_mode=ParseMode.HTML,
        )
        await _record_usage(context, "stats_view")
    except DatabaseError:
        logger.exception("فشل تحميل الإحصاءات.")
        await update.effective_message.reply_text("تعذر تحميل الإحصاءات مؤقتًا.")


async def link_report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """ربط المحادثة الخاصة كمستلم إداري بواسطة رمز لمرة واحدة."""
    if not update.effective_message or not update.effective_chat:
        return
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text("يجب تنفيذ ربط التقرير في محادثة خاصة مع البوت.")
        return
    raw_token = context.args[0].strip() if len(context.args) == 1 else ""
    if not REPORT_LINK_TOKEN_PATTERN.fullmatch(raw_token):
        await update.effective_message.reply_text("رمز الربط غير صالح أو ناقص.")
        return
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    database: Database = context.application.bot_data["database"]
    try:
        linked = await _database_call(
            database.consume_report_link_token,
            token_hash,
            update.effective_chat.id,
        )
    except DatabaseError:
        logger.exception("فشل ربط مستلم التقرير دون تسجيل معرف المحادثة.")
        await update.effective_message.reply_text("تعذر إكمال الربط مؤقتًا. حاول لاحقًا.")
        return
    if not linked:
        await update.effective_message.reply_text("انتهت صلاحية رمز الربط أو استُخدم سابقًا.")
        return
    await update.effective_message.reply_text(
        "تم ربط هذه المحادثة بالتقرير الأسبوعي بنجاح.\n"
        "لا يتضمن التقرير معرفات مستخدمين أو نصوص رسائل."
    )


async def send_weekly_usage_report(
    bot: Any,
    database: Database,
    *,
    now: datetime | None = None,
    test: bool = False,
) -> dict[str, Any]:
    """إرسال تقرير مجمع لمستلم الإدارة مع claim أسبوعي يمنع التكرار."""
    current_date = (now or datetime.now().astimezone()).date()
    config = await _database_call(database.get_report_delivery_config)
    if not config or config.get("telegram_chat_id") is None:
        return {"sent": False, "reason": "not_linked"}

    current, previous = await _database_call(database.get_completed_week_reports, current_date)
    week_start = current["start_date"]
    if not test:
        claimed = await _database_call(database.claim_weekly_report, week_start)
        if not claimed:
            return {"sent": False, "reason": "already_sent"}

    try:
        await bot.send_message(
            chat_id=int(config["telegram_chat_id"]),
            text=format_weekly_usage_report(current, previous, test=test),
            parse_mode=ParseMode.HTML,
        )
    except TelegramError:
        if not test:
            try:
                await _database_call(database.release_weekly_report, week_start)
            except DatabaseError:
                logger.exception("تعذر تحرير حجز تقرير فشل إرساله.")
        logger.warning("فشل إرسال التقرير الأسبوعي إلى مستلم الإدارة.")
        return {"sent": False, "reason": "telegram_error"}

    if not test:
        try:
            await _database_call(
                database.complete_weekly_report,
                week_start,
                current["total_interactions"],
            )
            await _database_call(database.prune_usage_data, current_date)
        except DatabaseError:
            logger.exception("أُرسل التقرير لكن تعذر تحديث سجل التشغيل أو الاحتفاظ.")
    return {
        "sent": True,
        "test": test,
        "week_start": week_start.isoformat(),
        "total_interactions": current["total_interactions"],
    }


async def maybe_send_weekly_usage_report(
    bot: Any,
    database: Database,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """إرسال التقرير يوم الأحد فقط؛ يعمل الـclaim كحاجز تكرار ثانٍ."""
    current = now or datetime.now().astimezone()
    if current.weekday() != 6:
        return {"sent": False, "reason": "not_sunday"}
    return await send_weekly_usage_report(bot, database, now=current)


async def publish_daily_content(
    bot: Any,
    database: Database,
    *,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> dict[str, int | bool]:
    """نشر ملخص يومي مرة واحدة وإرجاع إحصاء غير شخصي للعملية."""
    current = now or datetime.now().astimezone()
    disease = await _database_call(database.get_daily_disease, current.date())
    if not disease:
        return {"published": False, "sent": 0, "failed": 0}
    claimed = await _database_call(database.claim_daily_publication, current.date(), str(disease["id"]))
    if not claimed:
        return {"published": False, "sent": 0, "failed": 0}

    topic = _topic_for_disease(disease)
    if topic:
        summary, _ = format_bilingual_topic(topic)
        message = "<b>Daily medical topic | الموضوع الطبي اليومي</b>\n\n" + summary
        keyboard = topic_actions_keyboard(topic)
        image_url = _topic_image_url(topic, settings)
    else:
        message = "<b>المحتوى الطبي اليومي</b>\n\n" + format_disease(disease)
        keyboard = None
        image_url = None

    subscribers = await _database_call(database.list_active_subscribers)
    sent = 0
    failed = 0
    for subscriber in subscribers:
        user_id = int(subscriber["user_id"])
        try:
            if image_url:
                try:
                    await bot.send_photo(
                        chat_id=user_id,
                        photo=image_url,
                        caption=f"{topic['name_en']} | {topic['name_ar']}",
                    )
                except TelegramError:
                    logger.warning("تعذر إرسال صورة يومية إلى أحد المشتركين؛ سيُرسل النص.")
            await bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
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
    settings: Settings = context.application.bot_data["settings"]
    try:
        await publish_daily_content(context.bot, database, settings=settings)
        await maybe_send_weekly_usage_report(
            context.bot,
            database,
            now=datetime.now(settings.timezone),
        )
    except DatabaseError:
        logger.exception("فشلت مهمة النشر اليومي أو التقرير الأسبوعي.")


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
    """بناء تطبيق تيليغرام وتسجيل جميع الأوامر والـcallbacks."""
    application = Application.builder().token(settings.bot_token).post_init(configure_bot_commands).build()
    application.bot_data["database"] = database
    application.bot_data["settings"] = settings
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("today", today_command))
    application.add_handler(CommandHandler("learn", learn_command))
    application.add_handler(CommandHandler("sources", sources_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("quiz_en", quiz_en_command))
    application.add_handler(CommandHandler("quiz", quiz_command))
    application.add_handler(CommandHandler("systems", systems_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("link_report", link_report_command))
    application.add_handler(CallbackQueryHandler(menu_callback, pattern=r"^menu\|(today|quiz_en|topics|stats|help|home)$"))
    application.add_handler(CallbackQueryHandler(topic_callback, pattern=r"^topic\|[a-z-]+$"))
    application.add_handler(CallbackQueryHandler(detail_callback, pattern=r"^detail\|[a-z-]+$"))
    application.add_handler(CallbackQueryHandler(references_callback, pattern=r"^refs\|[a-z-]+$"))
    application.add_handler(CallbackQueryHandler(new_quiz_callback, pattern=r"^newquiz\|[a-z-]+$"))
    application.add_handler(CallbackQueryHandler(bilingual_quiz_answer, pattern=r"^biquiz\|[a-z-]+\|[A-D]$"))
    application.add_handler(CallbackQueryHandler(quiz_answer, pattern=r"^quiz\|[0-9a-fA-F-]{36}\|[A-D]$"))
    application.add_error_handler(error_handler)
    schedule_daily_job(application, settings)
    return application


async def configure_bot_commands(application: Application) -> None:
    """عرض قائمة الأوامر الثنائية داخل واجهة Telegram."""
    await application.bot.set_my_commands(
        [
            BotCommand("start", "ابدأ | Start"),
            BotCommand("menu", "القائمة الرئيسية | Main menu"),
            BotCommand("today", "موضوع اليوم | Daily topic"),
            BotCommand("learn", "تعلم موضوعًا بالإنجليزية والعربية"),
            BotCommand("quiz_en", "English MCQ + شرح عربي"),
            BotCommand("sources", "المراجع الرسمية | Sources"),
            BotCommand("search", "البحث عن مرض"),
            BotCommand("quiz", "سؤال عربي للمراجعة"),
            BotCommand("systems", "الأجهزة الطبية"),
            BotCommand("stats", "إحصاءات البوت"),
            BotCommand("link_report", "ربط التقرير الإداري"),
            BotCommand("help", "المساعدة | Help"),
        ]
    )
