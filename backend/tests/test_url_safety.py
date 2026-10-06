import socket
import pytest
from unittest.mock import patch, MagicMock
from url_safety import (
    validate_url,
    is_safe_url,
    safe_requests_get,
    SSRFValidationError,
    ERROR_PRIVATE_OR_UNSUPPORTED,
)


def mock_dns_resolver(mapping: dict):
    """Returns a mock socket.getaddrinfo function mapped to specified IPs."""
    def _mock_getaddrinfo(host, port, *args, **kwargs):
        if host in mapping:
            ip = mapping[host]
            family = socket.AF_INET6 if ":" in ip else socket.AF_INET
            return [(family, socket.SOCK_STREAM, 6, "", (ip, port or 80))]
        # Try direct IP parsing
        if ":" in host:
            clean_host = host.strip("[]")
            return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", (clean_host, port or 80))]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (host, port or 80))]
    return _mock_getaddrinfo


@pytest.mark.parametrize(
    "url,resolved_ip",
    [
        ("http://localhost", "127.0.0.1"),
        ("http://127.0.0.1", "127.0.0.1"),
        ("http://10.0.0.1", "10.0.0.1"),
        ("http://10.254.1.5", "10.254.1.5"),
        ("http://192.168.1.1", "192.168.1.1"),
        ("http://169.254.169.254", "169.254.169.254"),
        ("http://[::1]", "::1"),
        ("http://private.example.internal", "172.16.0.5"),
    ],
)
def test_private_and_loopback_ips_rejected(url, resolved_ip):
    with patch("socket.getaddrinfo", side_effect=mock_dns_resolver({url: resolved_ip, "localhost": "127.0.0.1", "private.example.internal": "172.16.0.5"})):
        with pytest.raises(SSRFValidationError) as exc:
            validate_url(url)
        assert ERROR_PRIVATE_OR_UNSUPPORTED in str(exc.value)
        assert is_safe_url(url) is False


def test_url_with_credentials_rejected():
    with pytest.raises(SSRFValidationError) as exc:
        validate_url("http://admin:secret@example.com")
    assert ERROR_PRIVATE_OR_UNSUPPORTED in str(exc.value)

    with pytest.raises(SSRFValidationError):
        validate_url("https://user@example.com")


def test_invalid_scheme_and_ports():
    # Only http and https
    with pytest.raises(SSRFValidationError):
        validate_url("ftp://example.com")
    with pytest.raises(SSRFValidationError):
        validate_url("file:///etc/passwd")

    # Allowed ports 80 and 443 only
    with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 8080))]):
        with pytest.raises(SSRFValidationError):
            validate_url("http://example.com:8080")
        with pytest.raises(SSRFValidationError):
            validate_url("http://example.com:22")


def test_normal_public_url_accepted():
    with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]):
        url = "http://example.com/pricing"
        assert validate_url(url) == url
        assert is_safe_url(url) is True


def test_redirect_to_private_ip_is_blocked():
    """Ensure safe_requests_get blocks redirect from a public to a private URL."""
    # Hop 1: public URL returns 302 -> private URL
    hop1_response = MagicMock()
    hop1_response.is_redirect = True
    hop1_response.status_code = 302
    hop1_response.headers = {"Location": "http://169.254.169.254/latest/meta-data"}

    def mock_get(url, *args, **kwargs):
        if "public.com" in url:
            return hop1_response
        raise AssertionError("Should not make request to private target")

    dns_map = {
        "public.com": "93.184.216.34",
        "169.254.169.254": "169.254.169.254",
    }

    with patch("socket.getaddrinfo", side_effect=mock_dns_resolver(dns_map)):
        with patch("requests.Session.get", side_effect=mock_get):
            with pytest.raises(SSRFValidationError) as exc:
                safe_requests_get("http://public.com")
            assert ERROR_PRIVATE_OR_UNSUPPORTED in str(exc.value)


def test_response_size_limit():
    """Ensure safe_requests_get raises SSRFValidationError if response exceeds 2MB."""
    mock_resp = MagicMock()
    mock_resp.is_redirect = False
    mock_resp.status_code = 200
    # Yield 3MB of chunks
    mock_resp.iter_content = MagicMock(return_value=[b"x" * 1024 * 1024 for _ in range(3)])

    with patch("socket.getaddrinfo", return_value=[(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))]):
        with patch("requests.Session.get", return_value=mock_resp):
            with pytest.raises(SSRFValidationError) as exc:
                safe_requests_get("http://example.com", max_bytes=2 * 1024 * 1024)
            assert "exceeded maximum" in str(exc.value)
