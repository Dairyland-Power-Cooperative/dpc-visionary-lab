import logging
import json
import sys
import os
from datetime import datetime
from pythonjsonlogger import jsonlogger
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import time
import uuid
from contextvars import ContextVar
import traceback
import socket
import platform

from backend.core.config import settings

# Create a context variable to store request ID
request_id_var = ContextVar("request_id", default=None)
correlation_id_var = ContextVar("correlation_id", default=None)
user_id_var = ContextVar("user_id", default=None)
session_id_var = ContextVar("session_id", default=None)

# Custom JSON formatter for structured logging
class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        
        # Add timestamp in ISO format
        log_record['timestamp'] = datetime.utcnow().isoformat() + 'Z'
        log_record['level'] = record.levelname
        log_record['logger'] = record.name
        
        # Add process and thread information
        log_record['process_id'] = os.getpid()
        log_record['thread_id'] = record.thread
        log_record['thread_name'] = record.threadName
        
        # Add host information
        log_record['hostname'] = socket.gethostname()
        try:
            log_record['host_ip'] = socket.gethostbyname(socket.gethostname())
        except:
            log_record['host_ip'] = '127.0.0.1'
        
        # Add context variables if available
        request_id = request_id_var.get()
        if request_id:
            log_record['request_id'] = request_id
            
        correlation_id = correlation_id_var.get()
        if correlation_id:
            log_record['correlation_id'] = correlation_id
        
        user_id = user_id_var.get()
        if user_id:
            log_record['user_id'] = user_id
            
        session_id = session_id_var.get()
        if session_id:
            log_record['session_id'] = session_id
        
        # Add application metadata
        log_record['app_version'] = os.environ.get('APP_VERSION', 'unknown')
        log_record['environment'] = settings.ENVIRONMENT
        log_record['python_version'] = platform.python_version()
        
        # Add exception info if present
        if record.exc_info:
            exc_info = record.exc_info
            log_record['exception'] = {
                'type': exc_info[0].__name__,
                'message': str(exc_info[1]),
                'traceback': ''.join(traceback.format_exception(*exc_info))
            }

