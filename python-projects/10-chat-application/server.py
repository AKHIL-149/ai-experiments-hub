"""Chat Application FastAPI Server"""

import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Cookie, Response, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Literal
from urllib.parse import urlparse
import uvicorn
import os
import hashlib
from pathlib import Path
from dotenv import load_dotenv

# Load environment (before the imports below read it)
load_dotenv()

from src.core.database import DatabaseManager, User, Conversation, Message
from src.core.auth_manager import AuthManager
from src.core.llm_client import LLMClient
from src.core.rate_limit import FailureThrottle

# Size limits. Nothing used to be bounded: a 5 MB message or a 1 MB system prompt was stored and
# then sent to the model with every later request.
MAX_MESSAGE_CHARS = int(os.getenv('MAX_MESSAGE_CHARS', 20000))
MAX_SYSTEM_PROMPT_CHARS = int(os.getenv('MAX_SYSTEM_PROMPT_CHARS', 8000))
# The model sees at most this much of a conversation (newest messages win)
CLOUD_HISTORY_CHARS = 400000
HISTORY_MESSAGES = 20

# Failed logins allowed per username and client before further attempts get a 429
login_throttle = FailureThrottle(
    max_failures=int(os.getenv('LOGIN_MAX_FAILURES', 10)),
    window_seconds=int(os.getenv('LOGIN_WINDOW_SECONDS', 300)),
)

