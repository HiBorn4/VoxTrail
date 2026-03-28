# travel_assist_agentic_bot/agents/agent.py
import os
from typing import List, Optional
from travel_assist_agentic_bot.tools.voice_context_tool import voice_context_tool
from pathlib import Path
from loguru import logger
import importlib.util
from google.adk.tools import FunctionTool
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from travel_assist_agentic_bot.tools.function_tools_router import TRIP_FUNCTION_TOOLS, REIMBURSEMENT_FUNCTION_TOOLS
from travel_assist_agentic_bot.schemas import ChatEnvelope, Message, FlightDetails, GetReimbursement  
# from travel_assist_agentic_bot.runtime import auto_save_to_memory_callback
from travel_assist_agentic_bot.config2 import (
    root_instruction,
    travel_request_creation_agent_instruction,
    reimbursement_agent_instructions,
    redis_agent_instructions,
)


'''
APP_NAME: str = "travel-portal"
model_name_root: str = "gemini-2.5-flash"
model_name: str = "gemini-2.5-pro"
"gemini-2.5-flash-lite-preview-06-17"
"gemini-2.5-flash-lite"
gemini-live-2.5-flash-preview-native-audio-09-2025
gemini-live-2.5-flash-preview-native-audio-09-2025
gemini-2.0-flash-live
'''

# def attach_memory_callback(agent):
#     from travel_assist_agentic_bot.runtime import auto_save_to_memory_callback
#     agent.after_agent_callback = auto_save_to_memory_callback

def root_agent() -> LlmAgent:
    agent = LlmAgent(
        name="OrchestratorAgent",
        model="gemini-2.5-flash",
        description="""The Orchestrator Agent is the primary entry point that greets users, 
                    identifies their intent, and routes each query to the correct specialist agent for travel requests, reimbursements, or trip history, 
                    ensuring responses remain within the system’s defined scope.""",
        instruction=root_instruction,
        sub_agents = [travel_request_agent(), reimbursement_agent(), redis_mcp_agent()],
        tools=[PreloadMemoryTool()]
    )
    # attach_memory_callback(agent)
    return agent



def travel_request_agent() -> LlmAgent:
    agent = LlmAgent(
        name="TravelRequestBookingAgent",
        model="gemini-2.5-pro",
        description="""
                    The Travel Booking Agent manages the complete trip creation process – collecting travel details, validating inputs, 
                    and calling SAP tools to draft, price, and finalize flight or non-flight bookings.
                    Can work with voice context when invoked from voice orchestrator.
                    """,
        instruction=travel_request_creation_agent_instruction + """

VOICE MODE SUPPORT:
If invoked from voice orchestrator, first call get_voice_context tool to read:
- user_transcript: What user said
- extracted_params: Parsed travel details (origin, destination, date)
- user_preferences: Seating, meal preferences from memory

Use voice context to pre-fill booking parameters and reduce questions to user.""",
        tools = TRIP_FUNCTION_TOOLS + [voice_context_tool],  # ADD voice_context_tool here
        output_schema=ChatEnvelope
    )
    return agent
    

def reimbursement_agent() -> LlmAgent:
    agent = LlmAgent(
        name="ReimbursementAgent",
        model="gemini-2.5-pro",
        description="""
                    The Reimbursement Agent handles all reimbursement submissions and trip expense history – guiding users through document upload, 
                    analysis, review, and final claim submission.
                    Can work with voice context when invoked from voice orchestrator.
                    """,
        instruction=reimbursement_agent_instructions + """

VOICE MODE SUPPORT:
If invoked from voice orchestrator, first call get_voice_context tool to read user request.
Use voice context to understand which trip needs reimbursement.""",
        tools = REIMBURSEMENT_FUNCTION_TOOLS + [voice_context_tool],  # ADD voice_context_tool here
        output_schema=ChatEnvelope,
        sub_agents = [redis_mcp_agent()]
    )
    return agent
    

server_params = StdioServerParameters(
    command="cmd",
    args=[
        "/c",
        "uvx",
        "--from",
        "redis-mcp-server@latest",
        "redis-mcp-server",
        "--url",
        "redis://10.238.32.19:6378/0"
    ]
)

redis_mcp_toolset = MCPToolset(
    connection_params=StdioConnectionParams(
        server_params=server_params,
        timeout=30000,            # spawn/connect budget (ms)
        request_timeout_s=15.0,   # MCP request/handshake budget (s)
    ),
)


def redis_mcp_agent() -> LlmAgent:   
    agent = LlmAgent(
        name="RedisDataAgent",
        model="gemini-2.5-flash",
        instruction=redis_agent_instructions + """

VOICE MODE SUPPORT:
If invoked from voice orchestrator, first call get_voice_context tool to understand user's query about trip history.""",
        description="Reads Redis Database to access previous trip and expense history using the configured MCP tool. Can work with voice context.",
        tools=[redis_mcp_toolset, voice_context_tool],  # ADD voice_context_tool here
        output_schema=ChatEnvelope
    )
    return agent






