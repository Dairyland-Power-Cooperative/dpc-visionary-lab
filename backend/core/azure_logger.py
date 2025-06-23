import logging
import os
from opencensus.ext.azure.log_exporter import AzureLogHandler
from opencensus.trace import config_integration
from opencensus.trace.samplers import ProbabilitySampler
from opencensus.trace.tracer import Tracer
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.ext.fastapi.fastapi_middleware import FastAPIMiddleware
from opencensus.ext.azure import metrics_exporter
from opencensus.stats import stats as stats_module
from opencensus.stats import aggregation as aggregation_module
from opencensus.stats import measure as measure_module
from opencensus.stats import view as view_module
from opencensus.trace.span import SpanKind
from opencensus.trace.status import Status
from opencensus.trace.attributes_helper import COMMON_ATTRIBUTES
from time import time
from fastapi import FastAPI, Request
import psutil
import platform
import socket
import uuid
from typing import Dict, Any, Optional, Callable, List
import asyncio
import functools

from backend.core.config import settings

# Custom metrics
_REQUEST_LATENCY_MS = measure_module.MeasureFloat("request_latency", 
                                              "The latency of requests in milliseconds", "ms")
_REQUEST_COUNT = measure_module.MeasureInt("request_count", 
                                       "Number of requests", "requests")
_ERROR_COUNT = measure_module.MeasureInt("error_count", 
                                     "Number of errors", "errors")
_API_CALLS = measure_module.MeasureInt("api_calls",
                                   "Number of API calls", "calls")
_IMAGE_GENERATION_LATENCY = measure_module.MeasureFloat("image_generation_latency",
                                                   "Image generation latency in milliseconds", "ms")
_VIDEO_GENERATION_LATENCY = measure_module.MeasureFloat("video_generation_latency",
                                                    "Video generation latency in milliseconds", "ms")
_MEMORY_USAGE = measure_module.MeasureFloat("memory_usage",
                                       "Memory usage in MB", "MB")
_CPU_USAGE = measure_module.MeasureFloat("cpu_usage",
                                     "CPU usage percentage", "%")

def setup_azure_monitoring(app: FastAPI):
    """Configure Azure Application Insights integration if enabled"""
    if settings.ENABLE_AZURE_MONITOR and settings.APPLICATION_INSIGHTS_CONNECTION_STRING:
        # Configure trace exporter
        azure_exporter = AzureExporter(
            connection_string=settings.APPLICATION_INSIGHTS_CONNECTION_STRING
        )
        
        # Configure Azure metrics exporter with custom export interval
        metrics_exporter_client = metrics_exporter.new_metrics_exporter(
            connection_string=settings.APPLICATION_INSIGHTS_CONNECTION_STRING,
            export_interval=15.0  # Export metrics every 15 seconds
        )
        
        # Integrate with logging - this will send logs to App Insights
        azure_handler = AzureLogHandler(
            connection_string=settings.APPLICATION_INSIGHTS_CONNECTION_STRING
        )
        
        # Add custom properties to all telemetry data
        azure_handler.add_telemetry_processor(add_custom_properties)
        
        # Add Azure Log Handler to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(azure_handler)
        
        # Configure WSGI/ASGI trace integration
        config_integration.trace_integrations(['logging', 'requests', 'urllib3', 'httpx'])
        
        # Add FastAPI middleware for tracing
        app.add_middleware(
            FastAPIMiddleware,
            exporter=azure_exporter,
            sampler=ProbabilitySampler(1.0)  # Sample 100% of requests
        )
        
        # Create custom metrics
        stats = stats_module.stats
        view_manager = stats.view_manager
        
        # Configure various metrics to track
        register_custom_metrics(view_manager)
        
        # Start system metrics monitoring
        start_system_metrics_collection()
        
        # Add custom middleware to track API health metrics
        @app.middleware("http")
        async def track_request_metrics(request: Request, call_next):
            start_time = time()
            
            # Extract correlation ID
            correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
            
            # Track the start of the request
            azure_tracer.track_event("request_start", {
                "endpoint": request.url.path,
                "method": request.method,
                "correlation_id": correlation_id
            })
            
            try:
                response = await call_next(request)
                
                # Calculate duration
                duration_ms = (time() - start_time) * 1000
                
                # Record metrics
                stats.record([
                    stats_module.stats.stats_recorder.new_measurement(
                        _REQUEST_LATENCY_MS.name, duration_ms),
                    stats_module.stats.stats_recorder.new_measurement(
                        _REQUEST_COUNT.name, 1)
                ], {
                    "path": request.url.path,
                    "method": request.method,
                    "status_code": response.status_code,
                })
                
                # Track specific API endpoints for detailed monitoring
                if "api/v1/images" in request.url.path:
                    stats.record([
                        stats_module.stats.stats_recorder.new_measurement(
                            _API_CALLS.name, 1)
                    ], {
                        "api_category": "images",
                        "path": request.url.path,
                    })
                elif "api/v1/videos" in request.url.path:
                    stats.record([
                        stats_module.stats.stats_recorder.new_measurement(
                            _API_CALLS.name, 1)
                    ], {
                        "api_category": "videos",
                        "path": request.url.path,
                    })
                    
                return response
            
            except Exception as e:
                # Record error metrics
                stats.record([
                    stats_module.stats.stats_recorder.new_measurement(
                        _ERROR_COUNT.name, 1)
                ], {
                    "path": request.url.path,
                    "method": request.method,
                    "error_type": type(e).__name__
                })
                
                # Re-raise the exception
                raise
                
        # Add request tracking method to the app state
        app.state.azure_tracer = azure_tracer
        
        # Log successful setup
        logger = logging.getLogger("azure.monitor")
        logger.info(
            "Azure Application Insights monitoring configured successfully",
            extra={
                "app_insights_enabled": True,
                "custom_metrics_registered": True,
                "system_metrics_collection": True
            }
        )
        
        return True
    return False

