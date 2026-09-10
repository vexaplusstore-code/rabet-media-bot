from __future__ import annotations

import asyncio
import json
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiohttp import web

from .config import Settings
from .downloader import DownloadError, FileTooLarge, MediaDownloader
from .platforms import UnsupportedUrl, extract_first_url, identify_platform
from .rate_limit import HourlyRateLimiter
from .web import create_web_app


logger = logging.getLogger(__name__)


WELCOME_TEXT = (
    "<b>رابِط | Rabet</b> 🔗\n"
    "<i>أرسل الرابط… واستلم المقطع.</i>\n\n"
    "حمّل المقاطع العامة بسهولة من منصاتك المفضلة، "
    "مباشرة داخل Telegram.\n\n"
    "اختر من القائمة أو أرسل رابط المقطع الآن 👇"
)

TERMS_TEXT = (
    "<b>أهلًا بك في رابِط</b> 👋\n\n"
    "قبل أن نبدأ، استخدم البوت للمحتوى العام الذي تملكه "
    "أو لديك إذن بتنزيله فقط. المحتوى الخاص والمدفوع والمحمي غير مدعوم.\n\n"
    "بالضغط على «أوافق وأبدأ» فإنك توافق على سياسة الاستخدام."
)

CREDITS_TEXT = (
    "<b>المطوّر والحقوق</b> 👨‍💻\n\n"
    "صُمّم وطُوّر <b>RABET</b> ليمنحك تجربة سهلة، سريعة وأنيقة "
    "لتحميل الوسائط من المنصات المدعومة.\n\n"
    "👨‍💻 <b>البرمجة والتطوير</b>\n"
    "Abdulrahman Alzahrani\n\n"
    "🎨 <b>التصميم وتجربة المستخدم</b>\n"
    "Abdulrahman Alzahrani\n\n"
    "📧 <b>البريد الإلكتروني</b>\n"
    "<code>333.alsadi@gmail.com</code>\n\n"
    "© 2026 RABET — جميع حقوق البرمجة والتصميم محفوظة.\n"
    "<i>يُمنع نسخ البوت أو إعادة استخدام الكود أو الهوية البصرية "
    "دون إذن مسبق.</i>"
)


class DownloaderBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.bot = Bot(settings.bot_token)
        self.dispatcher = Dispatcher()
        self.router = Router()
        self.downloader = MediaDownloader(settings.max_file_mb, settings.max_duration_seconds)
        self.rate_limiter = HourlyRateLimiter(settings.hourly_user_limit)
        self.accepted_users: set[int] = set()
        self.active_users: set[int] = set()
        self.download_slots = asyncio.Semaphore(settings.max_concurrent_downloads)
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.router.message.register(self.start, CommandStart())
        self.router.message.register(self.help_message, Command("help"))
        self.router.message.register(self.privacy, Command("privacy"))
        self.router.message.register(self.credits, Command("credits"))
        self.router.message.register(self.quick_download, F.text == "📥 تحميل سريع")
        self.router.message.register(self.features_message, F.text == "✨ المزايا")
        self.router.message.register(self.help_message, F.text == "❔ المساعدة")
        self.router.message.register(self.privacy, F.text == "🔐 الخصوصية")
        self.router.message.register(
            self.credits,
            F.text == "👨‍💻 المطوّر والحقوق",
        )
        self.router.message.register(self.handle_web_app_data, F.web_app_data)
        self.router.callback_query.register(self.accept_terms, F.data == "accept_terms")
        self.router.callback_query.register(self.show_home, F.data == "menu_home")
        self.router.callback_query.register(self.show_download, F.data == "menu_download")
        self.router.callback_query.register(self.show_platforms, F.data == "menu_platforms")
        self.router.callback_query.register(self.show_help, F.data == "menu_help")
        self.router.callback_query.register(self.show_privacy, F.data == "menu_privacy")
        self.router.callback_query.register(self.show_credits, F.data == "menu_credits")
        self.router.callback_query.register(self.show_platforms, F.data.startswith("platform_"))
        self.router.message.register(self.handle_url, F.text)
        self.dispatcher.include_router(self.router)

    @staticmethod
    def _terms_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="✅ أوافق وأبدأ", callback_data="accept_terms")],
                [InlineKeyboardButton(text="🔐 سياسة الخصوصية", callback_data="menu_privacy")],
            ]
        )

    @staticmethod
    def _main_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="📥 تحميل مقطع", callback_data="menu_download")],
                [
                    InlineKeyboardButton(text="𝕏  X / تويتر", callback_data="platform_x"),
                    InlineKeyboardButton(text="🎵 TikTok", callback_data="platform_tiktok"),
                ],
                [
                    InlineKeyboardButton(text="📸 Instagram", callback_data="platform_instagram"),
                    InlineKeyboardButton(text="▶️ YouTube", callback_data="platform_youtube"),
                ],
                [
                    InlineKeyboardButton(text="✨ المزايا", callback_data="menu_platforms"),
                    InlineKeyboardButton(text="❔ المساعدة", callback_data="menu_help"),
                ],
                [InlineKeyboardButton(text="🔐 الخصوصية", callback_data="menu_privacy")],
                [
                    InlineKeyboardButton(
                        text="👨‍💻 المطوّر والحقوق",
                        callback_data="menu_credits",
                    )
                ],
            ]
        )

    def _app_keyboard(self) -> ReplyKeyboardMarkup:
        return ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(
                        text="✨ فتح واجهة RABET",
                        web_app=WebAppInfo(url=self.settings.web_app_url),
                    )
                ],
                [
                    KeyboardButton(text="📥 تحميل سريع"),
                    KeyboardButton(text="✨ المزايا"),
                ],
                [
                    KeyboardButton(text="❔ المساعدة"),
                    KeyboardButton(text="🔐 الخصوصية"),
                ],
                [KeyboardButton(text="👨‍💻 المطوّر والحقوق")],
            ],
            resize_keyboard=True,
            is_persistent=True,
            input_field_placeholder="ألصق رابط المقطع هنا…",
        )

    @staticmethod
    def _back_keyboard() -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏠 القائمة الرئيسية", callback_data="menu_home")]
            ]
        )

    async def _edit_or_answer(
        self,
        query: CallbackQuery,
        text: str,
        reply_markup: InlineKeyboardMarkup,
    ) -> None:
        await query.answer()
        if query.message:
            await query.message.edit_text(
                text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
            )

    async def start(self, message: Message) -> None:
        if message.from_user and message.from_user.id in self.accepted_users:
            await message.answer(
                WELCOME_TEXT,
                reply_markup=self._app_keyboard(),
                parse_mode=ParseMode.HTML,
            )
            return
        await message.answer(
            TERMS_TEXT,
            reply_markup=self._terms_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    async def help_message(self, message: Message) -> None:
        await message.answer(
            "<b>طريقة الاستخدام</b> 🪄\n\n"
            "1️⃣ انسخ رابط المقطع العام.\n"
            "2️⃣ أرسله هنا في المحادثة.\n"
            "3️⃣ انتظر قليلًا حتى يجهز الملف.\n"
            "4️⃣ استلم المقطع مباشرة.\n\n"
            "<i>الروابط الخاصة والبث المباشر وقوائم التشغيل غير مدعومة.</i>",
            reply_markup=self._app_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    async def privacy(self, message: Message) -> None:
        await message.answer(
            "<b>الخصوصية والأمان</b> 🔐\n\n"
            "🗑 لا نحتفظ بملفات الفيديو بعد إرسالها.\n"
            "🔑 لا نطلب كلمات مرور أو ملفات Cookies.\n"
            "⚡ تُحذف الملفات المؤقتة فور انتهاء الطلب.\n"
            "🛡 لا توجد قاعدة دائمة لبيانات المستخدمين.",
            reply_markup=self._app_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    async def credits(self, message: Message) -> None:
        await message.answer(
            CREDITS_TEXT,
            reply_markup=self._app_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    async def quick_download(self, message: Message) -> None:
        await message.answer(
            "<b>تحميل سريع</b> 📥\n\nألصق رابط المقطع في خانة الرسالة وأرسله مباشرة.",
            reply_markup=self._app_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    async def features_message(self, message: Message) -> None:
        await message.answer(
            "<b>منصاتك في مكان واحد</b> ✨\n\n"
            "𝕏  X / تويتر\n"
            "🎵 TikTok\n"
            "📸 Instagram\n"
            "▶️ YouTube\n\n"
            "🎞 جودة ذكية حتى 1080p\n"
            "🔊 دمج تلقائي للصوت والصورة\n"
            "🗑 حذف الملف فور إرساله",
            reply_markup=self._app_keyboard(),
            parse_mode=ParseMode.HTML,
        )

    async def accept_terms(self, query: CallbackQuery) -> None:
        if query.from_user:
            self.accepted_users.add(query.from_user.id)
        await query.answer("تم تفعيل RABET ✨")
        if query.message:
            await query.message.edit_text(
                "<b>تم تفعيل RABET بنجاح</b> ✅\n\n"
                "استخدم الواجهة الحديثة أو ألصق رابط المقطع مباشرة.",
                parse_mode=ParseMode.HTML,
            )
            await query.message.answer(
                WELCOME_TEXT,
                reply_markup=self._app_keyboard(),
                parse_mode=ParseMode.HTML,
            )

    async def show_home(self, query: CallbackQuery) -> None:
        await self._edit_or_answer(query, WELCOME_TEXT, self._main_keyboard())

    async def show_download(self, query: CallbackQuery) -> None:
        await self._edit_or_answer(
            query,
            "<b>تحميل مقطع</b> 📥\n\n"
            "ألصق رابطًا عامًا من إحدى المنصات المدعومة وسأبدأ فورًا.\n\n"
            "<i>مثال: أرسل رابط TikTok أو Instagram مباشرة في رسالة.</i>",
            self._back_keyboard(),
        )

    async def show_platforms(self, query: CallbackQuery) -> None:
        await self._edit_or_answer(
            query,
            "<b>المنصات المدعومة</b> ✨\n\n"
            "𝕏  <b>X / تويتر</b> — فيديوهات المنشورات العامة\n"
            "🎵 <b>TikTok</b> — المقاطع العامة\n"
            "📸 <b>Instagram</b> — Reels والمنشورات العامة\n"
            "▶️ <b>YouTube</b> — المقاطع المسموح بتنزيلها\n\n"
            "🎞 جودة ذكية حتى 1080p\n"
            "🔊 دمج تلقائي للصوت والصورة\n"
            "🗑 حذف الملف فور إرساله",
            self._back_keyboard(),
        )

    async def show_help(self, query: CallbackQuery) -> None:
        await self._edit_or_answer(
            query,
            "<b>كيف تستخدم رابِط؟</b> ❔\n\n"
            "1️⃣ انسخ رابط المقطع العام.\n"
            "2️⃣ أرسله هنا مباشرة.\n"
            "3️⃣ دع رابِط يتولى الباقي.\n\n"
            "عند تعذر التنزيل، تأكد أن الرابط عام وأن المقطع متاح.",
            self._back_keyboard(),
        )

    async def show_privacy(self, query: CallbackQuery) -> None:
        await self._edit_or_answer(
            query,
            "<b>الخصوصية والأمان</b> 🔐\n\n"
            "🗑 لا نحتفظ بملفات الفيديو بعد إرسالها.\n"
            "🔑 لا نطلب كلمات مرور أو ملفات Cookies.\n"
            "⚡ تُحذف الملفات المؤقتة فور انتهاء الطلب.\n"
            "🛡 لا توجد قاعدة دائمة لبيانات المستخدمين.",
            self._back_keyboard(),
        )

    async def show_credits(self, query: CallbackQuery) -> None:
        await self._edit_or_answer(
            query,
            CREDITS_TEXT,
            self._back_keyboard(),
        )

    async def handle_url(self, message: Message) -> None:
        if not message.text:
            return
        await self._process_url(message, message.text)

    async def handle_web_app_data(self, message: Message) -> None:
        if not message.web_app_data:
            return
        try:
            payload = json.loads(message.web_app_data.data)
        except (TypeError, json.JSONDecodeError):
            await message.answer("⚠️ تعذر قراءة الرابط من الواجهة. حاول مرة أخرى.")
            return
        if payload.get("action") != "download" or not isinstance(payload.get("url"), str):
            await message.answer("⚠️ طلب غير صالح. افتح واجهة RABET وحاول مجددًا.")
            return
        if message.from_user:
            self.accepted_users.add(message.from_user.id)
        await self._process_url(message, payload["url"])

    async def _process_url(self, message: Message, raw_text: str) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        if user_id not in self.accepted_users:
            await message.answer(
                "ابدأ من هنا أولًا 👇",
                reply_markup=self._terms_keyboard(),
            )
            return
        if user_id in self.active_users:
            await message.answer("⏳ لديك طلب قيد المعالجة. انتظر اكتماله أولًا.")
            return
        try:
            url = extract_first_url(raw_text)
            platform = identify_platform(url)
        except UnsupportedUrl as exc:
            await message.answer(str(exc))
            return
        if not self.rate_limiter.allow(user_id):
            await message.answer("⏱ وصلت إلى حد الاستخدام المؤقت. جرّب مرة أخرى لاحقًا.")
            return

        self.active_users.add(user_id)
        status = await message.answer(
            f"🔎 تم التعرف على <b>{platform.label}</b>\n"
            "⏳ جارٍ تجهيز المقطع…",
            parse_mode=ParseMode.HTML,
        )
        media = None
        try:
            async with self.download_slots:
                await self.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
                media = await self.downloader.download(url)
                await status.edit_text(
                    "✅ اكتمل التنزيل\n📤 جارٍ إرسال الملف…"
                )
                caption = self._caption(media.title, platform.label)
                try:
                    await message.answer_video(
                        video=FSInputFile(media.path),
                        thumbnail=(
                            FSInputFile(media.thumbnail_path)
                            if media.thumbnail_path
                            else None
                        ),
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                        supports_streaming=True,
                    )
                except Exception:
                    await message.answer_document(
                        document=FSInputFile(media.path),
                        caption=caption,
                        parse_mode=ParseMode.HTML,
                    )
            await status.delete()
        except FileTooLarge as exc:
            await status.edit_text(f"⚠️ تعذر الإرسال: {exc}")
        except DownloadError as exc:
            await status.edit_text(f"⚠️ {exc}")
        except Exception:
            logger.exception("Unexpected download job failure")
            await status.edit_text("⚠️ حدث خطأ غير متوقع أثناء تجهيز المقطع.")
        finally:
            if media:
                media.cleanup()
            self.active_users.discard(user_id)

    @staticmethod
    def _caption(title: str, platform: str) -> str:
        safe_title = (
            title.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        return f"<b>{safe_title[:300]}</b>\nالمصدر: {platform}\n@RabetMediaBot"

    async def run(self) -> None:
        web_runner = web.AppRunner(create_web_app())
        await web_runner.setup()
        web_site = web.TCPSite(web_runner, "0.0.0.0", self.settings.web_port)
        await web_site.start()
        logger.info("RABET Mini App ready on port %s", self.settings.web_port)
        node_ready, pot_ready = self.downloader.youtube_support_status()
        logger.info(
            "YouTube public-download helpers ready: node=%s pot_provider=%s",
            node_ready,
            pot_ready,
        )
        await self.bot.set_my_commands(
            [
                BotCommand(command="start", description="القائمة الرئيسية 🏠"),
                BotCommand(command="help", description="طريقة الاستخدام ❔"),
                BotCommand(command="privacy", description="الخصوصية والأمان 🔐"),
                BotCommand(command="credits", description="المطوّر والحقوق 👨‍💻"),
            ]
        )
        try:
            await self.dispatcher.start_polling(
                self.bot,
                allowed_updates=self.dispatcher.resolve_used_update_types(),
            )
        finally:
            await web_runner.cleanup()
