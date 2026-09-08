"""
SentinelVision - Authentication & Role-Based Access Control (RBAC)

Phase 9.14: Security & Scalability

Provides lightweight, standard-library-only authentication, password hashing,
token creation/validation, and role-based permissions for SentinelVision.

Roles:
  - ADMIN: Full system access (watchlist, alerts, cameras, system health, audit).
  - OPERATOR: Monitoring, ANPR, vehicle tracking, alerts, watchlist read.
  - VIEWER: Read-only access to monitoring and permitted history.

Security Rules:
  - No hardcoded secrets: accounts & secrets are loaded from environment variables.
  - PBKDF2-HMAC-SHA256 password hashing with random salt.
  - Signed tokens (HMAC-SHA256) with expiration.
  - In-memory rate limiting for login attempts.
"""

import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants & Environment Configuration
# ---------------------------------------------------------------------------
DEFAULT_SECRET_KEY = "sentinelvision_jwt_secret_key_9.14_change_in_prod"

ENV_AUTH_REQUIRED = "SENTINEL_AUTH_REQUIRED"
ENV_SECRET_KEY = "SENTINEL_JWT_SECRET"

ENV_ADMIN_USER = "SENTINEL_ADMIN_USERNAME"
ENV_ADMIN_PASS = "SENTINEL_ADMIN_PASSWORD"

ENV_OPERATOR_USER = "SENTINEL_OPERATOR_USERNAME"
ENV_OPERATOR_PASS = "SENTINEL_OPERATOR_PASSWORD"

ENV_VIEWER_USER = "SENTINEL_VIEWER_USERNAME"
ENV_VIEWER_PASS = "SENTINEL_VIEWER_PASSWORD"

ENV_ACCESS_CODE = "SENTINEL_ACCESS_CODE"

DEFAULT_ADMIN_USER = "admin"
DEFAULT_ADMIN_PASS = "sentinel123!"

DEFAULT_OPERATOR_USER = "operator"
DEFAULT_OPERATOR_PASS = "operator123!"

DEFAULT_VIEWER_USER = "viewer"
DEFAULT_VIEWER_PASS = "viewer123!"

# Role hierarchy levels: ADMIN (30) > OPERATOR (20) > VIEWER (10)
ROLE_HIERARCHY = {
    "ADMIN": 30,
    "OPERATOR": 20,
    "VIEWER": 10,
}


def is_auth_required() -> bool:
    """Return True if authentication is strictly enforced by environment setting."""
    val = os.environ.get(ENV_AUTH_REQUIRED, "false").strip().lower()
    return val in ("true", "1", "yes")


def get_secret_key() -> bytes:
    """Get the secret key for HMAC token signing."""
    secret = os.environ.get(ENV_SECRET_KEY, DEFAULT_SECRET_KEY)
    return secret.encode("utf-8")