# Initialize FastAPI
app = FastAPI(title="Chat Application", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv('ALLOWED_ORIGINS', 'http://localhost:8000').split(','),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database
db_manager = DatabaseManager(os.getenv('DATABASE_URL'))

# Sessions are only ever deleted when they are used again after expiring, so abandoned ones
# (every closed guest tab) piled up forever
with db_manager.get_session() as _db:
    AuthManager(_db).cleanup_expired_sessions()

# LLM Client
llm_client = LLMClient()

# Templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


def static_version(rel_path: str) -> str:
    """
    Short cache-busting token for a static asset, derived from its mtime.

    StaticFiles serves no explicit Cache-Control header, so browsers
    fall back to heuristic caching (RFC 7234) off Last-Modified alone -
    which can and does serve a stale script/stylesheet indefinitely
    across edits without ever revalidating. Confirmed live here: after
    editing styles.css, a plain reload (and even a fresh navigation)
    kept rendering the pre-edit CSS - a direct fetch() of the same URL
    got the new content, but the real <link>/<script> tag load did
    not. Appending ?v=<mtime-hash> changes the URL itself whenever the
    file changes, bypassing heuristic caching without touching the
    StaticFiles mount. Same fix already applied in projects 11 and 12.
    """
    try:
        mtime = os.path.getmtime(Path("static") / rel_path)
        return hashlib.md5(str(mtime).encode()).hexdigest()[:8]
    except OSError:
        return "0"


templates.env.globals["static_version"] = static_version

# WebSocket connection registry
active_connections: Dict[str, List[WebSocket]] = {}


# Pydantic models
Provider = Literal['ollama', 'openai', 'anthropic']


class RegisterRequest(BaseModel):
    username: str = Field(max_length=200)
    email: str = Field(max_length=200)
    password: str = Field(max_length=1000)


class LoginRequest(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=1000)


class ConversationCreate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    llm_provider: Optional[Provider] = 'ollama'
    llm_model: Optional[str] = Field(None, max_length=100)
    system_prompt: Optional[str] = Field(None, max_length=MAX_SYSTEM_PROMPT_CHARS)


class ConversationUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    llm_provider: Optional[Provider] = None
    llm_model: Optional[str] = Field(None, max_length=100)
    system_prompt: Optional[str] = Field(None, max_length=MAX_SYSTEM_PROMPT_CHARS)


class MessageCreate(BaseModel):
    content: str = Field(max_length=MAX_MESSAGE_CHARS)

    @field_validator('content')
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Message cannot be empty')
        return value


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    """
    Every page script shows `error.detail` to the user, and FastAPI's own 422 body has a list of
    objects there, which they rendered as "[object Object]". Say it in words instead.
    """
    problems = []
    for err in exc.errors():
        field = ".".join(str(part) for part in err.get("loc", ()) if part not in ("body", "query"))
        message = str(err.get("msg", "Invalid value")).removeprefix("Value error, ")
        problems.append(f"{field}: {message}" if field else message)
    return JSONResponse(status_code=422, content={"detail": "; ".join(problems) or "Invalid request"})


# Dependency: Get current user from session cookie
async def get_current_user(session_token: Optional[str] = Cookie(None)) -> User:
    """Validate session and return current user"""
    if not session_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    with db_manager.get_session() as db:
        auth_manager = AuthManager(db)
        user = auth_manager.validate_session(session_token)

        if not user:
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        return user


# Routes

@app.get("/")
async def index(request: Request):
    """Serve main HTML page"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "ok",
        "database": "connected",
        "llm_providers": llm_client.get_available_providers()
    }


@app.get("/api/models")
async def list_models(user: User = Depends(get_current_user)):
    """Models that can really be used: what Ollama has installed (the cloud lists are fixed)"""
    return {"ollama": await llm_client.list_ollama_models()}


# Authentication endpoints

def client_key(request: Request) -> str:
    return request.client.host if request.client else 'unknown'


# The three handlers below are plain `def` on purpose: FastAPI runs those in a worker thread.
# bcrypt takes ~0.25 s of CPU per hash, and as `async def` every login or guest sign-in froze
# every open chat stream for that long.

@app.post("/api/auth/register")
def register(data: RegisterRequest, response: Response):
    """Register new user"""
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db)
        success, user, error = auth_manager.register_user(
            data.username, data.email, data.password
        )

        if not success:
            raise HTTPException(status_code=400, detail=error)

        # Create session
        session_token = auth_manager.create_session(user)

        # Set HTTPOnly cookie
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=os.getenv('COOKIE_SECURE', 'false').lower() == 'true',
            samesite='strict',
            max_age=30 * 24 * 60 * 60  # 30 days
        )

        return user.to_dict()


@app.post("/api/auth/login")
def login(data: LoginRequest, request: Request, response: Response):
    """Login user"""
    throttle_key = f"{client_key(request)}|{data.username.lower()}"
    wait = login_throttle.retry_after(throttle_key)
    if wait:
        raise HTTPException(
            status_code=429,
            detail=f"Too many failed logins. Try again in {wait} seconds.",
            headers={"Retry-After": str(wait)},
        )

    with db_manager.get_session() as db:
        auth_manager = AuthManager(db)
        user = auth_manager.authenticate(data.username, data.password)

        if not user:
            login_throttle.record_failure(throttle_key)
            raise HTTPException(status_code=401, detail="Invalid credentials")

        login_throttle.reset(throttle_key)

        # Create session
        session_token = auth_manager.create_session(user)

        # Set HTTPOnly cookie
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=os.getenv('COOKIE_SECURE', 'false').lower() == 'true',
            samesite='strict',
            max_age=30 * 24 * 60 * 60
        )

        return user.to_dict()


@app.post("/api/auth/guest")
def guest_login(response: Response):
    """Create a temporary guest account and log in as it - no signup
    form required. Mirrors /api/auth/login's session/cookie setup."""
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db)
        success, user, error = auth_manager.create_guest_user()

        if not success:
            raise HTTPException(status_code=500, detail=error)

        session_token = auth_manager.create_session(user)

        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=os.getenv('COOKIE_SECURE', 'false').lower() == 'true',
            samesite='strict',
            max_age=30 * 24 * 60 * 60
        )

        return user.to_dict()


@app.post("/api/auth/logout")
async def logout(response: Response, session_token: Optional[str] = Cookie(None)):
    """Logout user"""
    if session_token:
        with db_manager.get_session() as db:
            auth_manager = AuthManager(db)
            auth_manager.delete_session(session_token)

    response.delete_cookie("session_token")
    return {"success": True}


@app.get("/api/auth/me")
async def get_current_user_info(user: User = Depends(get_current_user)):
    """Get current user info"""
    return user.to_dict()


# Conversation endpoints

