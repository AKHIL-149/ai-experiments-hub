"""Chat Application FastAPI Server"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Cookie, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from pydantic import BaseModel
from typing import Optional, List, Dict
import uvicorn
import os
from pathlib import Path
from dotenv import load_dotenv

from src.core.database import DatabaseManager, User, Conversation, Message
from src.core.auth_manager import AuthManager
from src.core.llm_client import LLMClient

# Load environment
load_dotenv()

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

# LLM Client
llm_client = LLMClient()

# Templates and static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# WebSocket connection registry
active_connections: Dict[str, List[WebSocket]] = {}


# Pydantic models
class RegisterRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class ConversationCreate(BaseModel):
    title: Optional[str] = None
    llm_provider: Optional[str] = 'ollama'
    llm_model: Optional[str] = None
    system_prompt: Optional[str] = None


class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    system_prompt: Optional[str] = None


class MessageCreate(BaseModel):
    content: str


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


# Authentication endpoints

@app.post("/api/auth/register")
async def register(data: RegisterRequest, response: Response):
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
async def login(data: LoginRequest, response: Response):
    """Login user"""
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db)
        user = auth_manager.authenticate(data.username, data.password)

        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

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
    limit: int = 50,
    offset: int = 0,
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
    limit: int = 100,
    offset: int = 0,
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

@app.websocket("/ws/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    conversation_id: str,
    session_token: Optional[str] = Cookie(None)
):
    """WebSocket for real-time chat streaming"""
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

    await websocket.accept()

    # Register connection
    if conversation_id not in active_connections:
        active_connections[conversation_id] = []
    active_connections[conversation_id].append(websocket)

    try:
        while True:
            # Receive user message
            data = await websocket.receive_json()

            if data.get('type') != 'message':
                continue

            user_content = data.get('content', '')

            # Save user message
            with db_manager.get_session() as db:
                user_message = Message(
                    conversation_id=conversation_id,
                    role='user',
                    content=user_content
                )
                db.add(user_message)
                db.commit()
                db.refresh(user_message)

                # Get conversation history
                conversation = db.query(Conversation).filter(
                    Conversation.id == conversation_id
                ).first()

                messages = []
                if conversation.system_prompt:
                    messages.append({'role': 'system', 'content': conversation.system_prompt})

                for msg in conversation.messages[-20:]:  # Last 20 messages
                    messages.append({'role': msg.role, 'content': msg.content})

                provider = conversation.llm_provider
                model = conversation.llm_model

            # Stream LLM response
            assistant_content = ""
            assistant_message_id = None

            try:
                async for token in llm_client.stream_completion(messages, provider, model):
                    assistant_content += token

                    # Send token to client
                    await websocket.send_json({
                        'type': 'token',
                        'token': token
                    })

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

                    if not conversation.title:
                        conversation.title = user_content[:50] + ('...' if len(user_content) > 50 else '')

                    db.commit()
                    db.refresh(assistant_message)
                    assistant_message_id = assistant_message.id

                # Send completion
                await websocket.send_json({
                    'type': 'done',
                    'message_id': assistant_message_id
                })

            except Exception as e:
                await websocket.send_json({
                    'type': 'error',
                    'error': str(e)
                })

    except WebSocketDisconnect:
        active_connections[conversation_id].remove(websocket)
        if not active_connections[conversation_id]:
            del active_connections[conversation_id]


# Image Generation Endpoint
class ImageGenerationRequest(BaseModel):
    prompt: str
    provider: str = 'stable-diffusion'
    width: Optional[int] = 512
    height: Optional[int] = 512


@app.post("/api/generate-image")
async def generate_image(
    request: ImageGenerationRequest,
    session_token: Optional[str] = Cookie(None)
):
    """
    Generate image using local Stable Diffusion or cloud providers

    Supported providers:
    - stable-diffusion (local - requires Stable Diffusion WebUI or ComfyUI)
    - dall-e (OpenAI DALL-E)
    - midjourney (via API)
    """
    with db_manager.get_session() as db:
        auth_manager = AuthManager(db)
        user = auth_manager.validate_session(session_token)

        if not user:
            raise HTTPException(status_code=401, detail="Not authenticated")

        try:
            # Check provider
            if request.provider == 'stable-diffusion':
                # Use local Stable Diffusion (diffusers library)
                try:
                    from src.local_sd_service import get_service
                    import uuid
                    from pathlib import Path

                    # Get or create the SD service
                    sd_service = get_service()

                    # Generate image
                    image = sd_service.generate_image(
                        prompt=request.prompt,
                        width=request.width,
                        height=request.height,
                        steps=20
                    )

                    # Save image to static directory
                    image_id = str(uuid.uuid4())
                    images_dir = Path("static/generated_images")
                    images_dir.mkdir(exist_ok=True)

                    image_path = images_dir / f"{image_id}.png"
                    image.save(image_path, format='PNG')

                    return {
                        "success": True,
                        "image_url": f"/static/generated_images/{image_id}.png",
                        "prompt": request.prompt,
                        "provider": "local-stable-diffusion"
                    }

                except ImportError as e:
                    raise HTTPException(
                        status_code=503,
                        detail="Stable Diffusion dependencies not installed. Run: pip install diffusers transformers accelerate"
                    )
                except Exception as e:
                    print(f"Local SD error: {str(e)}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Image generation failed: {str(e)}"
                    )

            elif request.provider == 'dall-e':
                # Use OpenAI DALL-E
                if not os.getenv('OPENAI_API_KEY'):
                    raise HTTPException(
                        status_code=400,
                        detail="OpenAI API key not configured"
                    )

                from openai import OpenAI
                client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

                response = client.images.generate(
                    model="dall-e-3",
                    prompt=request.prompt,
                    size=f"{request.width}x{request.height}",
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
    uvicorn.run(app, host="0.0.0.0", port=port)
