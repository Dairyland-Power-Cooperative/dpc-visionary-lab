# Backend Logging and Azure Deployment Troubleshooting Guide

This document explains how logging is configured in the backend application and provides guidance for troubleshooting issues when deployed on Azure.

## Logging Configuration

The backend application has comprehensive logging configured to help diagnose issues, especially when deployed on Azure. The main components of the logging system are:

### 1. Structured JSON Logging

All logs are formatted as JSON to enable easier parsing and analysis in log management systems. Each log entry includes:

- Timestamp in ISO format
- Log level
- Source module/logger name
- Detailed message
- Context information (request ID, correlation ID, etc.)
- Host information (hostname, IP)
- Process/thread information
- Azure deployment details (when running on Azure)

### 2. Request/Response Logging

The application logs detailed information for each HTTP request:

- Request details (method, URL, client IP, headers)
- Response status code and timing
- Correlation IDs for request tracing
- Optional request/response body logging (configurable, disabled in production by default)

### 3. Azure Application Insights Integration

When enabled, the application integrates with Azure Application Insights for advanced monitoring:

- Distributed tracing of requests
- Custom metrics for performance monitoring
- Exception tracking with full stack traces
- Custom events for business logic tracking
- System metrics (CPU, memory usage)
- Dependency tracking for external services

## Environment Variables for Logging

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) | INFO |
| `ENVIRONMENT` | Environment name (development, staging, production) | development |
| `ENABLE_AZURE_MONITOR` | Enable Azure Application Insights integration | FALSE |
| `APPLICATION_INSIGHTS_CONNECTION_STRING` | Connection string for Azure Application Insights | None |
| `LOG_TO_FILE` | Enable file-based logging | FALSE |
| `LOG_FILE_PATH` | Path for log file | ./logs/app.log |
| `ENABLE_RESPONSE_LOGGING` | Log response bodies (development/debugging only) | TRUE in dev, FALSE in prod |
| `DEBUG_AZURE_STORAGE` | Enable debug-level logging for Azure Storage | FALSE |
| `DEBUG_BACKEND` | Enable debug-level logging for backend modules | FALSE |
| `ENABLE_DIAGNOSTICS` | Enable diagnostics endpoint in production | FALSE |

## Troubleshooting Azure Deployment Issues

### 1. Check Health Endpoint

The application provides a health check endpoint that returns detailed system information:

```
GET /api/v1/health
```

This endpoint shows:
- Basic status information
- Azure deployment details
- Directory permissions
- Python environment information

### 2. Use Diagnostics Endpoint

For more comprehensive diagnostics:

```
GET /api/v1/diagnostics
```

> **Note:** In production, this endpoint is disabled by default. Set `ENABLE_DIAGNOSTICS=true` to enable it.

The diagnostics endpoint provides:
- Directory access tests
- Environment variables (non-sensitive)
- System information
- Configuration status

### 3. Check Application Logs

When deployed on Azure Container Apps, you can access logs through:

- **Azure Portal:** Navigate to your container app > Monitoring > Log stream
- **Azure CLI:**
  ```
  az containerapp logs show --name <your-app-name> --resource-group <resource-group> --follow
  ```

### 4. Common Issues and Solutions

#### Image or Video Generation Fails

1. **Check storage configuration:** Verify Azure Blob Storage settings are correct and the application can connect
   - Look for logs with "Storage configuration" during application startup
   - Check if containers exist and are accessible

2. **Check AI service configuration:** Verify Azure OpenAI or OpenAI API settings
   - Look for logs with "AI Service configuration" during startup
   - Ensure API keys are correctly set

#### Cannot Write to File System

1. **Check directory permissions:** The application logs directory permissions during startup
   - Look for "Directory created or verified" logs
   - Check the diagnostics endpoint for write tests

2. **Container filesystem issues:** Azure Container Apps have ephemeral storage
   - Use Azure Blob Storage for persistent storage
   - Ensure directories are created at startup

#### CORS Issues with Frontend

1. **Check CORS configuration:** The application logs CORS origins during startup
   - Look for "Setting up CORS with origins" logs
   - Verify that your frontend origin is included

2. **Add environment variables:**
   ```
   CORS_ORIGINS=https://your-frontend-url.com,http://localhost:3000
   ```

#### Application Insights Not Working

1. **Check configuration:**
   - Verify `ENABLE_AZURE_MONITOR=true` is set
   - Verify `APPLICATION_INSIGHTS_CONNECTION_STRING` is correctly set

2. **Check startup logs:**
   - Look for "Azure monitoring setup successful" log
   - If failed, check the error message

## Best Practices for Logging

1. **Use correlation IDs:** Include the `X-Correlation-ID` header in requests between services

2. **Structured logging:** Always use structured logging patterns
   ```python
   logger.info("Message", extra={"key": "value"})
   ```

3. **Add context to logs:** Include relevant business context in logs
   ```python
   logger.info("User action", extra={"user_id": user_id, "action": action})
   ```

4. **Don't log sensitive data:** Never log API keys, tokens, or personal information

5. **Use appropriate log levels:**
   - `DEBUG`: Detailed information, typically of interest only when diagnosing problems
   - `INFO`: Confirmation that things are working as expected
   - `WARNING`: Indication that something unexpected happened, but the application is still working
   - `ERROR`: Due to a more serious problem, the application has not been able to perform a function
   - `CRITICAL`: A serious error, indicating that the program itself may be unable to continue running

## Additional Resources

- [Azure Container Apps Logging](https://learn.microsoft.com/en-us/azure/container-apps/logging)
- [Azure Application Insights](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