# Request logging middleware with enhanced details
class RequestLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.logger = logging.getLogger("api.request")
    
    async def dispatch(self, request: Request, call_next):
        # Generate unique request ID
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request_id_var.set(req_id)
        
        # Get correlation ID from header or generate one
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        correlation_id_var.set(correlation_id)
        
        # Extract user ID from request if available (adapt as needed for your auth system)
        try:
            auth_header = request.headers.get("Authorization")
            # You would extract the user ID based on your auth mechanism
            # This is just a placeholder
            if auth_header:
                user_id_var.set("extracted-user-id")
        except Exception as e:
            self.logger.debug(f"Failed to extract user ID: {str(e)}")
        
        start_time = time.time()
        
        # Build request details with enhanced debugging info
        request_details = {
            "method": request.method,
            "url": str(request.url),
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("User-Agent"),
            "request_id": req_id,
            "correlation_id": correlation_id,
            "content_length": request.headers.get("Content-Length"),
            "content_type": request.headers.get("Content-Type"),
            "path_params": dict(request.path_params) if request.path_params else {},
            "query_params": dict(request.query_params) if request.query_params else {},
            "headers": {k: v for k, v in request.headers.items() if k.lower() not in [h.lower() for h in settings.SENSITIVE_HEADERS]},
            "azure_deployment": {
                "slot": os.environ.get("WEBSITE_SLOT_NAME", "unknown"),
                "instance_id": os.environ.get("WEBSITE_INSTANCE_ID", "unknown"),
                "container_app": os.environ.get("CONTAINER_APP_NAME", "unknown"),
                "container_app_revision": os.environ.get("CONTAINER_APP_REVISION", "unknown"),
                "container_name": os.environ.get("CONTAINER_NAME", "unknown")
            }
        }
        
        # Log request details
        self.logger.info(f"Request started", extra=request_details)
        
        try:
            # Handle request body for debugging if needed
            if settings.ENVIRONMENT.lower() in ["development", "staging"] and settings.LOG_LEVEL.upper() == "DEBUG":
                try:
                    body = await request.body()
                    if body:
                        # Clone the request to avoid consuming the body
                        # This is needed because once the body is read, it can't be read again
                        request._body = body
                        content_type = request.headers.get("Content-Type", "")
                        
                        if "application/json" in content_type and len(body) < 10000:  # Limit size to avoid huge logs
                            try:
                                body_json = json.loads(body)
                                self.logger.debug("Request body", extra={"body": body_json})
                            except json.JSONDecodeError:
                                self.logger.debug("Request body (not valid JSON)", extra={"body": body.decode("utf-8", errors="replace")})
                except Exception as e:
                    self.logger.debug(f"Failed to log request body: {str(e)}")
            
            response = await call_next(request)
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = req_id
            response.headers["X-Correlation-ID"] = correlation_id
            
            # Calculate duration
            process_time = time.time() - start_time
            
            # Build response details
            response_details = {
                "method": request.method,
                "url": str(request.url),
                "status_code": response.status_code,
                "duration_ms": round(process_time * 1000, 2),
                "request_id": req_id,
                "correlation_id": correlation_id,
                "content_length": response.headers.get("Content-Length"),
                "content_type": response.headers.get("Content-Type"),
                "headers": {k: v for k, v in response.headers.items() if k.lower() not in [h.lower() for h in settings.SENSITIVE_HEADERS]}
            }
            
            # Log response details
            self.logger.info(f"Request completed", extra=response_details)
            
            # Optionally log response body for debugging
            if settings.ENVIRONMENT.lower() in ["development", "staging"] and settings.LOG_LEVEL.upper() == "DEBUG" and settings.ENABLE_RESPONSE_LOGGING:
                try:
                    content_type = response.headers.get("Content-Type", "")
                    if "application/json" in content_type:
                        response_body = b""
                        async for chunk in response.body_iterator:
                            response_body += chunk
                        
                        # Reconstruct the response
                        response = Response(
                            content=response_body,
                            status_code=response.status_code,
                            headers=dict(response.headers),
                            media_type=response.media_type
                        )
                        
                        try:
                            body_json = json.loads(response_body)
                            self.logger.debug("Response body", extra={"body": body_json})
                        except json.JSONDecodeError:
                            self.logger.debug("Response body (not valid JSON)", extra={"body": response_body.decode("utf-8", errors="replace")})
                except Exception as e:
                    self.logger.debug(f"Failed to log response body: {str(e)}")
            
            return response
            
        except Exception as e:
            # Log exception details with enhanced error tracking
            error_details = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            self.logger.error(
                f"Request failed: {str(e)}",
                extra={
                    "method": request.method,
                    "url": str(request.url),
                    "exception": str(e),
                    "exception_type": type(e).__name__,
                    "exception_traceback": error_details,
                    "duration_ms": round((time.time() - start_time) * 1000, 2),
                    "request_id": req_id,
                    "correlation_id": correlation_id,
                    "azure_deployment": {
                        "slot": os.environ.get("WEBSITE_SLOT_NAME", "unknown"),
                        "instance_id": os.environ.get("WEBSITE_INSTANCE_ID", "unknown"),
                        "container_app": os.environ.get("CONTAINER_APP_NAME", "unknown"),
                        "container_app_revision": os.environ.get("CONTAINER_APP_REVISION", "unknown"),
                        "container_name": os.environ.get("CONTAINER_NAME", "unknown")
                    }
                },
                exc_info=True
            )
            raise

class AzureLogHandler(logging.StreamHandler):
    """Custom log handler optimized for Azure App Insights and Log Analytics"""
    def __init__(self):
        super().__init__(stream=sys.stdout)  # App Insights collects stdout
        
        # Add filtering or special handling for Azure logs if needed
        self.addFilter(self.azure_log_filter)
    
    def azure_log_filter(self, record):
        """Add any special filtering logic for Azure logs"""
        # Add Azure-specific context if available
        if not hasattr(record, 'azure_deployment'):
            record.azure_deployment = {
                "slot": os.environ.get("WEBSITE_SLOT_NAME", "unknown"),
                "instance_id": os.environ.get("WEBSITE_INSTANCE_ID", "unknown"),
                "container_app": os.environ.get("CONTAINER_APP_NAME", "unknown"),
                "container_app_revision": os.environ.get("CONTAINER_APP_REVISION", "unknown"),
                "container_name": os.environ.get("CONTAINER_NAME", "unknown")
            }
        return True

class FileLogHandler(logging.FileHandler):
    """Log handler for file-based logging"""
    def __init__(self, filename):
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        super().__init__(filename, encoding='utf-8')