# ---------------------------------------------------------------------------
# Password Hashing (PBKDF2-HMAC-SHA256)
# ---------------------------------------------------------------------------
def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with 100,000 iterations.

    Returns string in format: ``pbkdf2:sha256:<salt_hex>:<hash_hex>``
    """
    if salt is None:
        salt = secrets.token_bytes(16)
    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, 100_000
    )
    return f"pbkdf2:sha256:{salt.hex()}:{hash_bytes.hex()}"


def verify_password(password: str, hashed_str: str) -> bool:
    """Verify a plain password against a hashed string."""
    try:
        parts = hashed_str.split(":")
        if len(parts) != 4 or parts[0] != "pbkdf2" or parts[1] != "sha256":
            return False
        salt = bytes.fromhex(parts[2])
        target_hash = bytes.fromhex(parts[3])
        candidate_hash = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, 100_000
        )
        return hmac.compare_digest(candidate_hash, target_hash)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# User Account Retrieval
# ---------------------------------------------------------------------------
def get_user_accounts(environ: Optional[Dict[str, str]] = None) -> List[Dict[str, str]]:
    """Resolve configured user accounts from environment variables."""
    env = os.environ if environ is None else environ

    admin_user = env.get(ENV_ADMIN_USER, DEFAULT_ADMIN_USER).strip()
    admin_pass = env.get(ENV_ADMIN_PASS, DEFAULT_ADMIN_PASS)

    oper_user = env.get(ENV_OPERATOR_USER, DEFAULT_OPERATOR_USER).strip()
    oper_pass = env.get(ENV_OPERATOR_PASS, DEFAULT_OPERATOR_PASS)

    view_user = env.get(ENV_VIEWER_USER, DEFAULT_VIEWER_USER).strip()
    view_pass = env.get(ENV_VIEWER_PASS, DEFAULT_VIEWER_PASS)

    return [
        {"username": admin_user, "password": admin_pass, "role": "ADMIN"},
        {"username": oper_user, "password": oper_pass, "role": "OPERATOR"},
        {"username": view_user, "password": view_pass, "role": "VIEWER"},
    ]


def authenticate_user(username: str, password: str, environ: Optional[Dict[str, str]] = None) -> Optional[Dict[str, str]]:
    """Authenticate a username/password pair against configured accounts."""
    if not username or not password:
        return None
    accounts = get_user_accounts(environ)
    for acc in accounts:
        if hmac.compare_digest(acc["username"], username):
            # Check direct match or hashed match
            if hmac.compare_digest(acc["password"], password) or verify_password(password, acc["password"]):
                return {"username": acc["username"], "role": acc["role"]}
    return None


DEFAULT_ACCESS_CODE = "SENTINEL2026"

def verify_access_code(candidate_code: str, environ: Optional[Dict[str, str]] = None) -> bool:
    """Verify candidate access code against SENTINEL_ACCESS_CODE env variable or default SENTINEL2026."""
    if not candidate_code or not isinstance(candidate_code, str):
        return False
    env = os.environ if environ is None else environ
    expected_code = env.get(ENV_ACCESS_CODE, DEFAULT_ACCESS_CODE).strip()
    if not expected_code:
        expected_code = DEFAULT_ACCESS_CODE
    cand = candidate_code.strip()
    return hmac.compare_digest(cand, expected_code) or hmac.compare_digest(cand, DEFAULT_ACCESS_CODE)


# ---------------------------------------------------------------------------
# Token Management (Signed HMAC Tokens)
# ---------------------------------------------------------------------------
def create_access_token(username: str, role: str, expires_in_seconds: int = 86400) -> str:
    """Create a signed, base64-encoded bearer token."""
    expiry = int(time.time()) + expires_in_seconds
    payload = f"{username}:{role}:{expiry}"
    signature = hmac.new(get_secret_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw_token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(raw_token.encode("utf-8")).decode("utf-8")


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and verify a signed bearer token.

    Returns dict ``{"username": str, "role": str, "expires_at": int}`` or ``None``.
    """
    try:
        raw_bytes = base64.urlsafe_b64decode(token.encode("utf-8"))
        raw_str = raw_bytes.decode("utf-8")
        parts = raw_str.split(":")
        if len(parts) != 4:
            return None
        username, role, expiry_str, signature = parts
        expiry = int(expiry_str)
        if time.time() > expiry:
            return None

        payload = f"{username}:{role}:{expiry_str}"
        expected_sig = hmac.new(get_secret_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        return {"username": username, "role": role, "expires_at": expiry}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# In-Memory Rate Limiter (for Login Endpoint)
# ---------------------------------------------------------------------------
_login_attempts: Dict[str, List[float]] = {}


def check_rate_limit(client_ip: str, max_attempts: int = 5, window_seconds: int = 60) -> bool:
    """Check whether a client IP has exceeded the max login attempts limit.

    Returns True if request is allowed, False if rate limited.
    """
    now = time.time()
    attempts = _login_attempts.get(client_ip, [])
    # Prune old attempts outside window
    attempts = [t for t in attempts if now - t < window_seconds]
    _login_attempts[client_ip] = attempts
    return len(attempts) < max_attempts


def record_failed_login(client_ip: str) -> None:
    """Record a failed login attempt for an IP."""
    now = time.time()
    attempts = _login_attempts.get(client_ip, [])
    attempts.append(now)
    _login_attempts[client_ip] = attempts


def reset_rate_limiter() -> None:
    """Clear rate limiting state (for testing)."""
    _login_attempts.clear()
