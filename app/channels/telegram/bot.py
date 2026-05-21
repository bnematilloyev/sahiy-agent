from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, Optional

from telegram import Update
from telegram.error import Forbidden, NetworkError, TelegramError, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.channels.telegram.keyboards import (
    inline_keyboard_from_extra,
    phone_request_keyboard,
    remove_keyboard,
)
from app.core.config import get_settings
from app.domain.pickup_present import parse_callback
from app.handlers.pickup_handler import PickupHandler
from app.infrastructure.sahiy_api.factory import get_sahiy_api_client
from app.infrastructure.sahiy_api.pickup_points import get_pickup_points_cached
from app.domain.customer_identity import PHONE_VERIFIED_TEXT, validate_uzbek_phone
from app.domain.order_refs import normalize_phone
from telegram.request import HTTPXRequest

from app.channels.ports import BotChannel
from app.core.config import Settings, get_settings
from app.core.database import run_in_session
from app.core.exceptions import ConfigurationError
from app.services.chat_service import ChatService
from app.services.factory import create_chat_service

logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "Assalomu alaykum! Men Sahiy yordamchi botman.\n\n"
    "Buyurtma holati uchun telefon raqamingizni yuboring.\n"
    "Topshirish punktlari: «qayerdan olib ketaman», «filial», «postomat» deb yozing.\n\n"
    "Yangi suhbat: /new"
)

PHONE_PROMPT_TEXT = (
    "Buyurtmangiz haqida ma'lumot olish uchun «Telefon raqamni yuborish» "
    "tugmasini bosing."
)

PHONE_SAVED_TEXT = (
    "Rahmat! Telefon raqamingiz saqlandi. Buyurtma yoki yetkazish haqida savolingizni yozing."
)

PHONE_WRONG_CONTACT_TEXT = (
    "Faqat o'zingizning telefon raqamingizni yuboring — «Telefon raqamni yuborish» tugmasini bosing."
)

FALLBACK_ERROR_TEXT = (
    "Hozir javob yubora olmadim (tarmoq xatosi). Iltimos, 1–2 daqiqadan keyin qayta yozing."
)

PHOTO_FALLBACK_TEXT = (
    "Rasmingiz qabul qilindi. Operator tez orada bog'lanadi: @sahiy_operator"
)


