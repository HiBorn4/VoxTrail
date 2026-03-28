import os
import asyncio
import websockets
import json
import base64
import numpy as np
import soundfile as sf
import time
from dotenv import load_dotenv
import sounddevice as sd

load_dotenv()

AZURE_KEY = os.getenv("AZURE_OPENAI_API_REALTIME_KEY")
AZURE_HOST = os.getenv("AZURE_OPENAI_ENDPOINT").replace("https://", "").replace("http://", "").rstrip("/")
AZURE_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION")
DEPLOYMENT = os.getenv("AZURE_OPENAI_REALTIME_DEPLOYMENT")

# Fixed audio settings
CHUNK_DURATION = 0.5
SAMPLE_RATE = 24000
CHANNELS = 1
AUDIO_DIR = "assistant_audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

# Audio buffer
audio_buffer = []
BUFFER_THRESHOLD = int(0.1 * SAMPLE_RATE)

# State management
assistant_speaking = False
current_playback = None
interruption_detected_time = None

## --- MODIFICATION START --- ##
# This function is now corrected to properly normalize audio before checking.
# This is the key fix for detecting your speech accurately.
def detect_speech(audio_chunk, threshold=0.02):
    """
    Detects speech in an audio chunk based on RMS energy.
    The audio chunk is expected to be int16, so it's normalized to float32 first.
    """
    # Convert int16 chunk to float32 normalized between -1.0 and 1.0
    normalized_chunk = audio_chunk.astype(np.float32) / 32767.0
    
    # Calculate Root Mean Square (RMS) energy
    rms = np.sqrt(np.mean(normalized_chunk**2))
    
    # Compare against the threshold
    return rms > threshold
## --- MODIFICATION END --- ##

async def stream_audio():
    url = f"wss://{AZURE_HOST}/openai/realtime?api-version={AZURE_API_VERSION}&deployment={DEPLOYMENT}"
    
    try:
        async with websockets.connect(url, extra_headers={"api-key": AZURE_KEY}) as ws:
            config = {
                "type": "session.update",
                "session": {
                    "modalities": ["audio", "text"],
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {"model": "gpt-4o-transcribe"},
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500,
                        "create_response": True,
                        "interrupt_response": True
                    }
                }
            }
            await ws.send(json.dumps(config))
            
            print("Connected to OpenAI Realtime API. Listening...")
            
            audio_queue = asyncio.Queue()
            recording_task = asyncio.create_task(record_audio_continuous(audio_queue))
            
            try:
                while True:
                    await asyncio.gather(
                        process_audio_input(ws, audio_queue),
                        handle_websocket_responses(ws),
                        return_exceptions=True
                    )
            except KeyboardInterrupt:
                print("\nStopping...")
                recording_task.cancel()
                
    except Exception as e:
        print(f"Connection error: {e}")

async def record_audio_continuous(audio_queue):
    """Continuously record audio and put chunks in queue."""
    thread_queue = asyncio.Queue()
    
    def audio_callback(indata, frames, time, status):
        if status:
            print(f"Audio status: {status}")
        audio_chunk = (indata[:, 0] * 32767).astype(np.int16)
        try:
            thread_queue.put_nowait(audio_chunk.copy())
        except asyncio.QueueFull:
            try:
                thread_queue.get_nowait()
                thread_queue.put_nowait(audio_chunk.copy())
            except asyncio.QueueEmpty:
                pass
    
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype='float32',
        callback=audio_callback,
        blocksize=int(CHUNK_DURATION * SAMPLE_RATE)
    )
    
    with stream:
        print("Recording started...")
        try:
            while True:
                try:
                    audio_chunk = thread_queue.get_nowait()
                    await audio_queue.put(audio_chunk)
                except asyncio.QueueEmpty:
                    pass
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            print("Recording stopped.")
            raise

