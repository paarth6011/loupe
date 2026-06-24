from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Account
from app.schemas.auth import CurrentUser
from app.schemas.summarizer import SummarizerKeyIn, SummarizerKeyOut, masked_key

router = APIRouter(prefix="/summarizer", tags=["summarizer"])


def _account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:  # pragma: no cover - the authed account always exists
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="account not found"
        )
    return account


@router.get("/key", response_model=SummarizerKeyOut)
def get_summarizer_key(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SummarizerKeyOut:
    """Whether this tenant has a Gemini key set (plus a masked hint) — used to
    bring their own free key for incident summaries. The key itself is never
    returned."""
    account = _account(db, current_user.account_id)
    return masked_key(account.gemini_api_key)


@router.put("/key", response_model=SummarizerKeyOut)
def set_summarizer_key(
    body: SummarizerKeyIn,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SummarizerKeyOut:
    """Set (or clear, with null) this tenant's Gemini key. With no key set,
    incident summaries fall back to the deterministic $0 template."""
    account = _account(db, current_user.account_id)
    account.gemini_api_key = body.gemini_api_key
    db.commit()
    return masked_key(account.gemini_api_key)