@app.post("/api/conversations")
async def create_conversation(
    data: ConversationCreate,
    user: User = Depends(get_current_user)
):
    """Create new conversation"""
    with db_manager.get_session() as db:
        conversation = Conversation(
            user_id=user.id,
            title=data.title,
            llm_provider=data.llm_provider,
            llm_model=data.llm_model,
            system_prompt=data.system_prompt
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

        return conversation.to_dict()


@app.get("/api/conversations")
async def list_conversations(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user)
):
    """List user's conversations"""
    with db_manager.get_session() as db:
        conversations = db.query(Conversation).filter(
            Conversation.user_id == user.id
        ).order_by(Conversation.updated_at.desc()).limit(limit).offset(offset).all()

        total = db.query(Conversation).filter(Conversation.user_id == user.id).count()

        return {
            "conversations": [c.to_dict() for c in conversations],
            "total": total,
            "has_more": offset + limit < total
        }


@app.get("/api/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user)
):
    """Get conversation with messages"""
    with db_manager.get_session() as db:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id
        ).first()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return conversation.to_dict(include_messages=True)


@app.patch("/api/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    data: ConversationUpdate,
    user: User = Depends(get_current_user)
):
    """Update conversation"""
    with db_manager.get_session() as db:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id
        ).first()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Update fields
        if data.title is not None:
            conversation.title = data.title
        if data.llm_provider is not None:
            conversation.llm_provider = data.llm_provider
        if data.llm_model is not None:
            conversation.llm_model = data.llm_model
        if data.system_prompt is not None:
            conversation.system_prompt = data.system_prompt

        db.commit()
        db.refresh(conversation)

        return conversation.to_dict()


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user)
):
    """Delete conversation"""
    with db_manager.get_session() as db:
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id
        ).first()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        db.delete(conversation)
        db.commit()

        return {"success": True}


# Message endpoints

@app.post("/api/conversations/{conversation_id}/messages")
async def create_message(
    conversation_id: str,
    data: MessageCreate,
    user: User = Depends(get_current_user)
):
    """Create new message"""
    with db_manager.get_session() as db:
        # Verify conversation ownership
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id
        ).first()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Create message
        message = Message(
            conversation_id=conversation_id,
            role='user',
            content=data.content
        )

        db.add(message)
        db.commit()
        db.refresh(message)

        return message.to_dict()


@app.get("/api/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user)
):
    """List conversation messages"""
    with db_manager.get_session() as db:
        # Verify conversation ownership
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id
        ).first()

        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        messages = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at).limit(limit).offset(offset).all()

        total = db.query(Message).filter(Message.conversation_id == conversation_id).count()

        return {
            "messages": [m.to_dict() for m in messages],
            "total": total
        }


# WebSocket endpoint

def allowed_origins() -> List[str]:
    return [o.strip() for o in os.getenv('ALLOWED_ORIGINS', 'http://localhost:8000').split(',') if o.strip()]


def origin_allowed(origin: Optional[str], host: Optional[str]) -> bool:
    """
    Browsers send no CORS preflight for a WebSocket, and SameSite=Strict is "same site", not
    "same origin": a page on another port of localhost (any other dev server) is same-site, so
    the browser attached the session cookie to its connection and it could chat as the user.
    Accept the page's own origin (Origin host == Host header) and ALLOWED_ORIGINS. Clients that
    send no Origin are not browsers and cannot ride a cookie, so they are let through.
    """
    if not origin:
        return True
    if origin in allowed_origins():
        return True
    return bool(host) and urlparse(origin).netloc == host


def history_for_model(conversation: Conversation, provider: Optional[str]) -> List[Dict[str, str]]:
    """
    System prompt plus the newest messages that fit what the model can read.

    Ollama's default window is small and it drops the OLDEST text silently, so budget the
    history here rather than letting the server decide what the model forgets.
    """
    budget = llm_client.num_ctx * 3 if provider in (None, 'ollama') else CLOUD_HISTORY_CHARS
    system = []
    if conversation.system_prompt:
        system = [{'role': 'system', 'content': conversation.system_prompt}]
        budget -= len(conversation.system_prompt)

    kept: List[Dict[str, str]] = []
    for msg in reversed(conversation.messages[-HISTORY_MESSAGES:]):
        if kept and len(msg.content) > budget:
            break  # always keep the newest message, whatever its size
        budget -= len(msg.content)
        kept.append({'role': msg.role, 'content': msg.content})
    kept.reverse()
    return system + kept


