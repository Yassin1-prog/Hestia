"""Landlord outreach: contact extraction + SMS (Twilio) / e-mail (Resend) delivery.

See OUTREACH.md at the repo root for the design and configuration.
"""

from backend.outreach.channels import ResendEmailSender, SendResult, TwilioSmsSender
from backend.outreach.contacts import ContactEmail, ContactPhone, ExtractedContacts, extract_contacts
from backend.outreach.messages import OutreachContext, UserContact, compose_email, compose_sms
from backend.outreach.service import (
    Channel,
    ChannelAttempt,
    OutreachBatchResponse,
    OutreachSettings,
    PropertyOutreachResult,
    run_outreach,
)

__all__ = [
    "Channel",
    "ChannelAttempt",
    "ContactEmail",
    "ContactPhone",
    "ExtractedContacts",
    "OutreachBatchResponse",
    "OutreachContext",
    "OutreachSettings",
    "PropertyOutreachResult",
    "ResendEmailSender",
    "SendResult",
    "TwilioSmsSender",
    "UserContact",
    "compose_email",
    "compose_sms",
    "extract_contacts",
    "run_outreach",
]
