from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, Optional

from telegram import InputMediaPhoto, Update
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
from app.domain.order_list_menu import parse_order_menu_callback
from app.domain.reply_language import resolve_reply_language
from app.domain.pickup_present import parse_callback
from app.handlers.pickup_handler import PickupHandler
from app.infrastructure.sahiy_api.factory import get_sahiy_api_client
from app.infrastructure.sahiy_api.pickup_points import get_pickup_points_cached
from app.domain.customer_identity import phone_verified_text, resolve_contact_phone
from app.domain.order_refs import normalize_phone
from app.domain.reply_language import localize
from telegram.request import HTTPXRequest

from app.channels.ports import BotChannel
from app.core.config import Settings, get_settings
from app.core.database import run_in_session
from app.core.exceptions import ConfigurationError
from app.services.chat_service import ChatService
from app.services.factory import create_chat_service

logger = logging.getLogger(__name__)

_WELCOME: dict[str, str] = {
    "uz_lat": (
        "Assalomu alaykum! Men Sahiy yordamchi botman.\n\n"
        "Davom etish uchun Sahiy user ID yoki telefon raqamingizni yuboring:\n"
        "• user ID — masalan 111111\n"
        "• telefon — tugma yoki 998901234567\n\n"
        "Buyurtmalar: «zakazlarimni ko'rsat» — turini tugma bilan tanlaysiz.\n"
        "Topshirish punktlari: «filial», «postomat» deb yozing.\n\n"
        "Yangi suhbat: /new"
    ),
    "uz_cyrl": (
        "Ассалому алайкум! Мен Sahiy ёрдамчи ботман.\n\n"
        "Давом этиш учун Sahiy user ID ёки телефон рақамингизни юборинг:\n"
        "• user ID — масалан 111111\n"
        "• телефон — тугма ёки 998901234567\n\n"
        "Буюртмалар: «заказларимни кўрсат» — турини тугма билан танлайсиз.\n"
        "Топшириш пунктлари: «филиал», «постомат» деб ёзинг.\n\n"
        "Янги суҳбат: /new"
    ),
    "ru": (
        "Привет! Я бот-помощник Sahiy.\n\n"
        "Для продолжения отправьте Sahiy user ID или номер телефона:\n"
        "• user ID — например 111111\n"
        "• телефон — кнопка или 998901234567\n\n"
        "Заказы: напишите «мои заказы» — выберите тип кнопкой.\n"
        "Пункты выдачи: напишите «филиал» или «постомат».\n\n"
        "Новый диалог: /new"
    ),
    "en": (
        "Hello! I'm Sahiy assistant bot.\n\n"
        "To continue, send your Sahiy user ID or phone number:\n"
        "• user ID — e.g. 111111\n"
        "• phone — button or 998901234567\n\n"
        "Orders: write «show my orders» — select type with a button.\n"
        "Pickup points: write «branch» or «postamat».\n\n"
        "New chat: /new"
    ),
    "zh": (
        "您好！我是Sahiy助理机器人。\n\n"
        "请发送Sahiy用户ID或电话号码以继续：\n"
        "• 用户ID — 例如 111111\n"
        "• 电话 — 按钮或 998901234567\n\n"
        "订单：输入«显示我的订单» — 用按钮选择类型。\n"
        "取货点：输入«分支机构»或«自取柜»。\n\n"
        "新对话：/new"
    ),
}

_PHONE_PROMPT: dict[str, str] = {
    "uz_lat": "Sahiy user ID (masalan 111111) yoki telefon raqamingizni yuboring — «Telefon raqamni yuborish» tugmasi ham bo'ladi.",
    "uz_cyrl": "Sahiy user ID (масалан 111111) ёки телефон рақамингизни юборинг — «Телефон рақамни юбориш» тугмаси ҳам бўлади.",
    "ru": "Отправьте Sahiy user ID (например 111111) или номер телефона — также доступна кнопка «Отправить номер телефона».",
    "en": "Send your Sahiy user ID (e.g. 111111) or phone number — you can also use the «Send phone number» button.",
    "zh": "请发送Sahiy用户ID（例如111111）或电话号码 — 也可使用«发送电话号码»按钮。",
}

_PHONE_SAVED: dict[str, str] = {
    "uz_lat": "Rahmat! Telefon raqamingiz saqlandi. Buyurtma yoki yetkazish haqida savolingizni yozing.",
    "uz_cyrl": "Раҳмат! Телефон рақамингиз сақланди. Буюртма ёки етказиш ҳақида саволингизни ёзинг.",
    "ru": "Спасибо! Номер телефона сохранён. Напишите вопрос о заказе или доставке.",
    "en": "Thank you! Your phone number has been saved. Write your question about orders or delivery.",
    "zh": "谢谢！您的电话号码已保存。请提出关于订单或配送的问题。",
}

