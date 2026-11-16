"""Upload documents, watch their progress, delete or re-read them"""
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.api.deps import get_owner
from src.core.auth import current_caller
from src.core.config import get_settings
from src.core.database import get_db
from src.models.graph import Document, DocumentStatus
from src.models.job import ACTIVE, Job
from src.services import job_queue, pipeline
from src.services.readers import ReadError, clean_text, read_bytes

router = APIRouter(prefix="/api/documents", tags=["documents"])


def job_to_dict(j: Job | None, positions: dict | None = None) -> dict | None:
    if j is None:
        return None
    return {"id": j.id, "status": j.status, "attempts": j.attempts, "max_attempts": j.max_attempts, "error": j.error,
            "cancel_requested": bool(j.cancel_requested), "position": (positions or {}).get(j.id),
            "created_at": j.created_at.isoformat() if j.created_at else None,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None}


def latest_job(db: Session, document_id: str) -> Job | None:
    return db.execute(select(Job).where(Job.document_id == document_id).order_by(Job.created_at.desc())).scalars().first()


def document_to_dict(d: Document, job: Job | None = None, positions: dict | None = None) -> dict:
    return {
        "id": d.id, "title": d.title, "filename": d.filename, "status": d.status.value, "error": d.error,
        "char_count": d.char_count, "chunk_count": d.chunk_count, "chunks_done": d.chunks_done,
        "progress": round(d.chunks_done / d.chunk_count, 3) if d.chunk_count else (1.0 if d.status == DocumentStatus.COMPLETED else 0.0),
        "stats": d.stats or {}, "model": d.model,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "finished_at": d.finished_at.isoformat() if d.finished_at else None,
        "job": job_to_dict(job, positions),
    }


class TextIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    text: str = Field(min_length=1)


def _create(db: Session, bg: BackgroundTasks, title: str, filename: str | None, text: str, owner: int | None) -> dict:
    settings = get_settings()
    caller = current_caller()
    if caller is not None and caller.is_guest:
        have = db.scalar(select(func.count()).select_from(Document).where(Document.owner_id == owner)) or 0
        if have >= settings.guest_max_documents:
            raise HTTPException(403, f"A guest can add {settings.guest_max_documents} documents. Create an account to add more")
    text = clean_text(text)
    if len(text) < 20:
        raise HTTPException(422, "The text is too short to contain facts (at least 20 characters)")
    if len(text) > settings.max_document_chars:
        raise HTTPException(413, f"The text has {len(text):,} characters; the limit is {settings.max_document_chars:,}")
    doc = Document(owner_id=owner, title=title.strip()[:300], filename=filename, text=text, char_count=len(text))
    db.add(doc)
    db.flush()
    try:
        job, _ = job_queue.enqueue(db, doc)
    except job_queue.QueueFull as exc:
        db.rollback()
        raise HTTPException(429, str(exc))
    db.commit()
    out = document_to_dict(doc, job, job_queue.queue_positions(db))
    job_queue.notify()
    return out


@router.post("", status_code=202)
async def upload_document(bg: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    settings = get_settings()
    data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"The file is larger than {settings.max_upload_mb} MB")
    try:
        text = read_bytes(file.filename or "", data)
    except ReadError as exc:
        raise HTTPException(422, str(exc))
    return _create(db, bg, (file.filename or "Untitled").rsplit(".", 1)[0], file.filename, text, owner)


@router.post("/text", status_code=202)
def add_text(body: TextIn, bg: BackgroundTasks, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    return _create(db, bg, body.title, None, body.text, owner)


@router.get("")
def list_documents(db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    rows = db.execute(select(Document).where(Document.owner_id == owner).order_by(Document.created_at.desc())).scalars().all()
    positions = job_queue.queue_positions(db)
    return {"documents": [document_to_dict(d, latest_job(db, d.id), positions) for d in rows]}


def _get(db: Session, document_id: str, owner: int | None) -> Document:
    doc = db.get(Document, document_id)
    if doc is None or doc.owner_id != owner:  # someone else's document answers exactly like one that does not exist
        raise HTTPException(404, "Document not found")
    return doc


@router.get("/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    doc = _get(db, document_id, owner)
    return document_to_dict(doc, latest_job(db, doc.id), job_queue.queue_positions(db))


@router.post("/{document_id}/reprocess", status_code=202)
def reprocess(document_id: str, bg: BackgroundTasks, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    doc = _get(db, document_id, owner)
    if doc.status in (DocumentStatus.PROCESSING, DocumentStatus.PENDING) or db.execute(
            select(Job.id).where(Job.document_id == doc.id, Job.status.in_(ACTIVE))).first():
        raise HTTPException(409, "The document is already waiting to be read or being read")
    try:
        job, _ = job_queue.enqueue(db, doc)
    except job_queue.QueueFull as exc:
        db.rollback()
        raise HTTPException(429, str(exc))
    db.commit()
    out = document_to_dict(doc, job, job_queue.queue_positions(db))
    job_queue.notify()
    return out


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: str, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    doc = _get(db, document_id, owner)
    if doc.status in (DocumentStatus.PROCESSING, DocumentStatus.PENDING) or db.execute(
            select(Job.id).where(Job.document_id == doc.id, Job.status.in_(ACTIVE))).first():
        raise HTTPException(409, "The document is waiting or being read. Cancel it (or wait until it finishes), then delete it")
    pipeline.delete_document(db, doc)
    db.commit()
