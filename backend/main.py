from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.exception_handlers import RequestValidationError
from fastapi.exceptions import HTTPException
import os
import logging

from .core.config import settings
from .api.endpoints import images, videos, gallery, env

# Configure logging to show DEBUG and INFO logs for troubleshooting
logging.basicConfig(level=logging.DEBUG)
logging.getLogger('azure.core.pipeline.policies.http_logging_policy').setLevel(
    logging.WARNING)

# Create directories if they don't exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.IMAGE_DIR, exist_ok=True)
os.makedirs(settings.VIDEO_DIR, exist_ok=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this with proper origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include routers
app.include_router(
    images.router, prefix=f"{settings.API_V1_STR}/images", tags=["images"])
app.include_router(
    videos.router, prefix=f"{settings.API_V1_STR}/videos", tags=["videos"])
app.include_router(
    gallery.router, prefix=f"{settings.API_V1_STR}/gallery", tags=["gallery"])
app.include_router(env.router, prefix=f"{settings.API_V1_STR}", tags=["env"])
# app.include_router(organizer.router, prefix=f"{settings.API_V1_STR}/organizer", tags=["organizer"])
# app.include_router(sora.router, prefix=f"{settings.API_V1_STR}/sora", tags=["sora"])


@app.get("/")
def read_root():
    return {"message": "Welcome to AI Content Lab API"}


@app.get(f"{settings.API_V1_STR}/health")
def health_check():
    return {"status": "ok"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error.",
            "error": str(exc),
        },
    )


# This allows the file to be run directly with `python backend/main.py`
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
