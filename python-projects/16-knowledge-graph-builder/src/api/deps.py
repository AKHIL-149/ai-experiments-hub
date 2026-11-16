"""Who is asking, as an endpoint dependency. Every endpoint that touches a person's data takes `owner`."""
from fastapi import HTTPException

from src.core.auth import current_caller


async def get_owner() -> int | None:
    """The account id of the caller (None in single-user mode). 401 when there is no caller at all (fails closed)."""
    caller = current_caller()
    if caller is None:
        raise HTTPException(401, detail="Not signed in")
    return caller.user_id
