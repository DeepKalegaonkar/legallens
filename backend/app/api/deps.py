import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.crud.user import get_user_by_email
from app.db.session import get_db
from app.models.user import User
from app.services.nlp.base import ClauseAnalyzer
from app.services.nlp.placeholder import PlaceholderClauseAnalyzer

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _load_clause_analyzer() -> ClauseAnalyzer:
    """Swap point: this is the only place that decides which ClauseAnalyzer runs.

    Prefers the real trained models; falls back to the regex/keyword
    placeholder if the joblib artifacts under app/services/nlp/models/
    haven't been trained yet (see ml_training/README or backend/README.md).
    """
    try:
        from app.services.nlp.trained_model import TrainedClauseAnalyzer

        return TrainedClauseAnalyzer()
    except FileNotFoundError as exc:
        logger.warning("Trained clause/risk models not found (%s); using placeholder analyzer.", exc)
        return PlaceholderClauseAnalyzer()


_clause_analyzer = _load_clause_analyzer()


def get_clause_analyzer() -> ClauseAnalyzer:
    return _clause_analyzer


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    email = decode_access_token(token)
    if email is None:
        raise credentials_error

    user = get_user_by_email(db, email)
    if user is None:
        raise credentials_error

    return user
