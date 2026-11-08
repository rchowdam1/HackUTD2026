"""Live calls (#94): the Twilio number's voice webhook and the Media Stream socket.

POST /voice/incoming answers a call to the Twilio number: stream both sides to /voice/stream and
bridge the call to DEMO_PHONE, so the two phones talk normally while the app listens. A
unidirectional <Start><Stream> is the only stream that lets the <Dial> after it run (PRD §11.2).

The tunnel middleware in app.main only filters HTTP requests, so the socket checks Twilio's
signature itself before accepting.
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

import asyncio

from fastapi import APIRouter, HTTPException, Request, Response, WebSocket
from twilio.twiml.voice_response import VoiceResponse

from app import callcontrol, consent, sms
from app.ingest import live
from app.sms.webhooks import signed, verified_form

router = APIRouter(prefix="/voice", tags=["tunnel"])


def stream_url() -> str:
    """PUBLIC_BASE_URL with https -> wss (the tunnel), http -> ws (local)."""
    return "ws" + sms.public_base_url().removeprefix("http") + "/voice/stream"


@router.post("/incoming")
async def incoming(request: Request) -> Response:
    form = await verified_form(request)
    if consent.configured("demo") is None:
        raise HTTPException(503, "DEMO_PHONE is not set")
    room = form["CallSid"]
    twiml = VoiceResponse()
    twiml.start().stream(url=stream_url(), track="both_tracks")
    # A conference, not a plain <Dial>, so an alert can hold the caller and speak to the subscriber alone.
    twiml.dial().conference(room, participant_label="caller", beep="false", wait_url="",
                            start_conference_on_enter=True, end_conference_on_exit=True)
    asyncio.get_running_loop().run_in_executor(None, callcontrol.dial_subscriber, room, form.get("From"))
    return Response(str(twiml), media_type="text/xml")


@router.api_route("/announce", methods=["GET", "POST"])
async def announce(t: str) -> Response:
    twiml = VoiceResponse()
    twiml.say(callcontrol.announcement(t), voice=callcontrol.VOICE)
    return Response(str(twiml), media_type="text/xml")


@router.api_route("/hold", methods=["GET", "POST"])
async def hold() -> Response:
    twiml = VoiceResponse()
    twiml.say("Please hold.", voice=callcontrol.VOICE)
    twiml.pause(length=60)
    return Response(str(twiml), media_type="text/xml")


@router.websocket("/stream")
async def stream(ws: WebSocket) -> None:
    # Twilio signs the stream URL with no params; the header name arrives lowercase on a WebSocket.
    if not signed(stream_url(), {}, ws.headers.get("x-twilio-signature", "")):
        await ws.close(code=1008)  # before accept(), so the handshake gets a 403
        return
    await ws.accept()
    await live.run(_messages(ws), sms_mode=sms.get_mode())


async def _messages(ws: WebSocket) -> AsyncIterator[dict]:
    async for text in ws.iter_text():
        yield json.loads(text)