async def process_audio_input(ws, audio_queue):
    """Process audio from queue, handle interruptions, and send to WebSocket."""
    global audio_buffer, assistant_speaking, current_playback, interruption_detected_time
    
    while True:
        try:
            audio_chunk = await asyncio.wait_for(audio_queue.get(), timeout=1.0)
            
            # Handle user interruption with a 3-second delay
            if assistant_speaking:
                is_speech = detect_speech(audio_chunk) # This will now work correctly
                
                if is_speech:
                    if interruption_detected_time is None:
                        interruption_detected_time = time.time()
                        print("🗣️ Possible interruption detected, confirming...")
                    elif time.time() - interruption_detected_time >= 3.0:
                        print("🛑 User interruption confirmed. Stopping assistant playback.")
                        sd.stop()
                        assistant_speaking = False
                        current_playback = None
                        interruption_detected_time = None
                else:
                    if interruption_detected_time is not None:
                        print("🎤 Interruption ended before confirmation. Resuming.")
                        interruption_detected_time = None

            # Buffer and send user audio to the API
            audio_buffer.extend(audio_chunk)
            if len(audio_buffer) >= BUFFER_THRESHOLD:
                if detect_speech(np.array(audio_buffer)):
                    audio_bytes = np.array(audio_buffer, dtype=np.int16).tobytes()
                    audio_base64 = base64.b64encode(audio_bytes).decode()
                    await ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": audio_base64
                    }))
                    print(f"🎤 Sent {len(audio_buffer)} samples ({len(audio_buffer)/SAMPLE_RATE*1000:.1f}ms)")
                audio_buffer = []
                
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            print(f"Error processing audio: {e}")

async def handle_websocket_responses(ws):
    """Handle responses from WebSocket and manage playback state."""
    global assistant_speaking, current_playback, interruption_detected_time
    assistant_audio = b""
    
    while True:
        try:
            msg = await ws.recv()
            data = json.loads(msg)
            
            event_type = data.get("type")
            if event_type == "conversation.item.input_audio_transcription.completed":
                print(f"👤 User: {data.get('transcript', '')}")
            elif event_type == "response.created":
                print("🤖 Assistant is thinking...")
            elif event_type == "response.cancelled":
                print("❌ Assistant response cancelled due to interruption")
                assistant_speaking = False
                assistant_audio = b""
            elif event_type == "error":
                print(f"❌ API Error: {data.get('error', {}).get('message', 'Unknown error')}")

            if event_type == "response.audio.delta":
                assistant_audio += base64.b64decode(data.get("delta", ""))

            elif event_type == "response.audio.done":
                if len(assistant_audio) > 0:
                    audio_np = np.frombuffer(assistant_audio, dtype=np.int16)
                    filename = os.path.join(AUDIO_DIR, f"assistant_{int(time.time())}.wav")
                    sf.write(filename, audio_np, SAMPLE_RATE, subtype='PCM_16')
                    print(f"💾 Saved assistant audio to {filename}")
                    
                    assistant_speaking = True
                    print("🔊 Assistant is speaking...")
                    
                    audio_float = audio_np.astype(np.float32) / 32767.0
                    sd.play(audio_float, SAMPLE_RATE)
                    current_playback = audio_float
                    
                    start_time = time.time()
                    playback_duration = len(audio_np) / SAMPLE_RATE

                    while assistant_speaking and (time.time() - start_time) < playback_duration:
                        await asyncio.sleep(0.1)

                    if not assistant_speaking:
                        print("🎤 Playback stopped due to user interruption.")
                    else:
                        assistant_speaking = False
                        print("✅ Assistant finished speaking.")
                    
                    current_playback = None
                    interruption_detected_time = None
                        
                else:
                    print("🔇 No audio response received from assistant.")
                
                assistant_audio = b""
                
        except websockets.exceptions.ConnectionClosed:
            print("🔌 WebSocket connection closed")
            break
        except Exception as e:
            print(f"❌ Error handling WebSocket response: {e}")

if __name__ == "__main__":
    print("🎙️ Starting Real-time Speech Bot with Interruption Support...")
    print("💬 Speak into your microphone. You can interrupt the assistant anytime!")
    print("⚡ The assistant will stop speaking when you start talking.")
    print("🛑 Press Ctrl+C to stop.")
    print("-" * 60)
    asyncio.run(stream_audio())