def add_custom_properties(envelope):
    """Add custom properties to all telemetry sent to Application Insights"""
    envelope.tags['ai.cloud.role'] = settings.PROJECT_NAME
    envelope.tags['ai.cloud.roleInstance'] = socket.gethostname()
    
    # Add custom properties
    envelope.data.baseData.properties['environment'] = settings.ENVIRONMENT
    envelope.data.baseData.properties['python_version'] = platform.python_version()
    
    # For container apps, add container-specific information
    if os.environ.get("CONTAINER_APP_NAME"):
        envelope.data.baseData.properties['container_app'] = os.environ.get("CONTAINER_APP_NAME")
        envelope.data.baseData.properties['container_revision'] = os.environ.get("CONTAINER_APP_REVISION")
    
    return True

def register_custom_metrics(view_manager):
    """Register custom metrics to track in Azure Monitor"""
    
    # Request latency distribution
    latency_view = view_module.View(
        "request_latency",
        "The distribution of request latencies",
        [],
        _REQUEST_LATENCY_MS,
        aggregation_module.DistributionAggregation(
            [0, 5, 10, 25, 50, 75, 100, 250, 500, 750, 1000, 2500, 5000, 10000])
    )
    view_manager.register_view(latency_view)
    
    # Request count
    request_count_view = view_module.View(
        "request_count",
        "Count of requests",
        ["path", "method", "status_code"],
        _REQUEST_COUNT,
        aggregation_module.CountAggregation()
    )
    view_manager.register_view(request_count_view)
    
    # Error count
    error_count_view = view_module.View(
        "error_count",
        "Count of errors",
        ["path", "method", "error_type"],
        _ERROR_COUNT,
        aggregation_module.CountAggregation()
    )
    view_manager.register_view(error_count_view)
    
    # API calls by category
    api_calls_view = view_module.View(
        "api_calls",
        "Count of API calls by category",
        ["api_category", "path"],
        _API_CALLS,
        aggregation_module.CountAggregation()
    )
    view_manager.register_view(api_calls_view)
    
    # Image generation latency
    image_gen_latency_view = view_module.View(
        "image_generation_latency",
        "The distribution of image generation latencies",
        ["model", "size"],
        _IMAGE_GENERATION_LATENCY,
        aggregation_module.DistributionAggregation(
            [0, 100, 250, 500, 1000, 2500, 5000, 10000, 20000, 30000])
    )
    view_manager.register_view(image_gen_latency_view)
    
    # Video generation latency
    video_gen_latency_view = view_module.View(
        "video_generation_latency",
        "The distribution of video generation latencies",
        ["model", "duration"],
        _VIDEO_GENERATION_LATENCY,
        aggregation_module.DistributionAggregation(
            [0, 1000, 5000, 10000, 30000, 60000, 120000, 300000])
    )
    view_manager.register_view(video_gen_latency_view)
    
    # Memory usage
    memory_view = view_module.View(
        "memory_usage",
        "Memory usage in MB",
        [],
        _MEMORY_USAGE,
        aggregation_module.LastValueAggregation()
    )
    view_manager.register_view(memory_view)
    
    # CPU usage
    cpu_view = view_module.View(
        "cpu_usage",
        "CPU usage percentage",
        [],
        _CPU_USAGE,
        aggregation_module.LastValueAggregation()
    )
    view_manager.register_view(cpu_view)

