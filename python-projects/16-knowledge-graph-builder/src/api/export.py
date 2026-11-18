"""Download the graph as JSON, CSV (a zip of three tables) or Cypher, and say first what a download would contain"""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from src.api.deps import get_owner
from src.core.database import get_db
from src.models.graph import Document
from src.services import export as ex

router = APIRouter(prefix="/api/export", tags=["export"])


def _dataset(db: Session, owner: int | None, document_id: str | None, sources: bool) -> ex.Dataset:
    if document_id:
        doc = db.get(Document, document_id)
        if doc is None or doc.owner_id != owner:
            raise HTTPException(404, "Document not found")
    return ex.collect(db, owner, document_id=document_id, with_sources=sources)


@router.get("/summary")
def summary(document_id: str | None = None, db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    """What a download would contain: entity, fact and quote counts, and how many facts are left out by settled conflicts"""
    ds = _dataset(db, owner, document_id, True)
    return {**ds.counts(), "document": ds.document}


@router.get("")
def download(format: str = Query("json"), document_id: str | None = None, sources: bool = True, schema: bool = True,
             db: Session = Depends(get_db), owner: int | None = Depends(get_owner)):
    """?format=json|cypher|csv. `sources=false` leaves the quotes out; `schema=false` leaves the constraint statements out of the
    Cypher script. With `document_id`, only the facts read from that document."""
    if format not in ex.FORMATS:
        raise HTTPException(422, f"Unknown format. Use one of: {', '.join(ex.FORMATS)}")
    ds = _dataset(db, owner, document_id, sources)
    media, _ = ex.MEDIA[format]
    name = ex.file_name(format, ds.document["title"] if ds.document else None)
    return Response(ex.render(ds, format, schema=schema), media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})
