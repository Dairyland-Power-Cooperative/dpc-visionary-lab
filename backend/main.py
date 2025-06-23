from fastapi import FastAPI, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from fastapi.exception_handlers import RequestValidationError
from fastapi.exceptions import HTTPException
import os
import logging
import traceback
import uuid
import platform
import socket
import sys
import time
import json
from typing import Dict, Any, List, Optional

from .core.config import settings
from .api.endpoints import images, videos, gallery, env
from .core.logging_config import setup_logging, RequestLoggingMiddleware, get_logger
from .core.logging_config import log_environment_variables, log_file_permissions
from .core.azure_logger import setup_azure_monitoring, azure_tracer, azure_monitor

# Set up structured logging
logger = setup_logging()
# Create a module-specific logger
app_logger = get_logger("app.main")

# Log startup information with detailed environment info
app_logger.info(f"Starting {settings.PROJECT_NAME} in {settings.ENVIRONMENT} environment", 
    extra={
        "environment": settings.ENVIRONMENT,
        "python_version": platform.python_version(),
        "system": platform.system(),
        "processor": platform.processor(),
        "hostname": socket.gethostname(),
        "log_level": settings.LOG_LEVEL,
        "is_azure_environment": os.environ.get("WEBSITE_SITE_NAME") is not None,
        "container_app_name": os.environ.get("CONTAINER_APP_NAME", "unknown"),
        "container_app_revision": os.environ.get("CONTAINER_APP_REVISION", "unknown"),
        "container_name": os.environ.get("CONTAINER_NAME", "unknown"),
    }
)

# Create directories if they don't exist and log their creation status
for directory in [settings.UPLOAD_DIR, settings.IMAGE_DIR, settings.VIDEO_DIR]:
    try:
        os.makedirs(directory, exist_ok=True)
        app_logger.info(f"Directory created or verified: {directory}")
    except Exception as e:
        app_logger.error(f"Failed to create directory {directory}: {str(e)}", exc_info=True)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Add request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Set up CORS with detailed origins logging
origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app_logger.info(f"Setting up CORS with origins: {origins}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up Azure Application Insights monitoring if enabled
if settings.ENABLE_AZURE_MONITOR:
    try:
        azure_monitoring_enabled = setup_azure_monitoring(app)
        app_logger.info(f"Azure monitoring setup {'successful' if azure_monitoring_enabled else 'skipped'}")
    except Exception as e:
        app_logger.error(f"Failed to set up Azure monitoring: {str(e)}", exc_info=True)

# Mount static files with explicit error handling
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
    app_logger.info("Static files mounted at /static")
except Exception as e:
    app_logger.error(f"Failed to mount static files: {str(e)}", exc_info=True)

# Include routers
app.include_router(
    images.router, prefix=f"{settings.API_V1_STR}/images", tags=["images"])
app.include_router(
    videos.router, prefix=f"{settings.API_V1_STR}/videos", tags=["videos"])
app.include_router(
    gallery.router, prefix=f"{settings.API_V1_STR}/gallery", tags=["gallery"])
app.include_router(env.router, prefix=f"{settings.API_V1_STR}", tags=["env"])

# Log which routers were included
app_logger.info("API routers included", extra={
    "routers": ["images", "videos", "gallery", "env"]
})


@app.get("/")
def read_root():
    return {"message": "Welcome to AI Content Lab API"}


@app.get(f"{settings.API_V1_STR}/health")
async def health_check():
    """Enhanced health check endpoint with detailed system information"""
    # Track health check call
    if settings.ENABLE_AZURE_MONITOR:
        azure_tracer.track_event("api.health_check")
        
    # Basic status
    health_data = {
        "status": "ok",
        "timestamp": time.time(),
        "environment": settings.ENVIRONMENT,
        "hostname": socket.gethostname(),
    }
    
    # Add Azure-specific information if we're running in Azure
    if os.environ.get("WEBSITE_SITE_NAME") or os.environ.get("CONTAINER_APP_NAME"):
        health_data["azure"] = {
            "container_app": os.environ.get("CONTAINER_APP_NAME", "unknown"),
            "container_app_revision": os.environ.get("CONTAINER_APP_REVISION", "unknown"),
            "container_name": os.environ.get("CONTAINER_NAME", "unknown"),
            "website_name": os.environ.get("WEBSITE_SITE_NAME", "unknown"),
            "website_instance_id": os.environ.get("WEBSITE_INSTANCE_ID", "unknown"),
        }
    
    # Add directory existence and permissions checks
    health_data["directories"] = {}
    for directory in [settings.UPLOAD_DIR, settings.IMAGE_DIR, settings.VIDEO_DIR]:
        health_data["directories"][directory] = {
            "exists": os.path.exists(directory),
            "is_directory": os.path.isdir(directory) if os.path.exists(directory) else False,
            "is_writable": os.access(directory, os.W_OK) if os.path.exists(directory) else False,
        }
    
    # Add Python environment info
    health_data["python"] = {
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "path": sys.executable,
    }
    
    return health_data


@app.get(f"{settings.API_V1_STR}/diagnostics")
async def diagnostics():
    """Comprehensive diagnostics endpoint for troubleshooting"""
    # Check if we should enable detailed diagnostics
    if settings.ENVIRONMENT.lower() == "production" and not os.environ.get("ENABLE_DIAGNOSTICS", "").lower() == "true":
        return {"message": "Diagnostics endpoint is disabled in production. Set ENABLE_DIAGNOSTICS=true to enable."}
    
    # Log that diagnostics was called
    app_logger.info("Diagnostics endpoint called")
    
    # Run diagnostics
    diagnostics_data = {
        "status": "ok",
        "timestamp": time.time(),
        "environment": settings.ENVIRONMENT,
        "hostname": socket.gethostname(),
    }
    
    # Test directory access
    diagnostics_data["directories"] = {}
    for directory in [settings.UPLOAD_DIR, settings.IMAGE_DIR, settings.VIDEO_DIR]:
        try:
            test_file = os.path.join(directory, f"test_write_{uuid.uuid4()}.txt")
            with open(test_file, "w") as f:
                f.write("Test write access")
            os.remove(test_file)
            write_test = True
        except Exception as e:
            write_test = False
            
        diagnostics_data["directories"][directory] = {
            "exists": os.path.exists(directory),
            "is_directory": os.path.isdir(directory) if os.path.exists(directory) else False,
            "is_writable": os.access(directory, os.W_OK) if os.path.exists(directory) else False,
            "write_test": write_test,
            "stats": str(os.stat(directory)) if os.path.exists(directory) else None,
        }
    
    # Collect environment variables (without sensitive data)
    env_vars = {}
    for key, value in os.environ.items():
        if any(key.upper().startswith(prefix) for prefix in ["PATH", "PYTHON", "WEBSITE_", "CONTAINER_", "HOME"]):
            env_vars[key] = value
        elif "SECRET" in key.upper() or "KEY" in key.upper() or "PASSWORD" in key.upper() or "CONNECTION" in key.upper():
            env_vars[key] = "[REDACTED]"
    
    diagnostics_data["environment_variables"] = env_vars
    
    # Log diagnostics results
    app_logger.info("Diagnostics results", extra={"diagnostics": diagnostics_data})
    
    return diagnostics_data


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle validation errors with detailed error tracking"""
    error_id = str(uuid.uuid4())
    
    # Log the validation error with request details
    app_logger.warning(
        f"Validation error",
        extra={
            "error_id": error_id,
            "path": request.url.path,
            "method": request.method,
            "client_host": request.client.host if request.client else None,
            "headers": {k: v for k, v in request.headers.items() if k.lower() not in settings.SENSITIVE_HEADERS},
            "errors": exc.errors(),
        }
    )
    
    # Track in Azure if enabled
    if settings.ENABLE_AZURE_MONITOR:
        azure_tracer.track_event("api.validation_error", {
            "path": request.url.path,
            "method": request.method,
            "error_id": error_id
        })
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "errors": exc.errors(),
            "error_id": error_id,
        },
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with enhanced error tracking"""
    error_id = str(uuid.uuid4())
    
    # Log the HTTP exception with request details
    app_logger.warning(
        f"HTTP error: {exc.detail}",
        extra={
            "error_id": error_id,
            "path": request.url.path,
            "method": request.method,
            "client_host": request.client.host if request.client else None,
            "status_code": exc.status_code,
            "headers": {k: v for k, v in request.headers.items() if k.lower() not in settings.SENSITIVE_HEADERS},
        }
    )
    
    # Track in Azure if enabled
    if settings.ENABLE_AZURE_MONITOR:
        azure_tracer.track_event("api.http_exception", {
            "path": request.url.path,
            "method": request.method,
            "status_code": exc.status_code,
            "error_id": error_id
        })
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "detail": exc.detail,
            "status_code": exc.status_code,
            "error_id": error_id,
        },
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all other exceptions with comprehensive error tracking"""
    error_id = str(uuid.uuid4())
    error_details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    
    # Log the unhandled exception with detailed information
    app_logger.error(
        f"Unhandled exception",
        extra={
            "error_id": error_id,
            "path": request.url.path,
            "method": request.method,
            "client_host": request.client.host if request.client else None,
            "error": str(exc),
            "error_type": type(exc).__name__,
            "error_details": error_details,
            "headers": {k: v for k, v in request.headers.items() if k.lower() not in settings.SENSITIVE_HEADERS},
        }
    )
    
    # Track in Azure if enabled
    if settings.ENABLE_AZURE_MONITOR:
        azure_tracer.track_event("api.unhandled_exception", {
            "path": request.url.path,
            "method": request.method,
            "error_id": error_id,
            "error_type": type(exc).__name__
        })
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error_message": str(exc),
            "error_id": error_id,
        },
    )

@app.on_event("startup")
async def startup_event():
    """Run startup diagnostics and log environment information"""
    app_logger.info("Application startup triggered")
    
    # Log environment variables (safe ones only by default)
    log_environment_variables(include_secrets=False)
    
    # Log file permissions for critical directories
    log_file_permissions()
    
    # Check for Azure environment
    if os.environ.get("WEBSITE_SITE_NAME") or os.environ.get("CONTAINER_APP_NAME"):
        app_logger.info("Running in Azure environment", extra={
            "container_app": os.environ.get("CONTAINER_APP_NAME", "unknown"),
            "container_app_revision": os.environ.get("CONTAINER_APP_REVISION", "unknown"),
            "container_name": os.environ.get("CONTAINER_NAME", "unknown"),
            "website_name": os.environ.get("WEBSITE_SITE_NAME", "unknown"),
            "website_instance_id": os.environ.get("WEBSITE_INSTANCE_ID", "unknown"),
        })
    
    # Check if Azure Storage is configured
    storage_configured = bool(settings.AZURE_STORAGE_CONNECTION_STRING or (
        settings.AZURE_BLOB_SERVICE_URL and settings.AZURE_STORAGE_ACCOUNT_NAME
    ))
    
    app_logger.info("Storage configuration", extra={
        "azure_storage_configured": storage_configured,
        "using_connection_string": bool(settings.AZURE_STORAGE_CONNECTION_STRING),
        "using_service_url": bool(settings.AZURE_BLOB_SERVICE_URL),
        "account_name_provided": bool(settings.AZURE_STORAGE_ACCOUNT_NAME),
        "account_key_provided": bool(settings.AZURE_STORAGE_ACCOUNT_KEY)
    })
    
    # Check OpenAI API configuration
    openai_configured = bool(settings.OPENAI_API_KEY or (
        settings.IMAGEGEN_AOAI_API_KEY and settings.IMAGEGEN_AOAI_RESOURCE
    ))
    
    app_logger.info("AI Service configuration", extra={
        "openai_configured": openai_configured,
        "using_openai_direct": bool(settings.OPENAI_API_KEY),
        "using_azure_openai": bool(settings.IMAGEGEN_AOAI_API_KEY and settings.IMAGEGEN_AOAI_RESOURCE),
        "sora_configured": bool(settings.SORA_AOAI_API_KEY and settings.SORA_AOAI_RESOURCE)
    })

@app.on_event("shutdown")
async def shutdown_event():
    """Log application shutdown"""
    app_logger.info("Application shutdown")

# This allows the file to be run directly with `python backend/main.py`
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
