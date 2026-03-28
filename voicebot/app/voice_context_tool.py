# travel_assist_agentic_bot/tools/voice_context_tool.py

from google.adk.tools import FunctionTool
from google.adk.tools.tool_context import ToolContext
from typing import Dict, Any

def get_voice_context(tool_context: ToolContext) -> Dict[str, Any]:
    """
    Retrieves voice conversation context from session state.
    
    This tool reads the transcript and extracted parameters from the voice orchestrator
    that were stored in session.state after the voice turn completed.
    
    Returns:
        Dictionary containing:
        - user_transcript: What the user said
        - agent_response: Brief acknowledgment from voice agent
        - intent: Classified intent (book_flight, reimbursement, trip_history)
        - extracted_params: Parsed parameters (origin, destination, date, etc)
        - user_preferences: Loaded from Memory Bank
    """
    voice_context = tool_context.state.get("voice_context", {})
    
    if not voice_context:
        return {
            "status": "no_voice_context",
            "message": "No voice context found in session state"
        }
    
    return {
        "status": "success",
        "user_transcript": voice_context.get("user_input_transcript", ""),
        "agent_response": voice_context.get("agent_output_transcript", ""),
        "intent": voice_context.get("intent", "unknown"),
        "extracted_params": voice_context.get("extracted_params", {}),
        "user_preferences": voice_context.get("user_preferences", {}),
        "timestamp": voice_context.get("timestamp", "")
    }

# Create the tool instance
voice_context_tool = FunctionTool(get_voice_context)