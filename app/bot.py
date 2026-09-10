from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .config import Settings
from .downloader import DownloadError, FileTooLarge, MediaDownloader
from .platforms import UnsupportedUrl, extract_first_url, identify_platform
from .rate_limit import HourlyRateLimiter


logger = logging.getLogger(__name__)


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
        self.router.callback_query.register(self.accept_terms, F.data == "accept_terms")
        self.router.message.register(self.handle_url, F.text)
        self.dispatcher.include_router(self.router)

    async def start(self, message: Message) -> None:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="أوافق وأبدأ", callback_data="accept_terms")]
            ]
        )
        await message.answer(
            "أهلًا بك في رابط 👋\n\n"
            "أرسل رابطًا عامًا من X أو TikTok أو Instagram أو YouTube، وسأجهز المقطع لك.\n\n"
            "باستخدام البوت تؤكد أن المحتوى ملكك أو لديك إذن بتنزيله، وأنه غير خاص أو مدفوع أو محمي.",
            reply_markup=keyboard,
        )

    async def help_message(self, message: Message) -> None:
        await message.answer(
            "طريقة الاستخدام:\n"
            "1) أرسل رابط المقطع العام.\n"
            "2) انتظر انتهاء المعالجة.\n"
            "3) استلم الملف مباشرة.\n\n"
            "الروابط الخاصة والبث المباشر وقوائم التشغيل غير مدعومة."
        )

    async def privacy(self, message: Message) -> None:
        await message.answer(
            "الخصوصية:\n"
            "• لا نحفظ ملفات الفيديو بعد إرسالها.\n"
            "• لا نطلب كلمات مرور أو ملفات Cookies.\n"
            "• تُحذف الملفات المؤقتة فور انتهاء الطلب.\n"
            "• تُحفظ حدود الاستخدام في الذاكرة المؤقتة فقط."
        )

    async def accept_terms(self, query: CallbackQuery) -> None:
        if query.from_user:
            self.accepted_users.add(query.from_user.id)
        await query.answer("تم التفعيل")
        if query.message:
            await query.message.answer("تم ✅ أرسل رابط المقطع الآن.")

    async def handle_url(self, message: Message) -> None:
        if not message.from_user or not message.text:
            return
        user_id = message.from_user.id
        if user_id not in self.accepted_users:
            await message.answer("ابدأ بالأمر /start ثم وافق على سياسة الاستخدام.")
            return
        if user_id in self.active_users:
            await message.answer("لديك طلب قيد المعالجة. انتظر اكتماله أولًا.")
            return
        try:
            url = extract_first_url(message.text)
            platform = identify_platform(url)
        except UnsupportedUrl as exc:
            await message.answer(str(exc))
            return
        if not self.rate_limiter.allow(user_id):
            await message.answer("وصلت إلى حد الاستخدام المؤقت. جرّب مرة أخرى لاحقًا.")
            return

        self.active_users.add(user_id)
        status = await message.answer(f"تم التعرف على {platform.label} — جارٍ تجهيز المقطع…")
        media = None
        try:
            async with self.download_slots:
                await self.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
                media = await self.downloader.download(url)
                await status.edit_text("اكتمل التنزيل — جارٍ إرسال الملف…")
                caption = self._caption(media.title, platform.label)
                try:
                    await message.answer_video(
                        video=FSInputFile(media.path),
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
            await status.edit_text(f"تعذر الإرسال: {exc}")
        except DownloadError as exc:
            await status.edit_text(str(exc))
        except Exception:
            logger.exception("Unexpected download job failure")
            await status.edit_text("حدث خطأ غير متوقع أثناء تجهيز المقطع.")
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
        await self.dispatcher.start_polling(
            self.bot,
            allowed_updates=self.dispatcher.resolve_used_update_types(),
        )