async def send_event(websocket: WebSocket, payload: dict) -> bool:
    """Send to the browser; False when it has gone away"""
    try:
        await websocket.send_json(payload)
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False


@app.websocket("/ws/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    conversation_id: str,
    session_token: Optional[str] = Cookie(None)
):
    """WebSocket for real-time chat streaming"""
    if not origin_allowed(websocket.headers.get('origin'), websocket.headers.get('host')):
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    # Authenticate
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db)
        user = auth_manager.validate_session(session_token)

        if not user:
            await websocket.close(code=1008, reason="Not authenticated")
            return

        # Verify conversation ownership
        conversation = db.query(Conversation).filter(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id
        ).first()

        if not conversation:
            await websocket.close(code=1008, reason="Conversation not found")
            return

        user_id = user.id

    await websocket.accept()

    # Register connection
    active_connections.setdefault(conversation_id, []).append(websocket)

    try:
        while True:
            # Receive user message. A frame that is not a JSON object used to raise out of the
            # handler (killing the connection with a traceback), or crash on `.get`.
            try:
                data = await websocket.receive_json()
            except (ValueError, KeyError, TypeError):
                if not await send_event(websocket, {'type': 'error', 'error': 'Messages must be JSON objects'}):
                    break
                continue

            if not isinstance(data, dict) or data.get('type') != 'message':
                continue

            user_content = data.get('content')
            problem = None
            if not isinstance(user_content, str) or not user_content.strip():
                problem = 'Message cannot be empty'
            elif len(user_content) > MAX_MESSAGE_CHARS:
                problem = f'Message is too long ({len(user_content)} characters, the limit is {MAX_MESSAGE_CHARS})'
            if problem:
                if not await send_event(websocket, {'type': 'error', 'error': problem}):
                    break
                continue

            # Re-check on every message: logging out, or deleting the conversation, used to leave
            # an already-open socket working (and deleting it crashed the handler).
            with db_manager.get_session() as db:
                if not AuthManager(db).validate_session(session_token):
                    await websocket.close(code=1008, reason="Session expired")
                    break

                conversation = db.query(Conversation).filter(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id
                ).first()
                if not conversation:
                    await send_event(websocket, {'type': 'error', 'error': 'This conversation was deleted'})
                    await websocket.close(code=1008, reason="Conversation not found")
                    break

                db.add(Message(
                    conversation_id=conversation_id,
                    role='user',
                    content=user_content
                ))
                db.commit()
                db.refresh(conversation)

                provider = conversation.llm_provider
                model = conversation.llm_model
                messages = history_for_model(conversation, provider)

            # Stream LLM response
            assistant_content = ""
            assistant_message_id = None
            stream = llm_client.stream_completion(messages, provider, model)

            try:
                async for token in stream:
                    assistant_content += token

                    # Send token to client
                    if not await send_event(websocket, {'type': 'token', 'token': token}):
                        return  # the browser left: stop generating

                # A provider that produced nothing is a failure, not an empty answer: saving
                # it left a blank assistant message in the history of every later request.
                if not assistant_content.strip():
                    raise RuntimeError("The model returned an empty response. Try again, or pick another model.")

                # Save assistant message
                with db_manager.get_session() as db:
                    assistant_message = Message(
                        conversation_id=conversation_id,
                        role='assistant',
                        content=assistant_content
                    )
                    db.add(assistant_message)

                    # Update conversation title if first message
                    conversation = db.query(Conversation).filter(
                        Conversation.id == conversation_id
                    ).first()

                    if conversation is None:
                        raise RuntimeError("This conversation was deleted while the model was answering")

                    if not conversation.title:
                        conversation.title = user_content[:50] + ('...' if len(user_content) > 50 else '')

                    db.commit()
                    db.refresh(assistant_message)
                    assistant_message_id = assistant_message.id

                # Send completion
                if not await send_event(websocket, {'type': 'done', 'message_id': assistant_message_id}):
                    return

            except Exception as e:
                if not await send_event(websocket, {'type': 'error', 'error': str(e)}):
                    return
            finally:
                await stream.aclose()

    except WebSocketDisconnect:
        pass
    finally:
        # Every way out of the handler, not just a clean disconnect, must forget the socket
        connections = active_connections.get(conversation_id, [])
        if websocket in connections:
            connections.remove(websocket)
        if not connections:
            active_connections.pop(conversation_id, None)


