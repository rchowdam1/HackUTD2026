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

from fastapi import APIRouter, HTTPException, Request, Response, WebSocket
from twilio.twiml.voice_response import VoiceResponse

from app import consent, sms
from app.ingest import live
from app.sms.webhooks import signed, verified_form

router = APIRouter(prefix="/voice", tags=["tunnel"])


def stream_url() -> str:
    """PUBLIC_BASE_URL with https -> wss (the tunnel), http -> ws (local)."""
    return "ws" + sms.public_base_url().removeprefix("http") + "/voice/stream"


@router.post("/incoming")
async def incoming(request: Request) -> Response:
    await verified_form(request)
    subscriber = consent.configured("demo")
    if subscriber is None:
        raise HTTPException(503, "DEMO_PHONE is not set")
    twiml = VoiceResponse()
    twiml.start().stream(url=stream_url(), track="both_tracks")
    twiml.dial(subscriber)
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
