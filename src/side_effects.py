"""
Safe Secondary Side Effects Layer (Confirmation Email / Webhook).
Failure in secondary side effects never breaks the primary submission flow.
"""

import logging
from src.config import MOCK_EMAIL_FAIL

logger = logging.getLogger("side_effects")
_runtime_fail_email = MOCK_EMAIL_FAIL


def set_email_side_effect_status(should_fail: bool):
    global _runtime_fail_email
    _runtime_fail_email = should_fail


def trigger_confirmation_email(submission_data: dict, widget_title: str) -> str:
    """
    Simulates sending an email confirmation.
    Returns status: 'sent' or 'failed'.
    Crucially: NEVER raises an exception out to the caller.
    """
    try:
        if _runtime_fail_email:
            raise ConnectionError("Simulated SMTP Server unreachable (550 Error)")

        # In production this connects to SMTP / SendGrid / Mailpit
        email = submission_data.get("email", "unknown@example.com")
        print(f"[EMAIL SIDE-EFFECT] Confirmation email queued for {email} regarding '{widget_title}'")
        return "sent"
    except Exception as e:
        logger.warning(f"[SAFE-FAIL] Side effect failed: {e}. Main submission preserved.")
        return "failed"
