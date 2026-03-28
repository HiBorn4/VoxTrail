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

# Fixed audio settings - minimum 100ms chunks required
CHUNK_DURATION = 0.5  # 500ms chunks (well above 100ms minimum)
SAMPLE_RATE = 24000  # OpenAI Realtime API expects 24kHz
CHANNELS = 1
AUDIO_DIR = "assistant_audio"
os.makedirs(AUDIO_DIR, exist_ok=True)

# Audio buffer for accumulating chunks
audio_buffer = []
BUFFER_THRESHOLD = int(0.1 * SAMPLE_RATE)  # 100ms minimum

# State management for interruptions
assistant_speaking = False
current_playback = None

def detect_speech(audio_chunk, threshold=0.01):
    """Simple speech detection based on RMS energy - slightly higher threshold for better detection"""
    rms = np.sqrt(np.mean(audio_chunk.astype(np.float32) ** 2))
    return rms > threshold

async def stream_audio():
    url = f"wss://{AZURE_HOST}/openai/realtime?api-version={AZURE_API_VERSION}&deployment={DEPLOYMENT}"
    
    try:
        async with websockets.connect(url, extra_headers={"api-key": AZURE_KEY}) as ws:
            # Configure session with interruption support
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
                        "interrupt_response": True  # Enable interruption
                    }
                }
            }
            await ws.send(json.dumps(config))
            
            print("Connected to OpenAI Realtime API. Listening...")
            
            # Start continuous audio recording in background
            audio_queue = asyncio.Queue()
            recording_task = asyncio.create_task(record_audio_continuous(audio_queue))
            
            try:
                while True:
                    # Process audio and WebSocket messages concurrently
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
    """Continuously record audio and put chunks in queue"""
    import threading
    
    # Use a thread-safe queue for the audio callback
    thread_queue = asyncio.Queue()
    
    def audio_callback(indata, frames, time, status):
        if status:
            print(f"Audio status: {status}")
        # Convert to int16
        audio_chunk = (indata[:, 0] * 32767).astype(np.int16)
        # Put in a thread-safe way using put_nowait
        try:
            thread_queue.put_nowait(audio_chunk.copy())
        except asyncio.QueueFull:
            # Drop oldest chunk if queue is full
            try:
                thread_queue.get_nowait()
                thread_queue.put_nowait(audio_chunk.copy())
            except asyncio.QueueEmpty:
                pass
    
    # Start recording stream
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
                # Transfer from thread queue to async queue
                try:
                    audio_chunk = thread_queue.get_nowait()
                    await audio_queue.put(audio_chunk)
                except asyncio.QueueEmpty:
                    pass
                await asyncio.sleep(0.01)  # Small sleep to prevent busy waiting
        except asyncio.CancelledError:
            print("Recording stopped.")
            raise

async def process_audio_input(ws, audio_queue):
    """Process audio input from queue and send to WebSocket"""
    global audio_buffer, assistant_speaking, current_playback, interruption_start_time
    
    while True:
        try:
            # Get audio chunk from queue
            audio_chunk = await asyncio.wait_for(audio_queue.get(), timeout=1.0)
            
            # Add to buffer
            audio_buffer.extend(audio_chunk)
            
            # Check if we have enough audio (minimum 100ms)
            if len(audio_buffer) >= BUFFER_THRESHOLD:
                # Detect if there's speech
                if detect_speech(np.array(audio_buffer)):
                                        
                    # Convert to base64 and send
                    audio_bytes = np.array(audio_buffer, dtype=np.int16).tobytes()
                    audio_base64 = base64.b64encode(audio_bytes).decode()
                    
                    await ws.send(json.dumps({
                        "type": "input_audio_buffer.append",
                        "audio": audio_base64
                    }))
                    
                    # print(f"🎤 Sent {len(audio_buffer)} samples ({len(audio_buffer)/SAMPLE_RATE*1000:.1f}ms)")
                
                # Clear buffer
                audio_buffer = []
                
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            print(f"Error processing audio: {e}")

async def handle_websocket_responses(ws):
    """Handle responses from WebSocket"""
    global assistant_speaking, current_playback
    assistant_audio = b""
    
    while True:
        try:
            msg = await ws.recv()
            data = json.loads(msg)
            
            # Print important events (not all debug info)
            if data.get("type") in [
                "session.created", "session.updated", 
                "conversation.item.input_audio_transcription.completed",
                "response.created", "response.done", "response.cancelled",
                "input_audio_buffer.speech_started", "input_audio_buffer.speech_stopped",
                "error"
            ]:
                if data.get("type") == "conversation.item.input_audio_transcription.completed":
                    transcript = data.get("transcript", "")
                    print(f"👤 User: {transcript}")
                    
                elif data.get("type") == "response.created":
                    print("🤖 Assistant is thinking...")
                    
                elif data.get("type") == "response.cancelled":
                    print("❌ Assistant response cancelled due to interruption")
                    assistant_speaking = False
                    assistant_audio = b""  # Clear any accumulated audio
                    
                elif data.get("type") == "input_audio_buffer.speech_started":
                    print("🎤 Speech detected...")
                    
                elif data.get("type") == "input_audio_buffer.speech_stopped":
                    print("🔇 Speech ended, processing...")
                    
                elif data.get("type") == "error":
                    error_msg = data.get("error", {}).get("message", "Unknown error")
                    print(f"❌ API Error: {error_msg}")
                    
                else:
                    print(f"ℹ️ Event: {data.get('type')}")

            # Handle audio response
            if data.get("type") == "response.audio.delta":
                # Alternative
                chunk = base64.b64decode(data.get("delta", ""))
                assistant_audio += chunk

            elif data.get("type") == "response.audio.done":
                if len(assistant_audio) > 0:
                    # Save assistant audio
                    audio_np = np.frombuffer(assistant_audio, dtype=np.int16)
                    filename = os.path.join(AUDIO_DIR, f"assistant_{int(time.time())}.wav")
                    # Avoid this to reduce latency
                    # sf.write(filename, audio_np, SAMPLE_RATE, subtype='PCM_16')
                    
                    print(f"💾 Saved assistant audio to {filename}")
                    
                    # Set speaking state and play the audio
                    assistant_speaking = True
                    print("🔊 Assistant is speaking...")
                    
                    # Play the audio in a non-blocking way
                    audio_float = audio_np.astype(np.float32) / 32767.0
                    sd.play(audio_float, SAMPLE_RATE)
                    current_playback = audio_float
                    
                    # Wait for playback to finish (but can be interrupted)
                    try:
                        # Calculate playback duration
                        playback_duration = len(audio_np) / SAMPLE_RATE
                        await asyncio.sleep(playback_duration + 0.5)  # Small buffer
                        assistant_speaking = False
                        current_playback = None
                        print("✅ Assistant finished speaking")
                    except asyncio.CancelledError:
                        assistant_speaking = False
                        current_playback = None
                        
                else:
                    print("🔇 No audio response received from assistant.")
                
                # Reset for next response
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