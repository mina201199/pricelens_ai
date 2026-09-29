from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from price_lens.ai.service import AskService, get_ask_service
from price_lens.db.session import get_db_session
from price_lens.schemas.ask import AskRequest, AskResponse

router = APIRouter(prefix="/api/v1", tags=["controlled AI"])
DatabaseSession = Annotated[Session, Depends(get_db_session)]
AskServiceDependency = Annotated[AskService, Depends(get_ask_service)]


@router.post("/ask", response_model=AskResponse)
def ask(
    payload: AskRequest,
    session: DatabaseSession,
    service: AskServiceDependency,
) -> AskResponse:
    return service.answer(session, payload.question.strip())
