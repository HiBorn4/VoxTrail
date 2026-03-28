# travel_assist_agentic_bot/runtime.py
from __future__ import annotations

import os
import logging
from typing import Any, Dict, List, Optional, Tuple
from travel_assist_agentic_bot.agents.voice_orchestrator_agent import voice_orchestrator_agent
from google.adk.runners import InMemoryRunner
import os
from dotenv import load_dotenv

load_dotenv()

# ADK core
from google.adk.runners import Runner
from google.adk.models import LlmRequest
from google.genai import types as genai_types
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import ToolContext

# Your app wiring
from .agents.agent import root_agent
from .services.session_service import get_session_service
from .config2 import APP_NAME

# ---- OpenTelemetry / Phoenix (HTTP only) ----
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
# ⬇️ HTTP exporter (replaces prior gRPC exporter)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from phoenix.otel import register as phoenix_register


load_dotenv(override=True)
logger = logging.getLogger(__name__)

_tracer: Optional[trace.Tracer] = None


def _get_tracer() -> trace.Tracer:
    global _tracer
    if _tracer is None:
        _tracer = trace.get_tracer(__name__)
    return _tracer


def _setup_phoenix_otel() -> None:
    """
    Initialize OTLP → Phoenix tracing over HTTP if PHOENIX_OTLP_ENDPOINT is set.
    Safe to call multiple times; setup will only happen once per process.

    Expect endpoint like:
      https://<phoenix-cloud-run-url>/v1/traces
    """
    endpoint = "http://localhost:6006/v1/traces"
    if not endpoint:
        logger.info("Phoenix tracing disabled (PHOENIX_OTLP_ENDPOINT not set).")
        return

    # If already initialized by someone else, don't double-initialize.
    if isinstance(trace.get_tracer_provider(), TracerProvider):
        logger.info("TracerProvider already initialized; skipping.")
        return

    service_name = "travel_assist_agent"
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    trace.set_tracer_provider(provider)

    # HTTP exporter → Phoenix (/v1/traces). No 'insecure' flag on HTTP exporter.
    exporter = OTLPSpanExporter(endpoint=endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))


    try:
        phoenix_register(project_name=service_name,
                        endpoint=endpoint,
                        auto_instrument=True
                        )
        logger.info("Phoenix auto-instrumentation registered.")
    except Exception:
        logger.exception("phoenix.otel.register failed; continuing with raw OTLP exporter only.")

    logger.info("OTel → Phoenix (HTTP) configured (endpoint=%s, service.name=%s)", endpoint, service_name)

def initialize_voice_agent():
    """
    Initialize voice orchestrator agent
    Call this on app startup
    """
    try:
        # Create voice agent runner
        voice_runner = InMemoryRunner(
            app_name=os.getenv("APP_NAME", "travel-portal-voice"),
            agent=voice_orchestrator_agent
        )
        
        print("✓ Voice orchestrator agent initialized")
        return voice_runner
        
    except Exception as e:
        print(f"✗ Failed to initialize voice agent: {e}")
        raise

# -------------------------
# ADK callback instrumentation (lenient)
# -------------------------
def _before_model_cb(*args, **kwargs) -> Optional[genai_types.Content]:
    """
    Lenient before-model callback.
    Accepts both (callback_context, llm_request) and variations ADK may pass.
    """
    try:
        cb: CallbackContext = kwargs.get("callback_context") or args[0]
    except Exception:
        return None

    # LlmRequest can arrive as 'llm_request' or 'request'
    llm_req: Optional[LlmRequest] = kwargs.get("llm_request") or kwargs.get("request")

    tracer = _get_tracer()
    span = tracer.start_span(
        "llm.generate_content",
        attributes={
            "adk.agent_name": getattr(cb, "agent_name", ""),
            "adk.invocation_id": getattr(cb, "invocation_id", ""),
            "adk.session_id": cb.state.get("app:session_id", ""),
            "adk.user_id": cb.state.get("app:user_id", ""),
            "ai.model": getattr(llm_req, "model", "") if llm_req else "",
        },
    )
    # stash on context for _after_model_cb via callback_context (safe attach)
    setattr(cb, "_runtime_active_span", span)
    return None


