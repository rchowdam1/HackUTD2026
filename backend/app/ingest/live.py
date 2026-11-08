"""Live call ingestion: a Twilio Media Stream as a segment source for ingest._replay (#94).

`<Start><Stream track="both_tracks">` sends 20 ms frames of 8 kHz mu-law per track. Twilio's
inbound track is the party who called the Twilio number (the caller); outbound is what Twilio
plays to them, i.e. the dialled subscriber. Each track is cut into utterances at a pause (or at
MAX_UTTERANCE_MS, so a long monologue can't delay an alert), and each utterance is transcribed
in memory: no call audio is written to disk.
"""
from __future__ import annotations

import asyncio
import base64
import io
import logging
import math
import time
import wave
from array import array
from collections.abc import AsyncIterator

from app import asr
from app.ingest import Timed, _replay
from app.models import SmsMode, Speaker

SAMPLE_RATE = 8000
SPEECH_RMS = 500  # 16-bit RMS of a 20 ms frame above which it counts as speech; phone line noise sits well below
PAUSE_MS = 600  # the pause counts toward the 2 s alert budget (latency is timed from the end of speech)
MAX_UTTERANCE_MS = 8000
MIN_SPEECH_MS = 300  # shorter bursts (clicks, a cough) aren't sent to whisper, which invents words on noise
TRACK_SPEAKER: dict[str, Speaker] = {"inbound": "caller", "outbound": "subscriber"}
log = logging.getLogger(__name__)


def _ulaw_to_linear(byte: int) -> int:
    """G.711 mu-law byte -> 16-bit linear sample."""
    b = ~byte & 0xFF
    t = (((b & 0x0F) << 3) + 0x84) << ((b & 0x70) >> 4)
    return 0x84 - t if b & 0x80 else t - 0x84


ULAW = [_ulaw_to_linear(b) for b in range(256)]

# (speaker, start_ms, end_ms, 16-bit PCM, wall-clock time its speech ended)
Utterance = tuple[Speaker, int, int, bytes, float]


class _Track:
    """Collects one side of the call until a pause, then hands back the utterance."""

    def __init__(self, speaker: Speaker):
        self.speaker = speaker
        self._reset()

    def _reset(self) -> None:
        self.pcm = array("h")
        self.start_ms: int | None = None
        self.end_ms = 0
        self.speech_ms = self.silence_ms = 0

    def add(self, ulaw: bytes, timestamp_ms: int) -> Utterance | None:
        samples = [ULAW[b] for b in ulaw]
        frame_ms = len(samples) * 1000 // SAMPLE_RATE
        loud = math.sqrt(sum(s * s for s in samples) / max(len(samples), 1)) >= SPEECH_RMS
        if self.start_ms is None:
            if not loud:
                return None
            self.start_ms = timestamp_ms
        self.pcm.extend(samples)
        self.end_ms = timestamp_ms + frame_ms
        if loud:
            self.speech_ms += frame_ms
            self.silence_ms = 0
        else:
            self.silence_ms += frame_ms
        if self.silence_ms >= PAUSE_MS or self.end_ms - self.start_ms >= MAX_UTTERANCE_MS:
            return self.flush()
        return None

    def flush(self) -> Utterance | None:
        u = None
        if self.start_ms is not None and self.speech_ms >= MIN_SPEECH_MS:
            u = (self.speaker, self.start_ms, self.end_ms, self.pcm.tobytes(), time.time() - self.silence_ms / 1000)
        self._reset()
        return u


async def run(messages: AsyncIterator[dict], *, sms_mode: SmsMode) -> str:
    """Monitor one streamed call (Twilio's JSON messages) like a replay; returns session_ref.
    The session finishes when the stream stops or the socket closes. If the operator starts another
    call or resets, the session is replaced and this returns early without reading further."""
    utterances: asyncio.Queue[Utterance | None] = asyncio.Queue()
    reader = asyncio.create_task(_cut(messages, utterances))
    try:
        return await _replay(_transcribed(utterances), sms_mode, realtime=False, source="phone")
    finally:
        reader.cancel()


async def _cut(messages: AsyncIterator[dict], out: asyncio.Queue[Utterance | None]) -> None:
    tracks = {name: _Track(speaker) for name, speaker in TRACK_SPEAKER.items()}
    async for m in messages:
        if m.get("event") == "media":
            media = m["media"]
            if u := tracks[media["track"]].add(base64.b64decode(media["payload"]), int(media["timestamp"])):
                out.put_nowait(u)
        elif m.get("event") == "stop":
            break
    for track in tracks.values():
        if u := track.flush():
            out.put_nowait(u)
    out.put_nowait(None)


async def _transcribed(utterances: asyncio.Queue[Utterance | None]) -> Timed:
    """One utterance at a time, in the order they ended, so seq follows the conversation.
    Whisper runs off the event loop; a transcription error ends the call on the segments so far."""
    seq = 0
    while (u := await utterances.get()) is not None:
        speaker, start_ms, _, pcm, ended_at = u
        try:
            # Greedy decoding: on a phone line it reads the same as beam 5 for us, at a fraction of the time.
            segments, _ = await asyncio.to_thread(asr.transcribe, _wav(pcm), beam_size=1)
        except Exception:
            log.exception("ASR failed on a live call; ending the call")
            return
        for start_s, end_s, text in segments:
            seq += 1
            yield 0, {"seq": seq, "speaker": speaker, "text": text, "source": "asr", "ended_at": ended_at,
                      "t_start_ms": start_ms + round(start_s * 1000), "t_end_ms": start_ms + round(end_s * 1000)}


def _wav(pcm: bytes) -> io.BytesIO:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    buf.seek(0)
    return buf
