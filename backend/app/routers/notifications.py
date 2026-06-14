import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Account
from app.notifications import AlertEvent, WebhookNotifier
from app.schemas.auth import CurrentUser
from app.schemas.notifications import NotificationSettings

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _account(db: Session, account_id: int) -> Account:
    account = db.get(Account, account_id)
    if account is None:  # pragma: no cover - the authed account always exists
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="account not found"
        )
    return account


@router.get("", response_model=NotificationSettings)
def get_notifications(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> NotificationSettings:
    """The current tenant's alert webhook (Slack/Discord), or null if unset."""
    account = _account(db, current_user.account_id)
    return NotificationSettings(webhook_url=account.notify_webhook_url)


@router.put("", response_model=NotificationSettings)
def set_notifications(
    body: NotificationSettings,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> NotificationSettings:
    """Set (or clear, with null) this tenant's alert webhook. The URL is
    validated to an https Slack/Discord host by the schema."""
    account = _account(db, current_user.account_id)
    account.notify_webhook_url = body.webhook_url
    db.commit()
    return NotificationSettings(webhook_url=account.notify_webhook_url)


@router.post("/test")
def test_notification(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Send a sample alert to the configured webhook and report the result, so
    the user can confirm their Slack/Discord setup before a real alert fires."""
    account = _account(db, current_user.account_id)
    if not account.notify_webhook_url:
        return {"ok": False, "detail": "No webhook URL configured."}

    event = AlertEvent(
        status="firing",
        alert_id=0,
        workload="loupe-test",
        rule="test_notification",
        severity="info",
        message="This is a test notification from Loupe — your webhook works.",
    )
    try:
        WebhookNotifier(account.notify_webhook_url).send_test(event)
    except httpx.HTTPError as exc:
        return {"ok": False, "detail": f"Delivery failed: {exc}"}
    return {"ok": True, "detail": "Test notification sent."}
