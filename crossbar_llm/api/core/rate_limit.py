from typing import Callable

import hmac
from hashlib import sha256

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from crossbar_llm.api.core.settings import Settings


settings = Settings()


def _hash_ip(ip_address: str) -> str:
    return hmac.new(
        settings.env_settings.rate_limit_ip_hash_secret.get_secret_value().encode("utf-8"),
        ip_address.encode("utf-8"),
        digestmod=sha256
    ).hexdigest()


def rate_limit_key(request: Request) -> str:
    return _hash_ip(get_remote_address(request))


limiter = Limiter(
    key_func=rate_limit_key,
    headers_enabled=True,
    enabled=settings.rate_limit_enabled
)



def standard_rate_limits(func: Callable) -> Callable:
    for limit in settings.get_rate_limit_settings():
        func = limiter.limit(limit)(func)
    
    return func

   