def _after_model_cb(*args, **kwargs) -> Optional[genai_types.Content]:
    """
    Lenient after-model callback.
    Accepts both (callback_context, llm_response) and variations ADK may pass.
    """
    try:
        cb: CallbackContext = kwargs.get("callback_context") or args[0]
    except Exception:
        return None

    llm_resp: Optional[genai_types.GenerateContentResponse] = (
        kwargs.get("llm_response") or kwargs.get("response")
    )

    span = getattr(cb, "_runtime_active_span", None)
    if span is not None:
        try:
            # add a tiny bit of context (finish reason when available)
            finish_reason = ""
            try:
                if llm_resp and getattr(llm_resp, "candidates", None):
                    finish_reason = getattr(llm_resp.candidates[0], "finish_reason", "") or ""
            except Exception:
                pass
            span.set_attribute("ai.finish_reason", finish_reason)
        finally:
            span.end()
            setattr(cb, "_runtime_active_span", None)
    return None


def _before_tool_cb(*args, **kwargs) -> None:
    """
    Lenient before-tool callback.
    Accepts both (callback_context, tool_name, args) and variations ADK may pass.
    """
    try:
        tc: ToolContext = kwargs.get("callback_context") or args[0]
    except Exception:
        return None

    tool_name: str = kwargs.get("tool_name", "") or ""
    tool_args: Dict[str, Any] = kwargs.get("args", {}) or {}

    tracer = _get_tracer()
    span = tracer.start_span(
        f"tool.{tool_name or 'unknown'}",
        attributes={
            "adk.agent_name": getattr(tc, "agent_name", ""),
            "adk.invocation_id": getattr(tc, "invocation_id", ""),
            "adk.function_call_id": getattr(tc, "function_call_id", ""),
            "adk.session_id": tc.state.get("app:session_id", ""),
            "adk.user_id": tc.state.get("app:user_id", ""),
            "tool.name": tool_name,
            "tool.args_keys": ",".join(sorted(tool_args.keys())) if isinstance(tool_args, dict) else "",
        },
    )
    setattr(tc, "_runtime_active_span", span)


def _after_tool_cb(*args, **kwargs) -> None:
    """
    Lenient after-tool callback.
    Accepts both (callback_context, tool_name, result) and variations ADK may pass.
    """
    try:
        tc: ToolContext = kwargs.get("callback_context") or args[0]
    except Exception:
        return None

    result: Any = kwargs.get("result")
    span = getattr(tc, "_runtime_active_span", None)
    if span is not None:
        try:
            status = "success"
            if isinstance(result, dict) and (result.get("error") or result.get("status") == "error"):
                status = "error"
            span.set_attribute("tool.status", status)
        finally:
            span.end()
            setattr(tc, "_runtime_active_span", None)


def _wire_callbacks(agent) -> None:
    """Attach our tolerant callbacks onto the agent."""
    agent.before_model_callback = _before_model_cb
    agent.after_model_callback = _after_model_cb
    agent.before_tool_callback = _before_tool_cb
    agent.after_tool_callback = _after_tool_cb


# -------------------------
# Runner construction
# -------------------------
def build_runner() -> Runner:
    """
    Build a Runner with:
      - Phoenix/OTel tracing (HTTP) if configured
      - Your travel agent
      - Persistent session service
    """
    _setup_phoenix_otel()

    agent = root_agent()
    _wire_callbacks(agent)

    session_service = get_session_service()
    return Runner(agent=agent, session_service=session_service, app_name=APP_NAME)


# Export a singleton Runner for app.py
runner: Runner = build_runner()


async def run_agent_turn(
    *,
    user_id: str,
    session_id: str,
    user_content: genai_types.Content,
) -> Tuple[str, List[str]]:
    """
    Run one agent turn and collect the text output, using the exact loop you provided.

    Returns:
        reply_text (str): concatenated text from the agent for this turn.
        all_text_parts (List[str]): list of each text part encountered (for debugging/logging).
    """
    final_text_parts: List[str] = []
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=user_content,
        ):
            content = getattr(event, "content", None)
            parts = getattr(content, "parts", []) if content else []
            for p in parts or []:
                if getattr(p, "text", None):
                    final_text_parts.append(p.text)
            if getattr(event, "turn_complete", False):
                break
    except Exception as e:
        logger.exception("Runner.run_async failed")
        # Re-raise so the caller (e.g., FastAPI handler) can respond with 500
        raise

    return "".join(final_text_parts), final_text_parts


def get_runner() -> Runner:
    """Optional accessor if you prefer importing a function."""
    return runner
