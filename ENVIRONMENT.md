# Environment Configuration for CROssBAR LLM

CROssBAR LLM backend can be configured to run in different environments with distinct behaviors for development and production.

## Environment Types

The application supports two environment types:
- **Development**: Optimized for local development with security features relaxed and no rate limiting
- **Production**: Full security features enabled with CSRF protection and rate limiting

## Configuration

The environment is determined by the `CROSSBAR_ENV` environment variable:

```
CROSSBAR_ENV=development    # For development mode (default if not set)
CROSSBAR_ENV=production     # For production mode
```

You can set this in your `.env` file or directly in your environment.

## Features Affected by Environment

| Feature | Development | Production |
|---------|-------------|------------|
| CSRF Protection | Disabled | Enabled |
| Rate Limiting | Disabled | Enabled |
| Debug Logging | Verbose | Minimal |

### Rate Limits (Production Only)

Rate limiting in production mode follows these defaults:
- 6 requests per minute
- 20 requests per hour
- 50 requests per day

## Setting the Environment

### In .env file

```
# Other environment variables...
CROSSBAR_ENV=development
```

### In Docker

```
docker run -e CROSSBAR_ENV=production ...
```

### In shell

```bash
# For development
export CROSSBAR_ENV=development

# For production
export CROSSBAR_ENV=production
```

## Checking Current Environment

You can check the current environment configuration by accessing the `/environment-info/` endpoint:

```
GET /environment-info/
```

Example response:
```json
{
  "environment": "development",
  "isProduction": false,
  "isDevelopment": true,
  "settings": {
    "csrf_enabled": false,
    "rate_limiting_enabled": false,
    "rate_limits": {
      "minute": Infinity,
      "hour": Infinity,
      "day": Infinity
    }
  }
}
```