async def collect_system_metrics():
    """Collect system metrics periodically"""
    stats = stats_module.stats
    while True:
        try:
            # Memory usage
            memory_info = psutil.Process().memory_info()
            memory_mb = memory_info.rss / (1024 * 1024)  # Convert to MB
            
            # CPU usage
            cpu_percent = psutil.Process().cpu_percent(interval=1.0)
            
            # Record metrics
            stats.record([
                stats_module.stats.stats_recorder.new_measurement(
                    _MEMORY_USAGE.name, memory_mb),
                stats_module.stats.stats_recorder.new_measurement(
                    _CPU_USAGE.name, cpu_percent)
            ])
            
        except Exception as e:
            logger = logging.getLogger("azure.monitor")
            logger.error(f"Error collecting system metrics: {str(e)}", exc_info=True)
        
        # Wait before collecting metrics again
        await asyncio.sleep(30)  # Collect every 30 seconds

def start_system_metrics_collection():
    """Start the system metrics collection in the background"""
    if settings.ENABLE_AZURE_MONITOR:
        try:
            loop = asyncio.get_event_loop()
            asyncio.ensure_future(collect_system_metrics())
        except Exception as e:
            logger = logging.getLogger("azure.monitor")
            logger.error(f"Failed to start system metrics collection: {str(e)}", exc_info=True)

def azure_monitor(function=None, category=None, name=None, properties=None):
    """Decorator to monitor Azure function calls"""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time()
            event_name = name or func.__name__
            event_category = category or func.__module__
            event_properties = properties or {}
            
            # Add function details to properties
            event_properties.update({
                "function": func.__name__,
                "module": func.__module__,
            })
            
            # Track start of operation
            azure_tracer.track_event(f"{event_category}.{event_name}.start", event_properties)
            
            try:
                result = await func(*args, **kwargs)
                
                # Calculate duration
                duration_ms = (time() - start_time) * 1000
                
                # Track successful completion
                azure_tracer.track_event(
                    f"{event_category}.{event_name}.complete", 
                    {**event_properties, "duration_ms": duration_ms, "success": True}
                )
                
                return result
                
            except Exception as e:
                # Calculate duration
                duration_ms = (time() - start_time) * 1000
                
                # Track failure
                azure_tracer.track_event(
                    f"{event_category}.{event_name}.error",
                    {
                        **event_properties,
                        "duration_ms": duration_ms,
                        "success": False,
                        "error_type": type(e).__name__,
                        "error_message": str(e)
                    }
                )
                
                # Re-raise the exception
                raise
                
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time()
            event_name = name or func.__name__
            event_category = category or func.__module__
            event_properties = properties or {}
            
            # Add function details to properties
            event_properties.update({
                "function": func.__name__,
                "module": func.__module__,
            })
            
            # Track start of operation
            azure_tracer.track_event(f"{event_category}.{event_name}.start", event_properties)
            
            try:
                result = func(*args, **kwargs)
                
                # Calculate duration
                duration_ms = (time() - start_time) * 1000
                
                # Track successful completion
                azure_tracer.track_event(
                    f"{event_category}.{event_name}.complete", 
                    {**event_properties, "duration_ms": duration_ms, "success": True}
                )
                
                return result
                
            except Exception as e:
                # Calculate duration
                duration_ms = (time() - start_time) * 1000
                
                # Track failure
                azure_tracer.track_event(
                    f"{event_category}.{event_name}.error",
                    {
                        **event_properties,
                        "duration_ms": duration_ms,
                        "success": False,
                        "error_type": type(e).__name__,
                        "error_message": str(e)
                    }
                )
                
                # Re-raise the exception
                raise
        
        # Return the appropriate wrapper based on if the function is async or not
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    # Handle both @azure_monitor and @azure_monitor() syntax
    if function is None:
        return decorator
    return decorator(function)

