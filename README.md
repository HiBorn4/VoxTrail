# 🎙️ VoxTrail — Voice-Powered Corporate Travel AI

> **Talk your way through business travel.** Book flights, manage reimbursements, and review trip history — all with natural voice commands, powered by Google Gemini Live + a multi-agent AI backend.

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Google ADK](https://img.shields.io/badge/Google%20ADK-Gemini%20Live-4285F4?style=flat-square&logo=google&logoColor=white)](https://ai.google.dev)
[![Redis](https://img.shields.io/badge/Redis-Session%20Store-DC382D?style=flat-square&logo=redis&logoColor=white)](https://redis.io)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

---

## 📸 Demo

> **⚠️ Add your screenshots and screen recordings here (see [Media Guide](#-media-guide) below)**

| Voice Booking Flow | Reimbursement Upload | Trip Dashboard |
|---|---|---|
| `[Screenshot: Voice wave UI + booking confirmation]` | `[Screenshot: Document upload + AI analysis]` | `[Screenshot: Trip history panel]` |

### 🎬 Full Demo Video
```
[Embed a Loom / YouTube walkthrough here]
https://your-demo-link.com
```

---

## 🧠 What Is VoxTrail?

VoxTrail is a **production-grade, voice-first AI assistant** built for corporate travel management. Instead of clicking through clunky travel portals, employees speak naturally:

> *"Book me a flight from Mumbai to Delhi next Friday, economy, aisle seat"*

The system understands, confirms, and books — entirely via voice. Under the hood, a **multi-agent architecture** powered by Google's Agent Development Kit (ADK) routes requests intelligently across specialized AI agents backed by real enterprise APIs (SAP, Redis, custom reimbursement pipelines).

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 🎙️ **Real-time voice interface** | WebSocket-based bidirectional audio using `gemini-live-2.5-flash-preview-native-audio` |
| 🤖 **Multi-agent orchestration** | OrchestratorAgent → TravelBookingAgent / ReimbursementAgent / RedisDataAgent |
| ✈️ **Full flight booking flow** | Search → select → reprice → confirm, with SAP integration |
| 🧾 **Reimbursement AI** | Upload receipts → AI analysis → structured claim submission |
| 📂 **Trip history** | Redis MCP-powered retrieval of past trips and expenses |
| 💬 **Text + voice parity** | SSE-streamed chat fallback for accessibility and testing |
| 🔒 **Enterprise auth** | MSAL-based Azure AD login, AES-encrypted JWT pipeline |
| 🔭 **Observability** | OpenTelemetry tracing → Phoenix dashboard |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT / BROWSER                          │
│   Voice (WebSocket / PCM16) ◄──────────► Text (SSE / REST)     │
└──────────────────────┬──────────────────────────────────────────┘
                       │
              ┌────────▼────────┐
              │   FastAPI App   │  ← MSAL Auth · AES JWT · CORS
              │   (app.py)      │
              └──┬──────────┬───┘
                 │          │
    ┌────────────▼──┐    ┌──▼────────────────┐
    │ Voice WS      │    │   REST/SSE Chat    │
    │ Handler       │    │   Endpoints        │
    │ (Google ADK   │    │   (InMemoryRunner) │
    │  LiveRunner)  │    └──────────┬─────────┘
    └──────┬────────┘               │
           │                        │
     ┌─────▼────────────────────────▼──────┐
     │         OrchestratorAgent            │
     │         (gemini-2.5-flash)           │
     │         Intent routing · Memory      │
     └─────┬────────────┬──────────┬────────┘
           │            │          │
  ┌────────▼──┐  ┌──────▼──┐  ┌───▼───────────┐
  │  Travel   │  │ Reimburse│  │  RedisData    │
  │  Booking  │  │ Agent    │  │  Agent        │
  │  Agent    │  │ (2.5-pro)│  │  (2.5-flash)  │
  │ (2.5-pro) │  └──────────┘  └───────────────┘
  └──────┬────┘        │               │
         │        Reimbursement      Redis MCP
      SAP APIs      APIs            Server (MCP)
   (flights, trips, CSRF)
```

> 📌 See `architecture.svg` in the repo root for the full visual diagram.

---

## 📁 Project Structure

```
VoxTrail/
│
├── app.py                          # FastAPI entry point, auth, all routes
├── runtime.py                      # ADK Runner + Phoenix OTEL setup
├── agent.py                        # Multi-agent definitions (Orchestrator, Travel, Reimbursement, Redis)
├── voice_orchestrator_agent.py     # Gemini Live voice agent + tool delegation
├── voice_websocket_handler.py      # WebSocket lifecycle, ADK LiveRunner integration
├── voice_tool_delegates.py         # Bridge: voice agent → backend specialist agents
├── voice_context_tool.py           # Shared tool: passes voice context to sub-agents
│
├── config2.py                      # App config, agent instructions, DEFAULT_TRAVEL_STATE schema
├── schemas.py                      # Pydantic models: ChatEnvelope, FlightDetails, etc.
├── schema_with_travel_dict.py      # Extended schema variants
│
├── function_tools_router.py        # All SAP-facing function tool definitions
├── cancel_trip.py                  # Trip cancellation API wrapper
├── check_trip_validity.py          # Trip validation logic
├── post_es_final.py                # Non-flight booking finalization
├── post_es_final_flight.py         # Flight booking finalization (SAP)
├── post_es_get.py                  # Non-flight search
├── post_es_get_flight.py           # Flight search API
├── post_es_reprice.py              # Repricing flow
├── reimbursement_api.py            # Receipt analysis API
├── reimbursement_submit.py         # Claim submission
├── sap_csrf.py                     # SAP CSRF token fetch
├── trip_details_api.py             # Individual trip detail retrieval
│
├── session_service.py              # ADK session create/read/diff/merge
├── redis_manager.py                # RedisJSONManager: hierarchical key store
├── session_cleanup.py              # Session + Redis data cleanup
├── permanent_store.py              # Persistent chat history (DB)
├── chat_extract.py                 # Extract message pairs from ADK events
│
├── utils.py                        # JWT decode, user extraction, trip categorizer
├── env_loader.py                   # .env loading helper
│
└── voicebot/                       # Standalone voice client utilities
    ├── realtime_speechbot.py       # Azure OpenAI Realtime client (mic → API → speaker)
    ├── realtime_speechbot_copy.py  # Experimental variant
    ├── realtime_transcribing.py    # Live transcription only mode
    └── wav_to_mp4.py               # Audio format converter
```

---

## ⚡ Quick Start

### Prerequisites

- Python 3.11+
- Redis server (local or remote)
- Google Cloud project with Gemini API access
- SAP Travel API credentials (for full booking flow)
- Azure AD app registration (for enterprise auth)

### 1. Clone & Install

```bash
git clone https://github.com/hiborn4/VoxTrail.git
cd VoxTrail

python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Google AI
GOOGLE_API_KEY=your_gemini_api_key
GOOGLE_CLOUD_PROJECT=your_gcp_project_id

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=

# Auth
JWT_SECRET_KEY=your_jwt_secret_here
AES_SECRET_KEY=your_16_byte_aes_key

# Azure AD (optional, for enterprise auth)
AZURE_CLIENT_ID=
AZURE_CLIENT_SECRET=
AZURE_TENANT_ID=

# SAP (optional, for booking integration)
SAP_BASE_URL=
SAP_API_KEY=
```

### 3. Start Redis

```bash
# Docker (recommended)
docker run -d -p 6379:6379 redis:alpine

# Or local install
redis-server
```

### 4. Run

```bash
uvicorn app:app --reload --port 8000
```

Visit `http://localhost:8000/docs` for the interactive API explorer.

For voice, open the frontend on port 3000 (or 5173 for Vite dev server) and connect via WebSocket to `/ws/voice/{session_id}`.

---

## 🎙️ How the Voice Flow Works

```
User speaks → Browser captures PCM16 audio
    → WebSocket stream → FastAPI /ws/voice/{session_id}
    → Google ADK LiveRunner (voice_orchestrator_agent)
    → Gemini Live understands intent
    → Delegates to specialist agent via tool call
    → Specialist agent calls SAP / Redis APIs
    → Returns structured ChatEnvelope response
    → ADK synthesizes voice response (voice: "Puck")
    → Audio streamed back to browser → Speaker playback
```

Key technical choices:
- **Bidirectional streaming** with `RunConfig(streaming_mode="bidi")`
- **Server VAD** for natural turn detection (silence_duration_ms=1000)
- **Session resumption** via transparent ADK config for reconnect resilience
- **Voice context tool** bridges voice agent → sub-agents without losing transcript context

---

## 🤖 Agent Architecture Deep Dive

### OrchestratorAgent (`gemini-2.5-flash`)
Pure routing agent. Receives user message → detects intent → delegates to correct specialist. Never calls tools directly, never makes up booking data.

### TravelBookingAgent (`gemini-2.5-pro`)
Manages the full booking lifecycle:
1. Collect travel details (origin, destination, dates, class, cost center)
2. Search flights via SAP API
3. Present options, handle user selection
4. Reprice selected flight
5. Confirm and finalize booking

### ReimbursementAgent (`gemini-2.5-pro`)
- Guides user through document upload
- Calls AI analysis API to extract line items from receipts
- Reviews results with user
- Submits structured claim

### RedisDataAgent (`gemini-2.5-flash`)
- Uses Redis MCP Server to read trip and expense history
- Answers questions about past travel without SAP API calls

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **API Framework** | FastAPI + Uvicorn |
| **AI Agents** | Google ADK (Agent Development Kit) |
| **LLMs** | Gemini 2.5 Flash, Gemini 2.5 Pro, Gemini Live Flash |
| **Voice** | Google Gemini Live (native audio), Azure OpenAI Realtime (voicebot/) |
| **Session Store** | Redis (via RedisJSONManager + MCP Server) |
| **Auth** | MSAL / Azure AD + AES-encrypted JWT |
| **Observability** | OpenTelemetry + Phoenix (Arize) |
| **Data Models** | Pydantic v2 |
| **Database** | SQLAlchemy (permanent chat store) |

---

## 📸 Media Guide

### What Screenshots to Capture

1. **Voice interface active state** — Show the waveform animation while speaking. Ideal: side by side with the bot's text response appearing simultaneously.
2. **Booking confirmation screen** — After the AI confirms a flight, capture the full `ChatEnvelope` response rendered in the frontend with flight details, seat class, and cost center.
3. **Reimbursement flow** — Screenshot the document upload step, then the AI's extracted line-item analysis.
4. **Trip history panel** — Show the categorized trip list (upcoming / in-progress / past) with trip IDs.
5. **Architecture diagram** — Use the `architecture.svg` included in this repo.

### Screen Recording Tips

| Clip | Duration | What to Show |
|---|---|---|
| Full voice booking | ~45s | Speak a flight request → confirmation → done |
| Reimbursement upload | ~30s | Upload receipt → AI response → submit |
| System overview | ~20s | Pan through the architecture diagram |

**Recommended tools:**
- [Loom](https://loom.com) — Free, shareable, great for portfolio
- [OBS Studio](https://obsproject.com) — Full control, local recording
- [Kap](https://getkap.co) — macOS GIF/MP4 export

**For GIFs:** Use [Gifski](https://gif.ski) or export from Kap. Ideal size: 800×500px, under 5MB.

---

## 🌐 Deployment Options

Since VoxTrail uses WebSockets + Redis + environment secrets, serverless platforms like Vercel won't work directly. Recommended free-tier options:

| Platform | Notes |
|---|---|
| **Google Cloud Run** | Ideal — native Gemini integration, WebSocket support, scales to zero |
| **Railway** | Easy Redis + FastAPI deploy, generous free tier |
| **Render** | Free tier supports persistent services + Redis add-on |

> 💡 The project already contains Cloud Run origins in CORS config (`asia-south1.run.app`), so Cloud Run is the natural deployment target.

**Minimum deploy checklist:**
- [ ] Set all environment variables in your platform's secret manager
- [ ] Provision a Redis instance (Railway Redis, Upstash, or Cloud Memorystore)
- [ ] Build Docker image: `docker build -t VoxTrail .`
- [ ] Configure WebSocket idle timeout > 60s (Cloud Run: `--timeout 300`)

---

## 🗺️ Roadmap

- [ ] Frontend UI (React voice client with waveform visualization)
- [ ] `.env.example` template
- [ ] `requirements.txt` with pinned versions
- [ ] Docker Compose for local full-stack development
- [ ] Unit tests for agent routing and tool delegates
- [ ] Support for multi-city itineraries
- [ ] Hotel and car rental booking agents

---

## 🤝 Contributing

Pull requests are welcome. For major changes, please open an issue first.

```bash
# Lint
ruff check .

# Format
black .
```

---

## 📄 License

MIT © 2025 — Built with ❤️ and a lot of voice commands.

---

*Built using [Google Agent Development Kit](https://ai.google.dev/adk), [FastAPI](https://fastapi.tiangolo.com), and [Gemini Live](https://ai.google.dev/gemini-api/docs/live).*
