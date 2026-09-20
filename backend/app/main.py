from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, documents
from app.core.config import settings
from app.db.base import Base
from app.db.migrate import add_missing_columns
from app.db.session import engine
from app.models import *  # noqa: F401,F403  (registers all models on Base before create_all)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    add_missing_columns(engine, Base.metadata)
    yield


app = FastAPI(title="LegalLens API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(documents.router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