class AzureTracer:
    """Helper class to manage Azure tracing with custom events"""
    def __init__(self):
        if settings.ENABLE_AZURE_MONITOR and settings.APPLICATION_INSIGHTS_CONNECTION_STRING:
            azure_exporter = AzureExporter(
                connection_string=settings.APPLICATION_INSIGHTS_CONNECTION_STRING
            )
            self.tracer = Tracer(
                exporter=azure_exporter,
                sampler=ProbabilitySampler(1.0),
            )
            self.enabled = True
        else:
            self.tracer = None
            self.enabled = False
    
    def trace(self, name, callback, attributes=None):
        """Trace a function call with custom attributes"""
        if not self.enabled or not self.tracer:
            return callback()
        
        with self.tracer.span(name=name) as span:
            if attributes:
                for key, value in attributes.items():
                    span.add_attribute(key, str(value))
            try:
                result = callback()
                return result
            except Exception as e:
                span.status = Status(
                    code=Status.UNKNOWN,
                    message=str(e)
                )
                raise
    
    def track_event(self, name, properties=None, measurements=None):
        """Track a custom event in Azure Monitor"""
        if not self.enabled or not self.tracer:
            return
        
        # Add default properties
        all_properties = {
            "timestamp": time(),
            "hostname": socket.gethostname()
        }
        
        # Add custom properties
        if properties:
            all_properties.update(properties)
            
        with self.tracer.span(name) as span:
            span.span_kind = SpanKind.CLIENT
            for key, value in all_properties.items():
                span.add_attribute(key, str(value))
                
            if measurements:
                for key, value in measurements.items():
                    span.add_attribute(f"measurement.{key}", value)
    
    def track_dependency(self, name, target, data, start_time=None, end_time=None, result_code=None, success=True):
        """Track an external dependency call"""
        if not self.enabled or not self.tracer:
            return
            
        if not start_time:
            start_time = time()
        if not end_time:
            end_time = time()
            
        duration_ms = int((end_time - start_time) * 1000)
        
        with self.tracer.span(name) as span:
            span.span_kind = SpanKind.CLIENT
            span.add_attribute(COMMON_ATTRIBUTES['HTTP_URL'], target)
            span.add_attribute("dependency.name", name)
            span.add_attribute("dependency.data", data)
            span.add_attribute("dependency.duration", duration_ms)
            span.add_attribute("dependency.success", success)
            if result_code:
                span.add_attribute("dependency.resultCode", result_code)
    
    def track_api_call(self, api_name: str, endpoint: str, method: str, params: Optional[Dict[str, Any]] = None,
                      start_time: float = None, end_time: float = None, success: bool = True, 
                      error_message: str = None, status_code: int = None):
        """Track an API call with detailed information"""
        if not self.enabled:
            return
            
        if not start_time:
            start_time = time()
        if not end_time:
            end_time = time()
            
        duration_ms = int((end_time - start_time) * 1000)
        
        properties = {
            "api_name": api_name,
            "endpoint": endpoint,
            "method": method,
            "duration_ms": duration_ms,
            "success": success
        }
        
        # Add optional properties
        if params:
            # Filter out potentially sensitive information
            filtered_params = {k: v for k, v in params.items() 
                             if k.lower() not in ['api_key', 'key', 'token', 'secret', 'password']}
            properties["parameters"] = str(filtered_params)
            
        if status_code:
            properties["status_code"] = status_code
            
        if error_message and not success:
            properties["error_message"] = error_message
            
        # Track as a custom event
        self.track_event(
            f"api.call.{api_name}",
            properties=properties,
            measurements={"duration": duration_ms}
        )
        
    def track_generation_metrics(self, generation_type: str, model: str, params: Dict[str, Any], 
                              duration_ms: float, success: bool, error_message: str = None):
        """Track metrics for AI generation operations"""
        if not self.enabled:
            return
            
        event_name = f"ai.generation.{generation_type}"
        
        properties = {
            "model": model,
            "success": success,
        }
        
        # Add generation parameters, filtering out sensitive information
        for key, value in params.items():
            if key.lower() not in ['api_key', 'key', 'token', 'secret', 'password']:
                properties[f"param.{key}"] = str(value)
        
        if not success and error_message:
            properties["error_message"] = error_message
            
        # Track as a custom event with duration measurement
        self.track_event(
            event_name,
            properties=properties,
            measurements={"duration": duration_ms}
        )
        
        # Also record appropriate metrics based on generation type
        stats = stats_module.stats
        if generation_type == "image":
            stats.record([
                stats_module.stats.stats_recorder.new_measurement(
                    _IMAGE_GENERATION_LATENCY.name, duration_ms)
            ], {
                "model": model,
                "size": params.get("size", "unknown"),
            })
        elif generation_type == "video":
            stats.record([
                stats_module.stats.stats_recorder.new_measurement(
                    _VIDEO_GENERATION_LATENCY.name, duration_ms)
            ], {
                "model": model,
                "duration": params.get("duration", "unknown"),
            })
                
# Create a global instance of the Azure tracer
azure_tracer = AzureTracer()
