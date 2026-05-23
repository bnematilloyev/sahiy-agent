from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, Optional

from telegram import Message, Update
from telegram.error import Forbidden, TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from app.channels.ports import BotChannel
from app.channels.telegram.delivery import (
    ReplyPayload,
    deliver_follow_ups_and_media,
    deliver_product_search_to_message,
    deliver_to_update,
)
from app.channels.telegram.i18n_strings import (
    ERR_RETRY,
    FALLBACK_ERROR,
    NEW_CHAT_STARTED,
    PHONE_PROMPT,
    PHONE_SAVED,
    PHONE_WRONG_CONTACT,
    PHOTO_FALLBACK,
    WELCOME,
    t,
)
from app.channels.telegram.keyboards import (
    inline_keyboard_from_extra,
    main_menu_keyboard,
    phone_request_keyboard,
)
from app.channels.telegram.messenger import TelegramMessenger
from app.channels.telegram.streaming import SmoothStreamSession, StreamConfig
from app.channels.telegram.typing_indicator import typing_indicator
from app.core.config import Settings, get_settings
from app.core.database import run_in_session
from app.core.exceptions import ConfigurationError
from app.domain.customer_identity import phone_verified_text, resolve_contact_phone
from app.domain.language_menu import (
    LANGUAGE_PICKER_PROMPT,
    build_language_menu_extra,
    parse_language_callback,
)
from app.domain.order_list_menu import parse_order_menu_callback
from app.domain.product_search_present import (
    format_product_caption,
    product_buy_keyboard_extra,
    product_search_see_all_keyboard,
)
from app.domain.product_search_intent import is_product_search_intent
from app.domain.reply_language import resolve_reply_language
from app.domain.category_present import parse_category_callback
from app.domain.category_intent import is_category_browse_intent
from app.domain.pickup_present import parse_callback
from app.domain.telegram_menu import (
    build_rating_inline_extra,
    is_main_menu_label,
    localize_menu,
    match_menu_action,
    parse_rating_callback,
    RATING_PROMPT,
    RATING_THANKS,
    MENU_CALLBACK,
    MENU_HELP,
    PRODUCT_SEARCH_EMPTY,
    PRODUCT_SEARCH_ERROR,
    PRODUCT_SEARCH_HEADER,
    PRODUCT_SEARCH_PROMPT,
    PRODUCT_SEARCH_TOO_SHORT,
)
from app.handlers.category_browse_handler import CategoryBrowseHandler
from app.handlers.pickup_handler import PickupHandler
from app.services.chat_service import ChatService
from app.services.factory import create_chat_service
from app.services.product_search_service import ProductSearchService, ProductSearchStatus

logger = logging.getLogger(__name__)

STREAM_PLACEHOLDER = "⏳"

# Backward-compatible exports for tests/scripts
WELCOME_TEXT = t(WELCOME, "uz_lat")
PHONE_PROMPT_TEXT = t(PHONE_PROMPT, "uz_lat")
PHONE_SAVED_TEXT = t(PHONE_SAVED, "uz_lat")
PHONE_WRONG_CONTACT_TEXT = t(PHONE_WRONG_CONTACT, "uz_lat")
FALLBACK_ERROR_TEXT = t(FALLBACK_ERROR, "uz_lat")
PHOTO_FALLBACK_TEXT = t(PHOTO_FALLBACK, "uz_lat")


def _tg_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    if context.user_data:
        stored = context.user_data.get("reply_language")
        if stored:
            return str(stored)
    return "uz_lat"


