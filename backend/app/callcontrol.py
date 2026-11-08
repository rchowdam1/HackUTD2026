"""Live-call control: the caller and DEMO_PHONE meet in a Twilio conference, so when an alert fires the
app can put the caller on hold and speak the warning to the subscriber alone (a conference
announcement plays to one participant only). This works with no SMS registration (10DLC).
"""
from __future__ import annotations

import asyncio
import logging
import os

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app import consent, sms

log = logging.getLogger(__name__)

VOICE = "Polly.Joanna-Neural"
SPOKEN = {
    "ALERT-OTP-01": "They asked you for a code, password or PIN. Legitimate companies and organizations will never "
                    "ask you for these over the phone. Do not share it. Hang up, and call them back on a number "
                    "you trust.",
    "ALERT-PAY-01": "They are pressuring you to send money or make a payment. Legitimate organizations will never "
                    "rush you to pay over the phone. Do not pay. Hang up, and call them back on a number you trust.",
    "ALERT-REMOTE-01": "They want access to your device or want you to install something. Legitimate organizations "
                       "will never ask for this on an unexpected call. Do not install anything. Hang up, and call "
                       "them back on a number you trust.",
}

# The live call: conference SID and each side's call SID. Taken from the participant Twilio returns when the
# subscriber is dialled in; looking the conference up by name proved unreliable (it can come back empty).
_live: dict[str, str] = {}


def _client() -> Client:
    return Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])


def announcement(template_id: str) -> str:
    return "CallSafe alert. This caller may be a scammer. " + SPOKEN.get(template_id, "Be careful what you share.")


def dial_subscriber(room: str, caller: str | None) -> None:
    """Ring DEMO_PHONE into the room, showing the scammer's number when Twilio allows it."""
    _live.clear()
    kw = dict(to=consent.configured("demo"), label="subscriber", beep="false", end_conference_on_exit=True,
              early_media=True)
    participants = _client().conferences(room).participants
    try:
        p = participants.create(from_=caller, **kw)
    except TwilioRestException as e:
        log.info("caller-id passthrough refused (%s); ringing from TWILIO_FROM", e.code)
        p = participants.create(from_=os.environ["TWILIO_FROM"], **kw)
    _live.update(conference=p.conference_sid, caller=room, subscriber=p.call_sid)


def _hold(on: bool) -> None:
    kw = {"hold": True, "hold_url": f"{sms.public_base_url()}/voice/hold"} if on else {"hold": False}
    _client().conferences(_live["conference"]).participants(_live["caller"]).update(**kw)


def _announce(template_id: str) -> None:
    url = f"{sms.public_base_url()}/voice/announce?t={template_id}"
    _client().conferences(_live["conference"]).participants(_live["subscriber"]).update(announce_url=url)


async def alert(template_id: str) -> None:
    """Hold the caller, speak the warning to the subscriber, then take the caller off hold."""
    if not _live:
        log.warning("voice alert skipped: no live conference")
        return
    try:
        await asyncio.gather(asyncio.to_thread(_hold, True), asyncio.to_thread(_announce, template_id))
        log.warning("voice alert %s spoken on live call", template_id)
        # ~2.6 words/s for the neural voice, plus a beat for Twilio to start playing it
        await asyncio.sleep(len(announcement(template_id).split()) / 2.6 + 1.5)
        await asyncio.to_thread(_hold, False)
    except Exception:
        log.exception("voice alert failed")