def setup_logging():
    """Configure logging for the application with enhanced Azure support"""
    # Clear any existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Set the root logger level based on settings
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root_logger.setLevel(log_level)
    
    # Create JSON formatter for structured logging
    formatter = CustomJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s')
    
    # Create Azure-optimized log handler
    azure_handler = AzureLogHandler()
    azure_handler.setFormatter(formatter)
    
    # Add handler to root logger
    root_logger.addHandler(azure_handler)
    
    # Add file logging if enabled
    if settings.LOG_TO_FILE:
        try:
            file_handler = FileLogHandler(settings.LOG_FILE_PATH)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            print(f"Failed to set up file logging: {str(e)}")
    
    # Configure libraries logging levels
    # Set third-party libraries to higher log levels to reduce noise
    logging.getLogger("azure").setLevel(logging.WARNING)
    logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    # Special case: set Azure Storage logging to DEBUG when troubleshooting storage issues
    if os.environ.get("DEBUG_AZURE_STORAGE", "").lower() == "true":
        logging.getLogger("azure.storage").setLevel(logging.DEBUG)
    
    # Set specific loggers to DEBUG in development or when troubleshooting
    if settings.ENVIRONMENT.lower() in ["development", "local"] or os.environ.get("DEBUG_BACKEND", "").lower() == "true":
        logging.getLogger("backend").setLevel(logging.DEBUG)
        # Enable SQL query logging if needed
        # logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)
    
    # Create module specific loggers with appropriate levels
    api_logger = logging.getLogger("api")
    api_logger.setLevel(log_level)
    
    core_logger = logging.getLogger("core")
    core_logger.setLevel(log_level)
    
    # Log initial setup information
    startup_logger = logging.getLogger("app.startup")
    startup_logger.info(
        "Logging system initialized",
        extra={
            "log_level": settings.LOG_LEVEL,
            "environment": settings.ENVIRONMENT,
            "file_logging": settings.LOG_TO_FILE,
            "file_path": settings.LOG_FILE_PATH if settings.LOG_TO_FILE else None,
            "azure_monitor_enabled": settings.ENABLE_AZURE_MONITOR,
            "python_version": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
            "azure_environment": {
                "is_azure": os.environ.get("WEBSITE_SITE_NAME") is not None,
                "container_app": os.environ.get("CONTAINER_APP_NAME", "unknown"),
                "container_app_revision": os.environ.get("CONTAINER_APP_REVISION", "unknown")
            }
        }
    )
    
    # Return the logger for convenience
    return root_logger

def get_logger(name):
    """Get a logger with the specified name"""
    return logging.getLogger(name)

def log_environment_variables(include_secrets=False):
    """Log all environment variables to help with debugging deployment issues"""
    env_logger = get_logger("app.environment")
    
    # Always safe variables to log
    safe_prefixes = [
        "PATH", "PYTHON", "WEBSITE_", "CONTAINER_APP_", "CONTAINER_NAME",
        "HOSTNAME", "HOME", "PORT", "WEBSITES_PORT", "BACKEND_", "FRONTEND_"
    ]
    
    # Variables that might contain sensitive information
    sensitive_prefixes = [
        "TOKEN", "KEY", "SECRET", "PASSWORD", "CONN", "CONNECTION", "AUTH", "AZURE_STORAGE"
    ]
    
    # Get all environment variables
    all_vars = {}
    for key, value in os.environ.items():
        # Check if we should include this variable
        is_safe = any(key.startswith(prefix) for prefix in safe_prefixes)
        is_sensitive = any(sensitive in key.upper() for sensitive in sensitive_prefixes)
        
        if is_safe or (include_secrets and not is_sensitive) or include_secrets:
            if is_sensitive and not include_secrets:
                all_vars[key] = "[REDACTED]"
            else:
                all_vars[key] = value
    
    # Log the environment variables
    env_logger.info(
        "Environment variables",
        extra={
            "environment_variables": all_vars,
            "include_secrets": include_secrets
        }
    )

def log_file_permissions():
    """Log file permissions for critical directories to debug file access issues"""
    fs_logger = get_logger("app.filesystem")
    
    critical_dirs = [
        settings.UPLOAD_DIR,
        settings.IMAGE_DIR,
        settings.VIDEO_DIR
    ]
    
    for directory in critical_dirs:
        try:
            if os.path.exists(directory):
                stats = os.stat(directory)
                fs_logger.info(
                    f"Directory permissions: {directory}",
                    extra={
                        "path": directory,
                        "exists": True,
                        "mode": oct(stats.st_mode),
                        "uid": stats.st_uid,
                        "gid": stats.st_gid,
                        "size": stats.st_size,
                        "is_writable": os.access(directory, os.W_OK),
                        "is_readable": os.access(directory, os.R_OK),
                        "is_executable": os.access(directory, os.X_OK)
                    }
                )
            else:
                fs_logger.warning(
                    f"Directory does not exist: {directory}",
                    extra={
                        "path": directory,
                        "exists": False
                    }
                )
        except Exception as e:
            fs_logger.error(
                f"Error checking directory permissions: {directory}",
                extra={
                    "path": directory,
                    "error": str(e)
                },
                exc_info=True
            )
