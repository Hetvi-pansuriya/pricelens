"""
url_safety.py
─────────────────────────────────────────────────────────────────────────────
PURPOSE: Server-Side Request Forgery (SSRF) protection for all user-supplied URLs.

RULES:
- Only http and https schemes are permitted.
- Reject URLs with credentials (username or password).
- Allowed ports: 80 and 443 only.
- Resolve hostnames via DNS. Reject if ANY resolved IP address is:
  private, loopback, link-local, multicast, reserved, or unspecified
  (IPv4 and IPv6), including 169.254.169.254.
- Requests: Disable automatic redirects. Follow redirects manually (max 5 hops),
  re-validating every target hop. Cap response size at 2 MB. Keep timeout.
- Playwright: Request interception handler validating every request made.
- Plain-English error: "That link points to a private or unsupported address"
─────────────────────────────────────────────────────────────────────────────
"""

import ipaddress
import socket
import urllib.parse
from typing import Optional, List
import requests

ERROR_PRIVATE_OR_UNSUPPORTED = "That link points to a private or unsupported address"
MAX_REDIRECTS = 5
MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # 2 MB


class SSRFValidationError(ValueError):
    """Raised when a URL violates SSRF safety constraints."""
    pass


def is_ip_private_or_restricted(ip_obj: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Check if an IPv4 or IPv6 address is private, loopback, link-local, or restricted."""
    return (
        ip_obj.is_private
        or ip_obj.is_loopback
        or ip_obj.is_link_local
        or ip_obj.is_multicast
        or ip_obj.is_reserved
        or ip_obj.is_unspecified
    )


def validate_url(url: str) -> str:
    """
    Validates a URL against SSRF attack vectors.
    Returns the cleaned URL if safe, or raises SSRFValidationError.
    """
    if not url or not isinstance(url, str):
        raise SSRFValidationError(ERROR_PRIVATE_OR_UNSUPPORTED)

    parsed = urllib.parse.urlsplit(url.strip())

    # 1. Scheme check: only http and https
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFValidationError(ERROR_PRIVATE_OR_UNSUPPORTED)

    # 2. Reject credentials (username/password)
    if parsed.username or parsed.password:
        raise SSRFValidationError(ERROR_PRIVATE_OR_UNSUPPORTED)

    # 3. Hostname check
    hostname = parsed.hostname
    if not hostname:
        raise SSRFValidationError(ERROR_PRIVATE_OR_UNSUPPORTED)

    # 4. Port check: allowed ports are 80 and 443 only
    port = parsed.port
    if port is None:
        port = 80 if parsed.scheme.lower() == "http" else 443

    if port not in (80, 443):
        raise SSRFValidationError(ERROR_PRIVATE_OR_UNSUPPORTED)

    # 5. DNS Resolution & IP checks
    try:
        addr_info = socket.getaddrinfo(hostname, port, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
    except (socket.gaierror, socket.error):
        raise SSRFValidationError(ERROR_PRIVATE_OR_UNSUPPORTED)

    if not addr_info:
        raise SSRFValidationError(ERROR_PRIVATE_OR_UNSUPPORTED)

    # Check EVERY resolved IP address
    for family, _, _, _, sockaddr in addr_info:
        ip_str = sockaddr[0]
        # Normalize zone ID or scope from IPv6 if present
        if "%" in ip_str:
            ip_str = ip_str.split("%")[0]

        try:
            ip_obj = ipaddress.ip_address(ip_str)
        except ValueError:
            raise SSRFValidationError(ERROR_PRIVATE_OR_UNSUPPORTED)

        if is_ip_private_or_restricted(ip_obj):
            raise SSRFValidationError(ERROR_PRIVATE_OR_UNSUPPORTED)

        # Explicit safeguard against 169.254.169.254 cloud metadata
        if str(ip_obj) == "169.254.169.254":
            raise SSRFValidationError(ERROR_PRIVATE_OR_UNSUPPORTED)

    return url.strip()


def is_safe_url(url: str) -> bool:
    """Helper that returns True if the URL is safe, False otherwise."""
    try:
        validate_url(url)
        return True
    except (SSRFValidationError, Exception):
        return False


def safe_requests_get(
    url: str,
    timeout: int = 12,
    headers: Optional[dict] = None,
    max_redirects: int = MAX_REDIRECTS,
    max_bytes: int = MAX_RESPONSE_BYTES,
) -> requests.Response:
    """
    Safely fetches a URL using requests with manual redirect following
    and strict response size enforcement.
    """
    current_url = url
    session = requests.Session()

    for hop in range(max_redirects + 1):
        # Validate current hop URL
        validate_url(current_url)

        response = session.get(
            current_url,
            timeout=timeout,
            headers=headers,
            allow_redirects=False,
            stream=True,
        )

        if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            if not location:
                # Redirect without Location header
                break

            current_url = urllib.parse.urljoin(current_url, location)
            response.close()
            continue

        # Non-redirect response: read content up to max_bytes
        content = bytearray()
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                content.extend(chunk)
                if len(content) > max_bytes:
                    response.close()
                    raise SSRFValidationError("Response size exceeded maximum allowed limit of 2 MB")

        response._content = bytes(content)
        return response

    raise SSRFValidationError("Too many redirects")