# Image Generation Endpoint

# One image at a time: the pipeline is a single shared model and each run needs gigabytes
image_lock = asyncio.Lock()

# What DALL-E 3 accepts
DALLE_SIZES = ((1024, 1024), (1792, 1024), (1024, 1792))


class ImageGenerationRequest(BaseModel):
    prompt: str = Field(max_length=1000)
    provider: str = 'stable-diffusion'
    # Unbounded sizes let one request ask a local GPU for a 100000x100000 image
    width: int = Field(512, ge=64, le=1024, multiple_of=8)
    height: int = Field(512, ge=64, le=1024, multiple_of=8)

    @field_validator('prompt')
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Prompt cannot be empty')
        return value


def dalle_size(width: int, height: int) -> str:
    """The DALL-E 3 size closest to the shape asked for (it rejects every other size)"""
    wide = width / height
    best = min(DALLE_SIZES, key=lambda size: abs(size[0] / size[1] - wide))
    return f"{best[0]}x{best[1]}"


def generate_local_image(prompt: str, width: int, height: int) -> str:
    """Blocking: run it in a worker thread. Returns the URL of the saved PNG."""
    import uuid
    from src.local_sd_service import get_service

    image = get_service().generate_image(prompt=prompt, width=width, height=height, steps=20)

    image_id = str(uuid.uuid4())
    images_dir = Path("static/generated_images")
    images_dir.mkdir(exist_ok=True)
    image.save(images_dir / f"{image_id}.png", format='PNG')
    return f"/static/generated_images/{image_id}.png"


@app.post("/api/generate-image")
async def generate_image(
    request: ImageGenerationRequest,
    session_token: Optional[str] = Cookie(None)
):
    """
    Generate image using local Stable Diffusion or cloud providers

    Supported providers:
    - stable-diffusion (local, in-process via the diffusers library)
    - dall-e (OpenAI DALL-E)
    """
    with db_manager.get_session() as db:
        if not AuthManager(db).validate_session(session_token):
            raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        if request.provider == 'stable-diffusion':
            # Generation takes tens of seconds of blocking work. It ran on the event loop (and
            # inside an open database session), so every chat in the app froze until it ended.
            async with image_lock:
                try:
                    image_url = await run_in_threadpool(
                        generate_local_image, request.prompt, request.width, request.height
                    )
                except ImportError:
                    raise HTTPException(
                        status_code=503,
                        detail="Stable Diffusion dependencies not installed. Run: pip install diffusers transformers accelerate"
                    )

            return {
                "success": True,
                "image_url": image_url,
                "prompt": request.prompt,
                "provider": "local-stable-diffusion"
            }

        elif request.provider == 'dall-e':
            # Same placeholder-key check as LLMClient (src/core/llm_client.py) -
            # "if not os.getenv(...)" alone treats the untouched
            # .env.example value "your_openai_key_here" as a real,
            # configured key (it's a non-empty string), so this would
            # otherwise call OpenAI with it and surface a raw 401
            # instead of this clear "not configured" message.
            openai_key = os.getenv('OPENAI_API_KEY')
            if not openai_key or openai_key.startswith('your_'):
                raise HTTPException(
                    status_code=400,
                    detail="OpenAI API key not configured"
                )

            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=openai_key)

            response = await client.images.generate(
                model="dall-e-3",
                prompt=request.prompt,
                size=dalle_size(request.width, request.height),
                quality="standard",
                n=1
            )

            return {
                "success": True,
                "image_url": response.data[0].url,
                "prompt": request.prompt
            }

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported provider: {request.provider}"
            )

    except HTTPException:
        raise
    except Exception as e:
        print(f"Image generation error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Image generation failed: {str(e)}"
        )


if __name__ == "__main__":
    port = int(os.getenv('PORT', 8000))
    # Loopback unless HOST says otherwise: the app is signed-in chat history plus a model
    # that anyone on the network could use. It used to listen on every interface regardless of HOST.
    uvicorn.run(app, host=os.getenv('HOST', '127.0.0.1'), port=port)
