import json
import asyncio
import base64
import logging
from datetime import datetime
from typing import Dict, Any
import time
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from google.genai.types import Part, Content, Blob
from google.adk.runners import InMemoryRunner
from google.adk.agents import LiveRequestQueue
from google.adk.agents.run_config import RunConfig
from google.genai import types

from travel_assist_agentic_bot.agents.voice_orchestrator_agent import voice_orchestrator_agent
from travel_assist_agentic_bot.services.session_service import (
    get_session_service,
    ensure_session,
    update_session_metadata,
    get_session_state
)
from travel_assist_agentic_bot.services.redis_manager import RedisJSONManager

logger = logging.getLogger(__name__)

async def start_voice_agent_session(
    session_id: str,
    user_id: str,
    app_name: str,
    redis_manager: RedisJSONManager
):
    """Initialize voice agent session with ADK runner"""
    
    # Get session service
    session_service = get_session_service()
    
    # Ensure session exists (create if needed with voice metadata)
    session = await ensure_session(
        session_service,
        app_name=app_name,
        user_id=user_id,
        session_id=session_id,
        initial_state={
            "voice_enabled": True,
            "voice_started_at": datetime.now().isoformat()
        }
    )
    
    # No need for apply_state_delta here - initial_state already set it
    logger.info(f"Voice session initialized: {session.id} for user: {user_id}")
    
    # Create ADK Runner
    runner = InMemoryRunner(
        app_name=app_name,
        agent=voice_orchestrator_agent
    )
    
    # Create LiveRequestQueue
    live_request_queue = LiveRequestQueue()
    
    # Configure RunConfig
    run_config = RunConfig(
        streaming_mode="bidi",
        session_resumption=types.SessionResumptionConfig(transparent=True),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(
                start_of_speech_sensitivity=types.StartSensitivity.START_SENSITIVITY_LOW,
                end_of_speech_sensitivity=types.EndSensitivity.END_SENSITIVITY_LOW,  # Changed from HIGH - ends turns faster
                prefix_padding_ms=300,
                silence_duration_ms=1000,  # Reduced from 2000 - critical for single responses
            )
        ),
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                    voice_name="Puck"
                )
            ),
            language_code="en-US"
        ),
        output_audio_transcription={},
        input_audio_transcription={},
    )
    
    # Start live agent session
    live_events = runner.run_live(
        session=session,
        live_request_queue=live_request_queue,
        run_config=run_config,
    )
    
    return live_events, live_request_queue, runner, session_service


async def agent_to_client_messaging(
    websocket: WebSocket,
    live_events,
    session_id: str,
    redis_manager: RedisJSONManager
):
    """Stream agent responses to client"""
    try:
        async for event in live_events:
            try:
                message_to_send = {
                    "author": event.author or "agent",
                    "is_partial": event.partial or False,
                    "turn_complete": event.turn_complete or False,
                    "interrupted": event.interrupted or False,
                    "parts": [],
                    "input_transcription": None,
                    "output_transcription": None
                }
                
                if not event.content:
                    if (message_to_send["turn_complete"] or message_to_send["interrupted"]):
                        await websocket.send_text(json.dumps(message_to_send))
                    continue
                
                # Extract text transcription
                transcription_text = "".join(
                    part.text for part in event.content.parts if part.text
                )
                
                # Handle user input transcription
                if hasattr(event.content, "role") and event.content.role == "user":
                    if transcription_text:
                        message_to_send["input_transcription"] = {
                            "text": transcription_text,
                            "is_final": not event.partial
                        }
                        
                        # Store final user transcript
                        if not event.partial:
                            await redis_manager.append_voice_transcript(
                                session_id,
                                "user",
                                transcription_text
                            )
                
                # Handle agent output transcription
                elif hasattr(event.content, "role") and event.content.role == "model":
                    if transcription_text:
                        message_to_send["output_transcription"] = {
                            "text": transcription_text,
                            "is_final": not event.partial
                        }
                        message_to_send["parts"].append({
                            "type": "text",
                            "data": transcription_text
                        })
                        
                        # Store final agent transcript
                        if not event.partial:
                            await redis_manager.append_voice_transcript(
                                session_id,
                                "agent",
                                transcription_text
                            )
                    
                    # Process audio parts
                    for part in event.content.parts:
                        if part.inline_data and part.inline_data.mime_type.startswith("audio/pcm"):
                            audio_data = part.inline_data.data
                            encoded_audio = base64.b64encode(audio_data).decode("ascii")
                            message_to_send["parts"].append({
                                "type": "audio/pcm",
                                "data": encoded_audio
                            })
                        
                        elif part.function_call:
                            message_to_send["parts"].append({
                                "type": "function_call",
                                "data": {
                                    "name": part.function_call.name,
                                    "args": part.function_call.args or {}
                                }
                            })
                        
                        elif part.function_response:
                            message_to_send["parts"].append({
                                "type": "function_response",
                                "data": {
                                    "name": part.function_response.name,
                                    "response": part.function_response.response or {}
                                }
                            })
                
                # Send message if there's content
                if (message_to_send["parts"] or
                    message_to_send["turn_complete"] or
                    message_to_send["interrupted"] or
                    message_to_send["input_transcription"] or
                    message_to_send["output_transcription"]):
                    
                    await websocket.send_text(json.dumps(message_to_send))
                    
            except Exception as e:
                logger.error(f"Error processing agent event: {e}", exc_info=True)
                
    except Exception as e:
        logger.error(f"Error in agent_to_client_messaging: {e}", exc_info=True)



