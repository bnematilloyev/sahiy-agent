from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.schemas.process import ProcessRequest, ProcessResponse
from app.core.dependencies import get_chat_service
from app.services.chat_service import ChatService

router = APIRouter()


@router.post("/process", response_model=ProcessResponse)
async def process_message(
    payload: ProcessRequest,
    chat: ChatService = Depends(get_chat_service),
) -> ProcessResponse:
    result = await chat.reply(
        user_id=payload.user_id,
        text=payload.text,
        channel=str(payload.context.get("channel", "api")),
        metadata=payload.context,
        session_id=payload.session_id,
    )
    return ProcessResponse(
        type=result.response_type.value,
        text=result.text,
        ticket_id=result.ticket_id,
    )