class TelegramBot(BotChannel):
    """Telegram UI — same ChatService as POST /process."""

    def __init__(self, settings: Settings) -> None:
        if not settings.telegram_bot_token:
            raise ConfigurationError("TELEGRAM_BOT_TOKEN is required")

        self._settings = settings
        timeout = float(settings.telegram_http_timeout_seconds)
        request = HTTPXRequest(
            connect_timeout=timeout,
            read_timeout=timeout,
            write_timeout=timeout,
            pool_timeout=timeout,
        )
        self._app = (
            Application.builder()
            .token(settings.telegram_bot_token)
            .request(request)
            .build()
        )
        self._send_retries = settings.telegram_send_retries
        self._typing_interval = settings.telegram_typing_interval_seconds
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("new", self._on_new))
        self._app.add_handler(MessageHandler(filters.CONTACT, self._on_contact))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text))
        self._app.add_handler(MessageHandler(filters.PHOTO, self._on_photo))
        self._app.add_handler(CallbackQueryHandler(self._on_pickup_callback, pattern=r"^pp_"))
        self._app.add_error_handler(self._on_error)

    async def start(self) -> None:
        settings = get_settings()
        ai = settings.resolved_ai_provider()
        emb = settings.resolved_embedding_provider()
        has_llm = bool(settings.ai_chain_providers())
        logger.info(
            "Starting Telegram bot (AI_PROVIDER=%s → chat=%s, embeddings=%s, rag_llm=%s)",
            settings.ai_provider,
            ai,
            emb,
            "yes" if has_llm else "no (FAQ copy only)",
        )
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

    async def stop(self) -> None:
        await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()

    async def _on_error(
        self, update: object, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        logger.exception("Telegram handler error: %s", context.error)

    async def _on_start(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message and update.effective_user:
            await self._safe_reply_text(
                update,
                WELCOME_TEXT,
                reply_markup=phone_request_keyboard(),
            )

    async def _on_new(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        user_id = str(update.effective_user.id)
        try:
            await self._with_chat(
                lambda chat: chat.reset_session(user_id=user_id, channel="telegram")
            )
            await self._safe_reply_text(
                update,
                "Yangi suhbat boshlandi.\n\n" + PHONE_PROMPT_TEXT,
                reply_markup=phone_request_keyboard(),
            )
        except Exception:
            logger.exception("reset_session failed")
            await self._safe_reply_text(update, "Xatolik yuz berdi. Keyinroq urinib ko'ring.")

    async def _on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user or not update.effective_chat:
            return

        user_id = str(update.effective_user.id)
        text = update.message.text or ""
        self._run_in_background(
            context,
            self._process_message(update, context, user_id, text),
            name=f"text-{user_id}",
        )

    async def _on_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user or not update.effective_chat:
            return

        user_id = str(update.effective_user.id)
        caption = update.message.caption or "[Rasm yuborildi]"
        self._run_in_background(
            context,
            self._process_message(
                update,
                context,
                user_id,
                f"MEDIA_PHOTO: {caption}",
                fallback_text=PHOTO_FALLBACK_TEXT,
                extra_metadata={"has_photo": True},
            ),
            name=f"photo-{user_id}",
        )

    async def _on_contact(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user or not update.message.contact:
            return

        contact = update.message.contact
        owner_id = update.effective_user.id
        if contact.user_id is not None and contact.user_id != owner_id:
            await self._safe_reply_text(
                update,
                PHONE_WRONG_CONTACT_TEXT,
                reply_markup=phone_request_keyboard(),
            )
            return

        raw_phone = contact.phone_number or ""
        phone = validate_uzbek_phone(raw_phone)
        if not phone:
            await self._safe_reply_text(
                update,
                PHONE_WRONG_CONTACT_TEXT,
                reply_markup=phone_request_keyboard(),
            )
            return

        user_id = str(owner_id)

        try:
            sahiy_user_id, error_text = await self._with_chat(
                lambda chat: chat.register_verified_phone(
                    user_id=user_id, phone=phone, channel="telegram"
                )
            )
            if error_text:
                await self._safe_reply_text(
                    update,
                    error_text,
                    reply_markup=phone_request_keyboard(),
                )
                return
            if sahiy_user_id is None:
                await self._safe_reply_text(
                    update,
                    PHONE_WRONG_CONTACT_TEXT,
                    reply_markup=phone_request_keyboard(),
                )
                return

            context.user_data["verified_phone"] = phone
            context.user_data["sahiy_user_id"] = sahiy_user_id
            logger.info(
                "Telegram user %s -> Sahiy user_id=%s (phone=%s)",
                user_id,
                sahiy_user_id,
                phone,
            )
        except Exception:
            logger.exception("register_verified_phone failed for user_id=%s", user_id)
            await self._safe_reply_text(update, FALLBACK_ERROR_TEXT)
            return

        await self._safe_reply_text(
            update,
            PHONE_VERIFIED_TEXT,
            reply_markup=remove_keyboard(),
        )

    @staticmethod
    def _build_metadata(
        update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> Dict[str, Any]:
        meta: Dict[str, Any] = {
            "telegram_chat_id": update.effective_chat.id if update.effective_chat else None,
            "telegram_username": update.effective_user.username if update.effective_user else None,
        }
        phone = context.user_data.get("verified_phone")
        if phone:
            meta["verified_phone"] = phone
        sahiy_user_id = context.user_data.get("sahiy_user_id")
        if sahiy_user_id is not None:
            meta["sahiy_user_id"] = sahiy_user_id
        return meta

    async def _on_pickup_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if not query or not query.data:
            return
        await query.answer()

        parsed = parse_callback(query.data)
        if parsed is None:
            return

        kind, value = parsed
        settings = get_settings()
        client = get_sahiy_api_client()
        if client is None:
            await query.edit_message_text("Topshirish punktlari vaqtincha mavjud emas.")
            return

        points = await get_pickup_points_cached(
            client, ttl_seconds=settings.pickup_points_cache_ttl_seconds
        )
        result = await PickupHandler.reply_for_callback(kind, value, points)
        markup = inline_keyboard_from_extra(result.channel_extra)
        try:
            await query.edit_message_text(result.text, reply_markup=markup)
        except TelegramError as exc:
            logger.warning("edit_message_text failed: %s", exc)
            await query.message.reply_text(result.text, reply_markup=markup)

    def _run_in_background(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        coro: Coroutine[Any, Any, None],
        *,
        name: str,
    ) -> None:
        context.application.create_task(coro, name=name)

    async def _process_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: str,
        text: str,
        *,
        fallback_text: str = FALLBACK_ERROR_TEXT,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not update.effective_chat:
            return

        metadata = self._build_metadata(update, context)
        if extra_metadata:
            metadata.update(extra_metadata)

        chat_id = update.effective_chat.id
        typing_task = asyncio.create_task(self._typing_loop(context, chat_id))
        reply_text = fallback_text
        try:
            result = await self._with_chat(
                lambda chat: chat.reply(
                    user_id=user_id,
                    text=text,
                    channel="telegram",
                    metadata=metadata,
                )
            )
            reply_text = result.text
            reply_markup = inline_keyboard_from_extra(getattr(result, "channel_extra", None))
        except Exception:
            logger.exception("ChatService.reply failed for user_id=%s", user_id)
            reply_markup = None
        finally:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

        sent = await self._safe_reply_text(update, reply_text, reply_markup=reply_markup)
        if not sent:
            logger.error("Could not deliver reply to Telegram for user_id=%s", user_id)

    async def _typing_loop(
        self, context: ContextTypes.DEFAULT_TYPE, chat_id: int
    ) -> None:
        try:
            while True:
                await self._try_typing(context, chat_id)
                await asyncio.sleep(self._typing_interval)
        except asyncio.CancelledError:
            raise

    async def _try_typing(
        self, context: ContextTypes.DEFAULT_TYPE, chat_id: int
    ) -> None:
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        except Forbidden:
            pass
        except (TimedOut, NetworkError) as exc:
            logger.warning("send_chat_action skipped (network): %s", exc)
        except TelegramError as exc:
            logger.warning("send_chat_action skipped: %s", exc)

    async def _safe_reply_text(
        self,
        update: Update,
        text: str,
        *,
        reply_markup: Any = None,
    ) -> bool:
        if not update.message:
            return False
        message = update.message
        user_id = update.effective_user.id if update.effective_user else "unknown"
        for attempt in range(1, self._send_retries + 1):
            try:
                await message.reply_text(text, reply_markup=reply_markup)
                return True
            except Forbidden:
                logger.info("User blocked bot, skipping reply user_id=%s", user_id)
                return False
            except (TimedOut, NetworkError) as exc:
                logger.warning(
                    "reply_text attempt %s/%s failed: %s",
                    attempt,
                    self._send_retries,
                    exc,
                )
                if attempt < self._send_retries:
                    await asyncio.sleep(1.5 * attempt)
            except TelegramError as exc:
                logger.warning("reply_text failed user_id=%s: %s", user_id, exc)
                return False
        return False

    async def _with_chat(self, callback: Callable[[ChatService], Coroutine[Any, Any, Any]]):
        return await run_in_session(
            lambda db: callback(create_chat_service(db)),
        )