async def client_to_agent_messaging(
    websocket: WebSocket,
    live_request_queue: LiveRequestQueue,
    session_id: str
):
    """Handle client audio/text input"""
    while True:
        try:
            message_json = await websocket.receive_text()
            message = json.loads(message_json)
            
            # Handle control messages (speech_end, etc.)
            msg_type = message.get("type")
            if msg_type == "speech_end":
                # Ignore - ADK handles turn detection via audio silence
                continue
            
            # Only process messages with mime_type
            mime_type = message.get("mime_type")
            if not mime_type:
                logger.warning(f"Ignoring message without mime_type: {message.keys()}")
                continue
            
            if mime_type == "text/plain":
                data = message["data"]
                content = Content(role="user", parts=[Part.from_text(text=data)])
                live_request_queue.send_content(content=content)
            
            elif mime_type == "audio/pcm":
                data = message["data"]
                decoded_data = base64.b64decode(data)
                live_request_queue.send_realtime(Blob(data=decoded_data, mime_type=mime_type))
            
            elif mime_type == "image/jpeg":
                data = message["data"]
                decoded_data = base64.b64decode(data)
                live_request_queue.send_realtime(Blob(data=decoded_data, mime_type=mime_type))
            
            else:
                logger.warning(f"Unsupported mime type: {mime_type}")
                
        except WebSocketDisconnect:
            logger.info(f"Voice client disconnected: {session_id}")
            break
        
        except Exception as e:
            logger.error(f"Error in client_to_agent_messaging: {e}", exc_info=True)
            break



async def handle_voice_websocket(
    websocket: WebSocket,
    session_id: str,
    user_id: str = None,
    app_name: str = "travel-portal-voice"
):
    """Main voice WebSocket handler"""
    redis_manager = RedisJSONManager()
    
    # Extract user_id from session if not provided
    if not user_id:
        session_service = get_session_service()
        try:
            session_state = await get_session_state(
                session_service,
                app_name=app_name,
                user_id="temp",  # Will be updated
                session_id=session_id
            )
            user_id = session_state.get("emp_id") or session_id
        except:
            user_id = session_id
    
    try:
        # Accept connection
        await websocket.accept()
        logger.info(f"Voice WebSocket connected: {session_id}")
        
        # Initialize voice agent session
        live_events, live_request_queue, runner, session_service = await start_voice_agent_session(
            session_id,
            user_id,
            app_name,
            redis_manager
        )
        
        # Initialize voice context in Redis
        await redis_manager.set_voice_context(session_id, {
            "conversation_state": "idle",
            "pending_action": None,
            "collected_params": {},
            "missing_params": [],
            "retry_count": 0
        })
        
        # Start parallel tasks
        agent_to_client_task = asyncio.create_task(
            agent_to_client_messaging(websocket, live_events, session_id, redis_manager)
        )
        
        client_to_agent_task = asyncio.create_task(
            client_to_agent_messaging(websocket, live_request_queue, session_id)
        )
        
        # Wait for completion or error
        tasks = [agent_to_client_task, client_to_agent_task]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
        
    except Exception as e:
        logger.error(f"Error in voice websocket handler: {e}", exc_info=True)
    finally:
        # Cleanup
        try:
            live_request_queue.close()
        except:
            pass
        
        # Update session metadata on disconnect
        try:
            if 'session_service' in locals() and session_service and user_id:
                # Get the session again
                session = await session_service.get_session(
                    app_name=app_name,
                    user_id=user_id,
                    session_id=session_id
                )
                
                # Update state with voice ended
                from travel_assist_agentic_bot.services.session_service import apply_state_delta
                await apply_state_delta(
                    session_service,
                    session,
                    state_delta={
                        "metadata": {
                            "voice_enabled": False,
                            "voice_ended_at": datetime.now().isoformat()
                        }
                    },
                    author="voice_system"
                )
        except Exception as e:
            logger.error(f"Error updating session on cleanup: {e}")
        
        logger.info(f"Voice WebSocket disconnected: {session_id}")