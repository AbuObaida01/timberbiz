from slowapi import Limiter
from slowapi.util import get_remote_address

# Use client IP address as the rate limit key
# get_remote_address extracts IP from request
limiter = Limiter(key_func=get_remote_address)