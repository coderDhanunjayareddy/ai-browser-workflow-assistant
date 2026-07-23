from __future__ import annotations

from datetime import datetime

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.product import models, security
from app.product.repositories import ProductRepository


class ProductPrincipal:
    def __init__(self, user: models.V5User, session: models.V5Session):
        self.user = user
        self.session = session


def current_principal(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ProductPrincipal:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    payload = security.decode_token(token)
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid token")
    repo = ProductRepository(db)
    session = repo.get_session_by_hash(security.token_hash(token))
    if not session or session.revoked or session.expires_at < datetime.utcnow() or session.id != payload.get("sid"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired")
    user = repo.get_user(str(payload.get("sub") or ""))
    if not user or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user unavailable")
    session.last_seen_at = datetime.utcnow()
    db.flush()
    return ProductPrincipal(user, session)