_PHONE_WRONG_CONTACT: dict[str, str] = {
    "uz_lat": "Telefon raqamini aniqlab bo'lmadi.\n\nSahiy user ID yozing (masalan 111111) yoki «Telefon raqamni yuborish» tugmasini bosing.",
    "uz_cyrl": "Телефон рақамини аниқлаб бўлмади.\n\nSahiy user ID ёзинг (масалан 111111) ёки «Телефон рақамни юбориш» тугмасини босинг.",
    "ru": "Не удалось определить номер телефона.\n\nНапишите Sahiy user ID (например 111111) или нажмите «Отправить номер телефона».",
    "en": "Could not determine phone number.\n\nWrite your Sahiy user ID (e.g. 111111) or press «Send phone number».",
    "zh": "无法确认电话号码。\n\n请输入Sahiy用户ID（例如111111）或点击«发送电话号码»。",
}

_FALLBACK_ERROR: dict[str, str] = {
    "uz_lat": "Hozir javob yubora olmadim (tarmoq xatosi). Iltimos, 1–2 daqiqadan keyin qayta yozing.",
    "uz_cyrl": "Ҳозир жавоб юбора олмадим (тармоқ хатоси). Илтимос, 1–2 дақиқадан кейин қайта ёзинг.",
    "ru": "Не могу отправить ответ сейчас (сетевая ошибка). Пожалуйста, напишите снова через 1–2 минуты.",
    "en": "Could not send a reply now (network error). Please write again in 1–2 minutes.",
    "zh": "暂时无法发送回复（网络错误）。请1–2分钟后重试。",
}

_PHOTO_FALLBACK: dict[str, str] = {
    "uz_lat": "Rasmingiz qabul qilindi. Operator tez orada bog'lanadi: @sahiy_operator",
    "uz_cyrl": "Расмингиз қабул қилинди. Оператор тез орада боғланади: @sahiy_operator",
    "ru": "Ваше изображение получено. Оператор свяжется с вами в ближайшее время: @sahiy_operator",
    "en": "Your image has been received. An operator will contact you shortly: @sahiy_operator",
    "zh": "您的图片已收到。操作员将尽快联系您：@sahiy_operator",
}


