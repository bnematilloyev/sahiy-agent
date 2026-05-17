from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.error import NetworkError, TelegramError, TimedOut
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.request import HTTPXRequest

from app.channels.ports import BotChannel
from app.core.config import Settings
from app.core.database import get_session_factory
from app.core.exceptions import ConfigurationError
from app.services.factory import create_chat_service

logger = logging.getLogger(__name__)

WELCOME_TEXT = (
    "Assalomu alaykum! Men Sahiy yordamchi botman.\n\n"
    "Savolingizni yozing — yetkazish, to'lov, buyurtma holati yoki "
    "shikoyat bo'yicha yordam beraman.\n\n"
    "Yangi suhbat: /new"
)

FALLBACK_ERROR_TEXT = (
    "Hozir javob yubora olmadim (tarmoq xatosi). Iltimos, 1–2 daqiqadan keyin qayta yozing."
)


class TelegramBot(BotChannel):
    """Telegram UI — same ChatService as POST /process."""

    def __init__(self, settings: Settings) -> None:
        if not settings.telegram_bot_token:
            raise ConfigurationError("TELEGRAM_BOT_TOKEN is required")

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
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("new", self._on_new))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text))
        self._app.add_error_handler(self._on_error)

    # 2. Rasm kelganda ishlaydigan yangi metod
    async def _on_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user or not update.effective_chat:
            return

        user_id = str(update.effective_user.id)
        # Rasm bilan birga yozilgan matn (caption) bormi?
        caption = update.message.caption or "[Rasm yuborildi]"

        await self._try_typing(context, update.effective_chat.id)

        try:
            # Bazada ticket ochish uchun ChatService.reply ni chaqiramiz
            # Manual ravishda ticket ochish uchun mantiq:
            result = await self._with_chat(
                lambda chat: chat.reply(
                    user_id=user_id,
                    text=f"MEDIA_PHOTO: {caption}",  # AI ga rasm kelganini bildirish
                    channel="telegram",
                    metadata={"has_photo": True}
                )
            )
            # prompts.py dagi BROKEN_ITEM_ACK yoki shunga o'xshash ticket xabarini yuborish
            # Agar ChatService ticket ochsa, result.ticket_id to'lgan bo'ladi
            reply_text = result.text
        except Exception:
            logger.exception("Photo handling failed for user_id=%s", user_id)
            reply_text = "Rasmingiz qabul qilindi. Operator tez orada bog'lanadi: @sahiy_operator"

        await self._safe_reply_text(update, reply_text)

    async def start(self) -> None:
        from app.core.config import get_settings

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
            await self._safe_reply_text(update, WELCOME_TEXT)

    async def _on_new(self, update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        user_id = str(update.effective_user.id)
        try:
            await self._with_chat(
                lambda chat: chat.reset_session(user_id=user_id, channel="telegram")
            )
            await self._safe_reply_text(update, "Yangi suhbat boshlandi. Savolingizni yozing.")
        except Exception:
            logger.exception("reset_session failed")
            await self._safe_reply_text(update, "Xatolik yuz berdi. Keyinroq urinib ko'ring.")

    async def _on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user or not update.effective_chat:
            return

        user_id = str(update.effective_user.id)
        text = update.message.text or ""
        meta = {
            "telegram_chat_id": update.effective_chat.id,
            "telegram_username": update.effective_user.username,
        }

        await self._try_typing(context, update.effective_chat.id)

        reply_text = FALLBACK_ERROR_TEXT
        try:
            result = await self._with_chat(
                lambda chat: chat.reply(
                    user_id=user_id,
                    text=text,
                    channel="telegram",
                    metadata=meta,
                )
            )
            reply_text = result.text
        except Exception:
            logger.exception("ChatService.reply failed for user_id=%s", user_id)

        sent = await self._safe_reply_text(update, reply_text)
        if not sent:
            logger.error("Could not deliver reply to Telegram for user_id=%s", user_id)

    async def _try_typing(
        self, context: ContextTypes.DEFAULT_TYPE, chat_id: int
    ) -> None:
        try:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        except (TimedOut, NetworkError) as exc:
            logger.warning("send_chat_action skipped (network): %s", exc)
        except TelegramError as exc:
            logger.warning("send_chat_action skipped: %s", exc)

    async def _safe_reply_text(self, update: Update, text: str) -> bool:
        if not update.message:
            return False
        message = update.message
        for attempt in range(1, self._send_retries + 1):
            try:
                await message.reply_text(text)
                return True
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
                logger.exception("reply_text failed: %s", exc)
                return False
        return False

    async def _with_chat(self, callback):
        factory = get_session_factory()
        async with factory() as db:
            chat = create_chat_service(db)
            try:
                result = await callback(chat)
                await db.commit()
                return result
            except Exception:
                await db.rollback()
                raise

