import os
import asyncio
import websockets
import json
import base64
import numpy as np
import sounddevice as sd
from dotenv import load_dotenv

load_dotenv()

AZURE_KEY = os.getenv("AZURE_OPENAI_API_REALTIME_KEY")
AZURE_HOST = os.getenv("AZURE_OPENAI_ENDPOINT").replace("https://", "").replace("http://", "").rstrip("/")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
DEPLOYMENT = os.getenv("AZURE_OPENAI_REALTIME_DEPLOYMENT")

CHUNK_DURATION = 2  # seconds
SAMPLE_RATE = 24000
CHANNELS = 1

# Normal
# English Hindi Marathi
# gpt-4o-mini-transcribe
# Azure Openai
# Api Calls -> Realtime
# 4o-mini
# blocks

async def stream_audio():
    url = f"wss://{AZURE_HOST}/openai/realtime?api-version={AZURE_API_VERSION}&deployment={DEPLOYMENT}"
    async with websockets.connect(url, extra_headers={"api-key": AZURE_KEY}) as ws:
        config = {
            "type": "session.update",
            "session": {
                "modalities": ["audio", "text"],
                "input_audio_format": "pcm16",
                "input_audio_transcription": {"model": "gpt-4o-transcribe"},
                "turn_detection": {"type": "server_vad"}
            }
        }
        await ws.send(json.dumps(config))

        try:
            with sd.InputStream(samplerate=SAMPLE_RATE, channels=CHANNELS, dtype='float32') as stream:
                while True:
                    audio_chunk, _ = stream.read(int(CHUNK_DURATION * SAMPLE_RATE))
                    audio_chunk = audio_chunk.flatten()
                    if audio_chunk.dtype != np.int16:
                        audio_chunk = (audio_chunk * 32767).astype(np.int16)
                    audio_base64 = base64.b64encode(audio_chunk.tobytes()).decode()
                    await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": audio_base64}))
                    await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

                    assistant_buffer = ""  # Buffer for assistant reply

                    while True:
                        try:
                            msg = await asyncio.wait_for(ws.recv(), timeout=0.05)
                            data = json.loads(msg)

                            # Print user transcription only
                            if data.get("type") == "conversation.item.input_audio_transcription.completed":
                                print("[You]:", data.get("transcript", ""))

                            # Buffer assistant streaming reply
                            if data.get("type") == "response.audio_transcript.delta":
                                assistant_buffer += data.get("delta", "")

                            # Print assistant final reply only (buffered)
                            if data.get("type") == "response.audio_transcript.final":
                                # Print the full buffered sentence
                                print("[Assistant]:", assistant_buffer.strip())
                                # Optionally, print the final text from API (should match buffer)
                                # print("[Assistant Final]:", data.get("text", ""))
                                break  # End inner loop after full reply

                        except asyncio.TimeoutError:
                            break
        except KeyboardInterrupt:
            print("\nStopped.")

if __name__ == "__main__":
    asyncio.run(stream_audio())