def _tg_lang(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    """Best-effort language from session or Telegram locale."""
    stored = context.user_data.get("reply_language") if context.user_data else None
    if stored:
        return stored
    lc = ""
    if update.effective_user:
        lc = (update.effective_user.language_code or "").lower()
    if lc.startswith("ru"):
        return "ru"
    if lc.startswith("zh"):
        return "zh"
    if lc.startswith("en"):
        return "en"
    return "uz_lat"


def _t(table: dict[str, str], lang: str) -> str:
    return table.get(lang) or table.get("uz_lat", "")


# UZ fallback constants for backward-compat references elsewhere in this file
WELCOME_TEXT = _t(_WELCOME, "uz_lat")
PHONE_PROMPT_TEXT = _t(_PHONE_PROMPT, "uz_lat")
PHONE_SAVED_TEXT = _t(_PHONE_SAVED, "uz_lat")
PHONE_WRONG_CONTACT_TEXT = _t(_PHONE_WRONG_CONTACT, "uz_lat")
FALLBACK_ERROR_TEXT = _t(_FALLBACK_ERROR, "uz_lat")
PHOTO_FALLBACK_TEXT = _t(_PHOTO_FALLBACK, "uz_lat")


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
        self._app.add_handler(CallbackQueryHandler(self._on_order_menu_callback, pattern=r"^ord_"))
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
            lang = _tg_lang(update, context)
            await self._safe_reply_text(
                update,
                _t(_WELCOME, lang),
                reply_markup=phone_request_keyboard(),
            )

    async def _on_new(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not update.message or not update.effective_user:
            return
        lang = _tg_lang(update, context)
        _new_chat_started: dict[str, str] = {
            "uz_lat": "Yangi suhbat boshlandi.\n\n",
            "uz_cyrl": "Янги суҳбат босhlandi.\n\n",
            "ru": "Новый диалог начат.\n\n",
            "en": "New chat started.\n\n",
            "zh": "新对话已开始。\n\n",
        }
        _err_retry: dict[str, str] = {
            "uz_lat": "Xatolik yuz berdi. Keyinroq urinib ko'ring.",
            "uz_cyrl": "Хатолик юз берди. Кейинроқ уриниб кўринг.",
            "ru": "Произошла ошибка. Попробуйте позже.",
            "en": "An error occurred. Please try again later.",
            "zh": "发生错误。请稍后重试。",
        }
        user_id = str(update.effective_user.id)
        try:
            await self._with_chat(
                lambda chat: chat.reset_session(user_id=user_id, channel="telegram")
            )
            await self._safe_reply_text(
                update,
                _t(_new_chat_started, lang) + _t(_PHONE_PROMPT, lang),
                reply_markup=phone_request_keyboard(),
            )
        except Exception:
            logger.exception("reset_session failed")
            await self._safe_reply_text(update, _t(_err_retry, lang))

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
        lang = _tg_lang(update, context)
        caption = update.message.caption or "[Rasm yuborildi]"
        self._run_in_background(
            context,
            self._process_message(
                update,
                context,
                user_id,
                f"MEDIA_PHOTO: {caption}",
                fallback_text=_t(_PHOTO_FALLBACK, lang),
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
            await self._safe_reply_text(
                update,
                _t(_PHONE_WRONG_CONTACT, lang),
                reply_markup=phone_request_keyboard(),
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
                await self._safe_reply_text(
                    update,
                    error_text,
                    reply_markup=phone_request_keyboard(),
                )
                return
            if sahiy_user_id is None:
                await self._safe_reply_text(
                    update,
                    _t(_PHONE_WRONG_CONTACT, lang),
                    reply_markup=phone_request_keyboard(),
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
            await self._safe_reply_text(update, _t(_FALLBACK_ERROR, lang))
            return

        await self._safe_reply_text(
            update,
            phone_verified_text(lang),
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
        _lang = str(metadata.get("reply_language") or "uz_lat")
        chat_id = query.message.chat_id if query.message else None
        typing_task = None
        if chat_id is not None:
            typing_task = asyncio.create_task(self._typing_loop(context, chat_id))

        reply_text = _t(_FALLBACK_ERROR, _lang)
        reply_markup = None
        photo_urls_menu: list = []
        extra_menu: Dict[str, Any] = {}
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
            extra_menu = getattr(result, "channel_extra", {}) or {}
            reply_markup = inline_keyboard_from_extra(extra_menu)
            photo_urls_menu = extra_menu.get("media_photos") or []
            context.user_data["reply_language"] = metadata.get("reply_language")
        except Exception:
            logger.exception("order menu callback failed user_id=%s", user_id)
        finally:
            if typing_task is not None:
                typing_task.cancel()
                try:
                    await typing_task
                except asyncio.CancelledError:
                    pass

        if query.message:
            try:
                await query.message.reply_text(reply_text, reply_markup=reply_markup)
                for follow_up in extra_menu.get("telegram_messages") or []:
                    if follow_up:
                        await query.message.reply_text(str(follow_up))
            except TelegramError as exc:
                logger.warning("order menu reply failed: %s", exc)

        if photo_urls_menu and update.message:
            await self._safe_send_media_group(update, photo_urls_menu)

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
        fallback_text: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not update.effective_chat:
            return

        metadata = self._build_metadata(update, context)
        if extra_metadata:
            metadata.update(extra_metadata)
        metadata["reply_language"] = resolve_reply_language(text, metadata, None)
        _lang = str(metadata.get("reply_language") or "uz_lat")
        if fallback_text is None:
            fallback_text = _t(_FALLBACK_ERROR, _lang)

        chat_id = update.effective_chat.id
        typing_task = asyncio.create_task(self._typing_loop(context, chat_id))
        reply_text = fallback_text
        reply_markup = None
        photo_urls: list = []
        extra: Dict[str, Any] = {}
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
            reply_markup = inline_keyboard_from_extra(extra)
            photo_urls = extra.get("media_photos") or []
            context.user_data["reply_language"] = metadata.get("reply_language")
        except Exception:
            logger.exception("ChatService.reply failed for user_id=%s", user_id)
        finally:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

        sent = await self._safe_reply_text(update, reply_text, reply_markup=reply_markup)
        if not sent:
            logger.error("Could not deliver reply to Telegram for user_id=%s", user_id)
            return

        for follow_up in extra.get("telegram_messages") or []:
            if follow_up:
                await self._safe_reply_text(update, str(follow_up))

        if photo_urls and update.message:
            await self._safe_send_media_group(update, photo_urls)

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

    async def _safe_send_media_group(
        self,
        update: Update,
        photo_urls: list,
    ) -> None:
        """Send up to 10 product images as a Telegram media group (album)."""
        if not update.message or not photo_urls:
            return
        urls = [u for u in photo_urls if u][:10]
        if not urls:
            return
        try:
            media = [InputMediaPhoto(media=url) for url in urls]
            await update.message.reply_media_group(media=media)
        except TelegramError as exc:
            logger.warning("media_group send failed: %s", exc)
            # fallback: send first image as single photo
            try:
                await update.message.reply_photo(photo=urls[0])
            except TelegramError as exc2:
                logger.warning("single photo fallback failed: %s", exc2)

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