class TelegramBot(BotChannel):
    """Telegram UI — same ChatService as POST /process."""

    def __init__(self, settings: Settings) -> None:
        if not settings.telegram_bot_token:
            raise ConfigurationError("TELEGRAM_BOT_TOKEN is required")

        self._settings = settings
        self._messenger = TelegramMessenger(send_retries=settings.telegram_send_retries)
        self._stream_config = StreamConfig(
            chars_per_tick=settings.telegram_stream_edit_min_chars,
            tick_delay=settings.telegram_stream_edit_delay_seconds,
            min_edit_gap=settings.telegram_stream_min_edit_gap_seconds,
            show_cursor=settings.telegram_stream_show_cursor,
        )
        self._pickup = PickupHandler()
        self._product_search = ProductSearchService(settings)
        self._category = CategoryBrowseHandler(product_search=self._product_search)

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
        self._typing_interval = settings.telegram_typing_interval_seconds
        self._stream_enabled = settings.telegram_stream_enabled

        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CommandHandler("new", self._on_new))
        self._app.add_handler(MessageHandler(filters.CONTACT, self._on_contact))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_text))
        self._app.add_handler(MessageHandler(filters.PHOTO, self._on_photo))
        self._app.add_handler(CallbackQueryHandler(self._on_language_callback, pattern=r"^lang_"))
        self._app.add_handler(CallbackQueryHandler(self._on_rating_callback, pattern=r"^rate_[1-5]$"))
        self._app.add_handler(CallbackQueryHandler(self._on_pickup_callback, pattern=r"^pp_"))
        self._app.add_handler(CallbackQueryHandler(self._on_order_menu_callback, pattern=r"^ord_"))
        self._app.add_handler(CallbackQueryHandler(self._on_category_callback, pattern=r"^ct_"))
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

    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message and update.effective_user:
            markup = inline_keyboard_from_extra(build_language_menu_extra())
            await self._messenger.reply_text(
                update,
                LANGUAGE_PICKER_PROMPT,
                reply_markup=markup,
                attach_main_menu=False,
            )

    async def _on_language_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if not query or not query.data:
            return
        lang = parse_language_callback(query.data)
        if not lang:
            return
        if context.user_data is not None:
            context.user_data["reply_language"] = lang
        await query.answer()
        welcome = t(WELCOME, lang)
        try:
            await query.edit_message_text(welcome)
        except TelegramError as exc:
            logger.warning("edit_message_text (language) failed: %s", exc)
            if query.message:
                await query.message.reply_text(welcome)
        if query.message:
            verified = bool(context.user_data and context.user_data.get("verified_phone"))
            if verified:
                await query.message.reply_text(
                    t(WELCOME, lang).split("\n\n")[0],
                    reply_markup=main_menu_keyboard(lang),
                )
            else:
                await query.message.reply_text(
                    t(PHONE_PROMPT, lang),
                    reply_markup=phone_request_keyboard(lang),
                )

    async def _on_rating_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if not query or not query.data or not update.effective_user:
            return
        stars = parse_rating_callback(query.data)
        if stars is None:
            return
        await query.answer()
        lang = _tg_lang(update, context)
        user_id = str(update.effective_user.id)
        logger.info("telegram_service_rating user_id=%s stars=%s", user_id, stars)
        if context.user_data is not None:
            context.user_data["rated_this_session"] = True
            context.user_data["rating_prompt_sent"] = True
            self._invalidate_rating_schedule(context.user_data)
        thanks = localize_menu(RATING_THANKS, lang, stars=str(stars))
        try:
            await query.edit_message_text(thanks)
        except TelegramError:
            if query.message:
                await query.message.reply_text(
                    thanks,
                    reply_markup=main_menu_keyboard(lang),
                )

    async def _on_new(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        lang = _tg_lang(update, context)
        user_id = str(update.effective_user.id)
        if context.user_data is not None:
            context.user_data.pop("rated_this_session", None)
            context.user_data.pop("rating_prompt_sent", None)
            context.user_data.pop("awaiting_product_search", None)
            self._invalidate_rating_schedule(context.user_data)
        try:
            await self._with_chat(
                lambda chat: chat.reset_session(user_id=user_id, channel="telegram")
            )
            verified = bool(context.user_data.get("verified_phone"))
            markup = (
                main_menu_keyboard(lang) if verified else phone_request_keyboard(lang)
            )
            body = t(NEW_CHAT_STARTED, lang)
            if not verified:
                body += t(PHONE_PROMPT, lang)
            await self._messenger.reply_text(
                update,
                body,
                reply_markup=markup,
                attach_main_menu=False,
            )
        except Exception:
            logger.exception("reset_session failed")
            await self._messenger.reply_text(update, t(ERR_RETRY, lang))

    async def _on_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user or not update.effective_chat:
            return

        user_id = str(update.effective_user.id)
        text = update.message.text or ""
        lang = _tg_lang(update, context)

        if context.user_data is not None:
            self._invalidate_rating_schedule(context.user_data)

        if is_main_menu_label(text):
            action = match_menu_action(text, lang)
            if action:
                await self._handle_menu_action(update, context, action, lang)
                return

        if context.user_data and context.user_data.get("awaiting_product_search"):
            await self._handle_product_search_query(update, context, text, lang)
            return

        self._run_in_background(
            context,
            self._process_message(update, context, user_id, text),
            name=f"text-{user_id}",
        )

    async def _handle_menu_action(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        action: str,
        lang: str,
    ) -> None:
        if action == "new_chat":
            await self._on_new(update, context)
            return
        if action == "language":
            markup = inline_keyboard_from_extra(build_language_menu_extra())
            await self._messenger.reply_text(
                update,
                LANGUAGE_PICKER_PROMPT,
                reply_markup=markup,
                lang=lang,
                attach_main_menu=False,
            )
            return
        if action == "help":
            await self._messenger.reply_text(
                update,
                localize_menu(MENU_HELP, lang),
                lang=lang,
            )
            return
        if action == "callback":
            await self._messenger.reply_text(
                update,
                localize_menu(MENU_CALLBACK, lang),
                lang=lang,
            )
            return
        if action == "product_search":
            if context.user_data is not None:
                context.user_data["awaiting_product_search"] = True
            await self._messenger.reply_text(
                update,
                localize_menu(PRODUCT_SEARCH_PROMPT, lang),
                lang=lang,
            )
            return

    async def _handle_product_search_query(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        text: str,
        lang: str,
    ) -> None:
        if context.user_data is not None:
            context.user_data["awaiting_product_search"] = False

        if not update.effective_chat:
            return

        chat_id = update.effective_chat.id
        async with typing_indicator(
            context, chat_id, interval_seconds=self._typing_interval
        ):
            outcome = await self._product_search.search(text, lang)

        if outcome.status == ProductSearchStatus.TOO_SHORT:
            if context.user_data is not None:
                context.user_data["awaiting_product_search"] = True
            await self._messenger.reply_text(
                update,
                localize_menu(PRODUCT_SEARCH_TOO_SHORT, lang),
                lang=lang,
            )
            return

        if outcome.status == ProductSearchStatus.NOT_CONFIGURED:
            await self._messenger.reply_text(
                update,
                localize_menu(PRODUCT_SEARCH_ERROR, lang),
                lang=lang,
            )
            return

        if outcome.status == ProductSearchStatus.EMPTY:
            await self._messenger.reply_text(
                update,
                localize_menu(PRODUCT_SEARCH_EMPTY, lang),
                lang=lang,
            )
            return

        if outcome.status == ProductSearchStatus.ERROR:
            logger.warning("product search failed keyword=%r", (text or "")[:40])
            await self._messenger.reply_text(
                update,
                localize_menu(PRODUCT_SEARCH_ERROR, lang),
                lang=lang,
            )
            return

        header = localize_menu(
            PRODUCT_SEARCH_HEADER,
            lang,
            keyword=outcome.display_keyword,
            count=str(len(outcome.items)),
        )
        await self._messenger.reply_text(update, header, lang=lang)

        rate = outcome.cny_to_uzs
        for index, item in enumerate(outcome.items, start=1):
            caption = format_product_caption(item, lang, cny_to_uzs=rate, index=index)
            buy_markup = inline_keyboard_from_extra(
                product_buy_keyboard_extra(item, lang)
            )
            await self._messenger.send_product_photo(
                update,
                item.pic_url,
                caption,
                reply_markup=buy_markup,
                lang=lang,
            )

        see_all_kw = (outcome.api_keyword or outcome.display_keyword or text).strip()
        if see_all_kw:
            see_all_markup = inline_keyboard_from_extra(
                product_search_see_all_keyboard(
                    see_all_kw,
                    lang,
                    page_size=self._settings.sahiy_product_search_see_all_page_size,
                )
            )
            await self._messenger.reply_text(
                update,
                "👇",
                reply_markup=see_all_markup,
                lang=lang,
            )

        if update.effective_chat and context.user_data is not None:
            self._schedule_rating_after_inactivity(
                context,
                update.effective_chat.id,
                lang,
            )

    async def _on_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user or not update.effective_chat:
            return

        user_id = str(update.effective_user.id)
        lang = _tg_lang(update, context)
        caption = update.message.caption or "[Rasm yuborildi]"
        self._run_in_background(
            context,
            self._process_message(
                update,
                context,
                user_id,
                f"MEDIA_PHOTO: {caption}",
                fallback_text=t(PHOTO_FALLBACK, lang),
                extra_metadata={"has_photo": True},
            ),
            name=f"photo-{user_id}",
        )

    async def _on_contact(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user or not update.message.contact:
            return

        contact = update.message.contact
        owner_id = update.effective_user.id
        raw_phone = contact.phone_number or ""
        lang = _tg_lang(update, context)
        phone = resolve_contact_phone(raw_phone)
        if not phone:
            await self._messenger.reply_text(
                update,
                t(PHONE_WRONG_CONTACT, lang),
                reply_markup=phone_request_keyboard(lang),
            )
            return

        user_id = str(owner_id)
        foreign_contact = (
            contact.user_id is not None and contact.user_id != owner_id
        )

        try:
            sahiy_user_id, error_text = await self._with_chat(
                lambda chat: chat.register_verified_phone(
                    user_id=user_id, phone=phone, channel="telegram"
                )
            )
            if error_text:
                await self._messenger.reply_text(
                    update,
                    error_text,
                    reply_markup=phone_request_keyboard(lang),
                )
                return
            if sahiy_user_id is None:
                await self._messenger.reply_text(
                    update,
                    t(PHONE_WRONG_CONTACT, lang),
                    reply_markup=phone_request_keyboard(lang),
                )
                return

            context.user_data["verified_phone"] = phone
            context.user_data["sahiy_user_id"] = sahiy_user_id
            logger.info(
                "Telegram user %s -> Sahiy user_id=%s (phone=%s, foreign_contact=%s)",
                user_id,
                sahiy_user_id,
                phone,
                foreign_contact,
            )
        except Exception:
            logger.exception("register_verified_phone failed for user_id=%s", user_id)
            await self._messenger.reply_text(update, t(FALLBACK_ERROR, lang))
            return

        await self._messenger.reply_text(
            update,
            phone_verified_text(lang),
            reply_markup=main_menu_keyboard(lang),
            attach_main_menu=False,
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
        reply_language = context.user_data.get("reply_language")
        if reply_language:
            meta["reply_language"] = reply_language
        return meta

    async def _on_order_menu_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if not query or not query.data or not update.effective_user:
            return

        synthetic_text = parse_order_menu_callback(query.data)
        if not synthetic_text:
            return

        await query.answer()
        user_id = str(update.effective_user.id)
        self._run_in_background(
            context,
            self._process_order_menu_choice(
                update, context, user_id, synthetic_text, query=query
            ),
            name=f"ord-{user_id}",
        )

    async def _process_order_menu_choice(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user_id: str,
        text: str,
        *,
        query: Any,
    ) -> None:
        metadata = self._build_metadata(update, context)
        metadata["reply_language"] = resolve_reply_language(text, metadata, None)
        lang = str(metadata.get("reply_language") or "uz_lat")
        chat_id = query.message.chat_id if query.message else None

        reply_text = t(FALLBACK_ERROR, lang)
        extra: Dict[str, Any] = {}

        if chat_id is not None:
            async with typing_indicator(
                context, chat_id, interval_seconds=self._typing_interval
            ):
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
                    extra = getattr(result, "channel_extra", {}) or {}
                    context.user_data["reply_language"] = metadata.get("reply_language")
                except Exception:
                    logger.exception("order menu callback failed user_id=%s", user_id)
        else:
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
                extra = getattr(result, "channel_extra", {}) or {}
            except Exception:
                logger.exception("order menu callback failed user_id=%s", user_id)

        payload = ReplyPayload.from_channel_extra(reply_text, extra)
        if query.message:
            await self._messenger.reply_to_message(
                query.message,
                payload.text,
                reply_markup=payload.reply_markup,
            )
            for follow_up in payload.follow_up_messages or []:
                await self._messenger.reply_to_message(query.message, follow_up)

        if payload.photo_urls and update.message:
            await self._messenger.send_media_group(update, payload.photo_urls)

    async def _on_category_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        query = update.callback_query
        if not query or not query.data:
            return
        await query.answer()

        parsed = parse_category_callback(query.data)
        if parsed is None:
            return

        action, category_id, back_target = parsed
        lang = _tg_lang(update, context)
        result = await self._category.reply_for_callback(
            action, category_id, back_target, lang
        )
        extra = getattr(result, "channel_extra", {}) or {}
        payload = ReplyPayload.from_channel_extra(result.text, extra)

        if payload.product_search_items and query.message:
            try:
                await query.edit_message_text(self._messenger.clip_text(result.text))
            except TelegramError as exc:
                logger.warning("category callback edit failed: %s", exc)
                await self._messenger.reply_to_message(query.message, result.text)
            await deliver_product_search_to_message(
                query.message, self._messenger, payload, lang=lang
            )
            return

        markup = inline_keyboard_from_extra(extra)
        try:
            await query.edit_message_text(result.text, reply_markup=markup)
        except TelegramError as exc:
            logger.warning("category edit_message_text failed: %s", exc)
            if query.message:
                await query.message.reply_text(result.text, reply_markup=markup)

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
        result = await self._pickup.reply_for_callback(kind, value)
        markup = inline_keyboard_from_extra(result.channel_extra)
        try:
            await query.edit_message_text(result.text, reply_markup=markup)
        except TelegramError as exc:
            logger.warning("edit_message_text failed: %s", exc)
            if query.message:
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
        fallback_text: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not update.effective_chat:
            return

        metadata = self._build_metadata(update, context)
        if extra_metadata:
            metadata.update(extra_metadata)
        metadata["reply_language"] = resolve_reply_language(text, metadata, None)
        lang = str(metadata.get("reply_language") or "uz_lat")
        if fallback_text is None:
            fallback_text = t(FALLBACK_ERROR, lang)

        chat_id = update.effective_chat.id
        use_stream = (
            self._stream_enabled
            and update.message is not None
            and not is_product_search_intent(text)
            and not is_category_browse_intent(text)
        )
        sent_message: Optional[Message] = None
        stream_session: Optional[SmoothStreamSession] = None

        reply_text = fallback_text
        extra: Dict[str, Any] = {}

        if use_stream:
            sent_message = await self._messenger.reply_text(
                update, STREAM_PLACEHOLDER, attach_main_menu=False
            )
            if sent_message is None:
                return
            stream_session = SmoothStreamSession(
                sent_message, self._messenger, self._stream_config
            )

        async def on_stream(accumulated: str) -> None:
            if stream_session is not None:
                await stream_session.enqueue(accumulated)

        async with typing_indicator(
            context, chat_id, interval_seconds=self._typing_interval
        ):
            try:
                result = await self._with_chat(
                    lambda chat: chat.reply(
                        user_id=user_id,
                        text=text,
                        channel="telegram",
                        metadata=metadata,
                        on_stream=on_stream if use_stream else None,
                    )
                )
                reply_text = result.text
                extra = getattr(result, "channel_extra", {}) or {}
                context.user_data["reply_language"] = metadata.get("reply_language")
            except Exception:
                logger.exception("ChatService.reply failed for user_id=%s", user_id)
            finally:
                if stream_session is not None:
                    final_text = self._messenger.clip_text(reply_text) or t(
                        FALLBACK_ERROR, lang
                    )
                    await stream_session.finish(final_text)

        payload = ReplyPayload.from_channel_extra(reply_text, extra)

        has_follow_ups = bool(
            payload.follow_up_messages
            or payload.photo_urls
            or payload.product_search_items
        )

        if use_stream and sent_message is not None:
            delivered = await deliver_to_update(
                update,
                self._messenger,
                payload,
                lang=lang,
                use_stream=True,
                stream_message=sent_message,
            )
            if not delivered and not has_follow_ups:
                logger.error(
                    "Could not deliver streamed reply to Telegram for user_id=%s",
                    user_id,
                )
                return
        else:
            delivered = await deliver_to_update(
                update, self._messenger, payload, lang=lang
            )
            if not delivered and not has_follow_ups:
                logger.error(
                    "Could not deliver reply to Telegram for user_id=%s", user_id
                )
                return

        await deliver_follow_ups_and_media(update, self._messenger, payload, lang=lang)

        if update.effective_chat and context.user_data is not None:
            self._schedule_rating_after_inactivity(
                context,
                update.effective_chat.id,
                lang,
            )

    @staticmethod
    def _cancel_rating_task(user_data: Optional[Dict[str, Any]]) -> None:
        if not user_data:
            return
        task = user_data.pop("rating_task", None)
        if task is not None and not task.done():
            task.cancel()

    @staticmethod
    def _invalidate_rating_schedule(user_data: Optional[Dict[str, Any]]) -> None:
        if not user_data:
            return
        user_data["rating_schedule_gen"] = int(user_data.get("rating_schedule_gen") or 0) + 1
        TelegramBot._cancel_rating_task(user_data)

    def _schedule_rating_after_inactivity(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        lang: str,
    ) -> None:
        user_data = context.user_data
        if not user_data:
            return
        if user_data.get("rated_this_session") or user_data.get("rating_prompt_sent"):
            return

        delay = float(self._settings.telegram_rating_inactivity_seconds)
        if delay <= 0:
            return

        self._cancel_rating_task(user_data)
        generation = int(user_data.get("rating_schedule_gen") or 0)

        async def _send_rating_when_idle() -> None:
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return
            if int(user_data.get("rating_schedule_gen") or 0) != generation:
                return
            if user_data.get("rated_this_session") or user_data.get("rating_prompt_sent"):
                return
            rating_markup = inline_keyboard_from_extra(build_rating_inline_extra())
            if rating_markup is None:
                return
            user_data["rating_prompt_sent"] = True
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=localize_menu(RATING_PROMPT, lang),
                    reply_markup=rating_markup,
                )
            except Forbidden:
                pass
            except TelegramError as exc:
                logger.warning("delayed rating prompt failed chat_id=%s: %s", chat_id, exc)

        user_data["rating_task"] = self._app.create_task(
            _send_rating_when_idle(),
            name=f"rating-{chat_id}",
        )

    async def _with_chat(self, callback: Callable[[ChatService], Coroutine[Any, Any, Any]]):
        return await run_in_session(
            lambda db: callback(create_chat_service(db)),
        )
