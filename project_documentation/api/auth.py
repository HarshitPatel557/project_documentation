import base64
import binascii
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import frappe
import jwt
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from jwt.exceptions import (
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
    InvalidTokenError,
)

from frappe.utils import get_url
from frappe.www.login import redirect_post_login


# =========================================================
# PROMOT SSO CONFIGURATION
# =========================================================

# RS256 JWT Settings
SSO_ISSUER = "ProMot"
SSO_AUDIENCE = "Promot Wiki"
SSO_ALGORITHM = "RS256"

PUBLIC_KEY_PATH = frappe.get_app_path(
    "project_documentation",
    "keys",
    "promot_public_key.pem",
)

# AES-GCM Parent Token Settings
DEFAULT_PARENT_TOKEN_AES_KEY = "hQ5fe7+8RuL45KtAN1PdqmglC/XWm5tIhyviTr/YqLg="


# =========================================================
# RS256 PUBLIC KEY RESOLUTION
# =========================================================

def _get_public_key():
    """
    Load the Promot RSA public key from site_config.json or the pem file.
    Supports raw PEM format as well as base64-encoded keys.
    """
    key_content = frappe.conf.get("promot_sso_public_key")

    if not key_content and os.path.exists(PUBLIC_KEY_PATH):
        try:
            with open(PUBLIC_KEY_PATH, "r") as file:
                key_content = file.read()
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "Promot SSO Public Key File Read Error",
            )

    if not key_content:
        frappe.throw("Promot SSO public key is not configured")

    key_content = key_content.strip()

    # If the key is base64-encoded, decode it
    if not key_content.startswith("-----BEGIN"):
        try:
            decoded = base64.b64decode(key_content).decode("utf-8").strip()
            if decoded.startswith("-----BEGIN"):
                return decoded
        except Exception:
            pass

    return key_content


# =========================================================
# AES-GCM / PARENT TOKEN CIPHER HELPERS
# =========================================================

def _normalize_base64_token(token):
    token = (token or "").strip()
    token = token.replace("\n", "").replace("\r", "").replace(" ", "+")

    padding_needed = len(token) % 4
    if padding_needed:
        token += "=" * (4 - padding_needed)

    return token


def _decode_base64_bytes(token):
    token = _normalize_base64_token(token)

    try:
        return base64.b64decode(token)
    except (binascii.Error, ValueError):
        try:
            return base64.urlsafe_b64decode(token)
        except (binascii.Error, ValueError):
            frappe.throw("Invalid base64 token")


def _get_parent_token_aes_key_bytes():
    key = frappe.conf.get("parent_token_aes_key") or DEFAULT_PARENT_TOKEN_AES_KEY
    return base64.b64decode(key)


def _get_parent_token_key_variants():
    key_value = frappe.conf.get("parent_token_aes_key") or DEFAULT_PARENT_TOKEN_AES_KEY
    decoded_key = base64.b64decode(key_value)
    utf8_key = key_value.encode("utf-8")

    variants = []
    seen = set()

    def add_variant(name, key_bytes):
        if not key_bytes or len(key_bytes) not in (16, 24, 32):
            return
        signature = (name, key_bytes)
        if signature in seen:
            return
        seen.add(signature)
        variants.append((name, key_bytes))

    add_variant("base64_key", decoded_key)
    add_variant("base64_key_16", decoded_key[:16])
    add_variant("utf8_key_32", utf8_key[:32] if len(utf8_key) >= 32 else utf8_key.ljust(32, b"\0"))
    add_variant("utf8_key_16", utf8_key[:16] if len(utf8_key) >= 16 else utf8_key.ljust(16, b"\0"))
    add_variant("sha256_utf8_key", hashlib.sha256(utf8_key).digest())

    return variants


def _unpad_pkcs7(padded_plaintext):
    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded_plaintext) + unpadder.finalize()


def _aes_cbc_decrypt(key_bytes, iv_bytes, ciphertext):
    cipher = Cipher(algorithms.AES(key_bytes), modes.CBC(iv_bytes))
    decryptor = cipher.decryptor()
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    return _unpad_pkcs7(padded_plaintext)


def _aes_ecb_decrypt(key_bytes, ciphertext):
    cipher = Cipher(algorithms.AES(key_bytes), modes.ECB())
    decryptor = cipher.decryptor()
    padded_plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    return _unpad_pkcs7(padded_plaintext)


def _aes_gcm_decrypt(key_bytes, nonce_bytes, ciphertext_with_tag):
    aesgcm = AESGCM(key_bytes)
    return aesgcm.decrypt(nonce_bytes, ciphertext_with_tag, None)


def _try_parse_plain_base64_json(token):
    try:
        decoded_bytes = _decode_base64_bytes(token)
    except Exception:
        return None

    for encoding in ("utf-8", "utf-16-le", "utf-16"):
        try:
            decoded_text = decoded_bytes.decode(encoding).strip().lstrip("\ufeff")
        except UnicodeDecodeError:
            continue

        if decoded_text.startswith("{") or "{" in decoded_text:
            try:
                return _normalize_parent_token_payload(decoded_text)
            except Exception:
                continue

    return None


def _parse_parent_token_plaintext(plaintext):
    decoded_text = None
    for encoding in ("utf-8", "utf-16-le", "utf-16"):
        try:
            decoded_text = plaintext.decode(encoding).strip().lstrip("\ufeff")
            break
        except UnicodeDecodeError:
            continue

    if decoded_text is None:
        raise ValueError("Decrypted token is not valid text")

    if not decoded_text.startswith("{"):
        start = decoded_text.find("{")
        end = decoded_text.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("Decrypted token does not contain JSON")
        decoded_text = decoded_text[start : end + 1]

    return _normalize_parent_token_payload(decoded_text)


def _normalize_parent_token_payload(data):
    if isinstance(data, str):
        data = frappe.parse_json(data)

    if not isinstance(data, dict):
        frappe.throw("Invalid parent token payload")

    return {
        "uid": data.get("uid") or data.get("Uid") or data.get("UserId") or data.get("userid"),
        "email": data.get("email") or data.get("Email"),
        "name": (
            data.get("name")
            or data.get("Name")
            or data.get("user_name")
            or data.get("User_Name")
            or data.get("Employee_Name")
        ),
        "roles": data.get("roles") or data.get("Roles") or [],
        "jti": data.get("jti") or data.get("Jti") or data.get("JTI"),
        "iat": data.get("iat"),
        "exp": data.get("exp"),
        "iss": data.get("iss"),
        "aud": data.get("aud"),
        "_token_type": "AES-GCM",
    }


def _encrypt_parent_token_payload(payload):
    key_bytes = _get_parent_token_aes_key_bytes()
    plaintext = frappe.as_json(payload).encode("utf-8")

    nonce_bytes = os.urandom(12)
    ciphertext_with_tag = AESGCM(key_bytes).encrypt(nonce_bytes, plaintext, None)

    return base64.b64encode(nonce_bytes + ciphertext_with_tag).decode("utf-8")


def _decrypt_parent_token(token):
    plain_payload = _try_parse_plain_base64_json(token)
    if plain_payload:
        return plain_payload

    encrypted_bytes = _decode_base64_bytes(token)
    configured_iv = frappe.conf.get("parent_token_aes_iv")

    if configured_iv:
        if len(configured_iv) == 16:
            iv_bytes = configured_iv.encode("utf-8")
        else:
            iv_bytes = base64.b64decode(configured_iv)

        for _name, key_bytes in _get_parent_token_key_variants():
            try:
                plaintext = _aes_gcm_decrypt(key_bytes, iv_bytes, encrypted_bytes)
                return _parse_parent_token_plaintext(plaintext)
            except Exception:
                pass

            if len(encrypted_bytes) % 16 == 0:
                try:
                    plaintext = _aes_cbc_decrypt(key_bytes, iv_bytes, encrypted_bytes)
                    return _parse_parent_token_plaintext(plaintext)
                except Exception:
                    pass

        frappe.throw("Unable to decrypt parent token with configured IV")

    decrypt_attempts = []
    key_value = frappe.conf.get("parent_token_aes_key") or DEFAULT_PARENT_TOKEN_AES_KEY
    utf8_iv_from_key = key_value[:16].encode("utf-8")

    for key_name, key_bytes in _get_parent_token_key_variants():
        if len(encrypted_bytes) > 28:
            decrypt_attempts.append(
                (
                    f"{key_name}:gcm_nonce_12",
                    lambda key=key_bytes: _aes_gcm_decrypt(
                        key, encrypted_bytes[:12], encrypted_bytes[12:]
                    ),
                )
            )

        if len(encrypted_bytes) > 32:
            decrypt_attempts.append(
                (
                    f"{key_name}:gcm_nonce_16",
                    lambda key=key_bytes: _aes_gcm_decrypt(
                        key, encrypted_bytes[:16], encrypted_bytes[16:]
                    ),
                )
            )

        if len(encrypted_bytes) > 16 and len(encrypted_bytes[16:]) % 16 == 0:
            decrypt_attempts.append(
                (
                    f"{key_name}:prepended_iv",
                    lambda key=key_bytes: _aes_cbc_decrypt(
                        key, encrypted_bytes[:16], encrypted_bytes[16:]
                    ),
                )
            )

        if len(encrypted_bytes) % 16 == 0:
            decrypt_attempts.extend(
                [
                    (
                        f"{key_name}:zero_iv",
                        lambda key=key_bytes: _aes_cbc_decrypt(key, bytes(16), encrypted_bytes),
                    ),
                    (
                        f"{key_name}:ecb",
                        lambda key=key_bytes: _aes_ecb_decrypt(key, encrypted_bytes),
                    ),
                ]
            )

        if len(key_bytes) >= 16 and len(encrypted_bytes) % 16 == 0:
            decrypt_attempts.append(
                (
                    f"{key_name}:iv_from_key",
                    lambda key=key_bytes: _aes_cbc_decrypt(
                        key, key[:16], encrypted_bytes
                    ),
                )
            )

        if len(encrypted_bytes) % 16 == 0:
            decrypt_attempts.append(
                (
                    f"{key_name}:iv_from_key_string",
                    lambda key=key_bytes, iv=utf8_iv_from_key: _aes_cbc_decrypt(
                        key, iv, encrypted_bytes
                    ),
                )
            )

    last_error = None
    for _mode_name, decrypt_fn in decrypt_attempts:
        try:
            plaintext = decrypt_fn()
            return _parse_parent_token_plaintext(plaintext)
        except Exception as error:
            last_error = error

    if last_error:
        frappe.throw(f"Unable to decrypt parent token: {last_error}")

    frappe.throw("Unable to decrypt parent token")


# =========================================================
# RS256 JWT VERIFIER
# =========================================================

def _verify_jwt_token(token):
    public_key = _get_public_key()

    payload = jwt.decode(
        token,
        public_key,
        algorithms=[SSO_ALGORITHM],
        issuer=SSO_ISSUER,
        audience=SSO_AUDIENCE,
    )

    return {
        "uid": payload.get("uid") or payload.get("UserId"),
        "email": payload.get("email"),
        "name": payload.get("name"),
        "roles": payload.get("roles", []),
        "jti": payload.get("jti"),
        "iat": payload.get("iat"),
        "exp": payload.get("exp"),
        "iss": payload.get("iss"),
        "aud": payload.get("aud"),
        "_token_type": "RS256",
    }


# =========================================================
# DUAL-MODE TOKEN VERIFIER
# =========================================================

def verify_sso_token(token):
    """
    Auto-detects token format:
    1. If token has exactly 2 dots (header.payload.signature), verifies as RS256 JWT.
    2. Otherwise, decrypts as AES-GCM Base64 parent token.
    """
    if not token:
        frappe.throw("SSO token is required")

    token = token.strip()

    # RS256 JWT (3-part dot-separated)
    if token.count(".") == 2:
        return _verify_jwt_token(token)

    # Base64-encoded encrypted parent token (AES-GCM / CBC)
    return _decrypt_parent_token(token)


# =========================================================
# TOKEN EXTRACTION
# =========================================================

def _get_sso_token(token=None):
    raw_token = None

    # 1. Direct function parameter
    if token:
        raw_token = token.strip()

    # 2. JSON request body
    if not raw_token:
        try:
            data = frappe.request.get_json(silent=True) or {}
            if data.get("token"):
                raw_token = data["token"].strip()
        except Exception:
            pass

    # 3. Form / query dictionary
    if not raw_token:
        form_token = frappe.form_dict.get("token")
        if form_token:
            raw_token = form_token.strip()

    # 4. HTTP Authorization header (Bearer)
    if not raw_token:
        authorization = frappe.get_request_header("Authorization")
        if authorization:
            parts = authorization.split(" ", 1)
            if len(parts) == 2 and parts[0].lower() == "bearer":
                raw_token = parts[1].strip()

    if not raw_token:
        return None

    # If it is a JWT, preserve it cleanly
    if raw_token.count(".") == 2:
        return raw_token

    # Normalize Base64 (query parameter handling turns '+' into ' ')
    return _normalize_base64_token(raw_token)


# =========================================================
# REQUIRED CLAIMS & EXPIRY VALIDATION
# =========================================================

def _validate_claims(payload):
    if not payload.get("uid"):
        frappe.throw("Missing required SSO claim: uid")

    if not payload.get("jti"):
        frappe.throw("Missing required SSO claim: jti")

    # Validate expiration for tokens
    exp = payload.get("exp")
    if exp is not None:
        try:
            if isinstance(exp, (int, float)):
                exp_timestamp = float(exp)
            else:
                try:
                    exp_timestamp = float(exp)
                except ValueError:
                    exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
                    exp_timestamp = exp_dt.timestamp()

            now_timestamp = datetime.now(timezone.utc).timestamp()
            if now_timestamp > exp_timestamp:
                raise ExpiredSignatureError("SSO token expired")
        except ExpiredSignatureError:
            raise
        except Exception:
            pass


# =========================================================
# FIND IMPORTED USER
# =========================================================

def _find_imported_user(payload):
    uid = payload.get("uid")
    email = payload.get("email")

    user = None

    # -----------------------------------------------------
    # PRIMARY MAPPING: custom_external_user_id == uid
    # -----------------------------------------------------
    if uid:
        user = frappe.db.get_value(
            "User",
            {
                "custom_external_user_id": uid
            },
            [
                "name",
                "email",
                "enabled",
                "full_name",
                "custom_external_user_id",
            ],
            as_dict=True,
        )

    # -----------------------------------------------------
    # EMAIL FALLBACK
    # -----------------------------------------------------
    if not user and email:
        user = frappe.db.get_value(
            "User",
            {
                "email": email
            },
            [
                "name",
                "email",
                "enabled",
                "full_name",
                "custom_external_user_id",
            ],
            as_dict=True,
        )

    if not user:
        frappe.throw("Promot user is not registered in Frappe")

    if not user.enabled:
        frappe.throw("Frappe user account is disabled")

    return user


# =========================================================
# SSO TOKEN REPLAY PROTECTION
# =========================================================

def _check_token_replay(jti):
    existing = frappe.db.exists(
        "SSO Token Log",
        {
            "jti": jti
        },
    )

    if existing:
        frappe.throw("SSO token has already been used")


# =========================================================
# LOG TOKEN
# =========================================================

def _create_sso_log(payload, user):
    log = frappe.get_doc({
        "doctype": "SSO Token Log",
        "jti": payload.get("jti"),
        "user_id": user["name"],
        "email": payload.get("email") or user.get("email"),
        "user_name": payload.get("name") or user.get("full_name"),
        "roles": frappe.as_json(payload.get("roles", [])),
    })

    log.insert(
        ignore_permissions=True
    )


# =========================================================
# CREATE FRAPPE SESSION
# =========================================================

def _create_session(user):
    if getattr(frappe.local, "login_manager", None):
        frappe.local.login_manager.login_as(user["name"])
    else:
        frappe.set_user(user["name"])


# =========================================================
# PROMOT SSO LOGIN ENTRYPOINT
# =========================================================

def _is_active_pm(user):
    return bool(
        frappe.db.exists(
            "Project User Mapping",
            {
                "user": user,
                "project_designation": "PM",
                "still_involved": 1,
            },
        )
    )


@frappe.whitelist(allow_guest=True)
def sso_login(token=None):
    token = _get_sso_token(token)

    if not token:
        frappe.local.response.http_status_code = 400
        return {
            "success": False,
            "message": "SSO token is required",
        }

    try:
        # -------------------------------------------------
        # 1. VERIFY TOKEN (Dual-Mode: RS256 or AES-GCM)
        # -------------------------------------------------
        payload = verify_sso_token(token)

        # -------------------------------------------------
        # 2. VALIDATE CLAIMS
        # -------------------------------------------------
        _validate_claims(payload)

        # -------------------------------------------------
        # 3. CHECK REPLAY
        # -------------------------------------------------
        _check_token_replay(payload["jti"])

        # -------------------------------------------------
        # 4. FIND IMPORTED USER
        # -------------------------------------------------
        user = _find_imported_user(payload)

        # -------------------------------------------------
        # 5. CREATE TOKEN LOG
        # -------------------------------------------------
        _create_sso_log(payload, user)

        # -------------------------------------------------
        # 6. CREATE FRAPPE SESSION
        # -------------------------------------------------
        _create_session(user)
        frappe.db.commit()

        # -------------------------------------------------
        # 7. REDIRECT BY PROJECT ROLE
        # -------------------------------------------------
        if _is_active_pm(user["name"]):
            from project_documentation.api.project_access import ensure_pm_wiki_access

            ensure_pm_wiki_access(user["name"])
            redirect_to = "/project-documentation"
        else:
            redirect_to = "/wiki-app/spaces/"

        redirect_post_login(
            desk_user=True,
            redirect_to=redirect_to,
        )

        return {
            "success": True,
            "message": "Authenticated successfully",
            "user": user["name"],
            "redirect_to": redirect_to,
        }

    # -----------------------------------------------------
    # ERROR HANDLERS
    # -----------------------------------------------------
    except ExpiredSignatureError:
        frappe.local.response.http_status_code = 401
        return {
            "success": False,
            "message": "SSO token expired",
        }

    except InvalidAudienceError:
        frappe.local.response.http_status_code = 401
        return {
            "success": False,
            "message": "Invalid SSO token audience",
        }

    except InvalidIssuerError:
        frappe.local.response.http_status_code = 401
        return {
            "success": False,
            "message": "Invalid SSO token issuer",
        }

    except InvalidTokenError:
        frappe.local.response.http_status_code = 401
        return {
            "success": False,
            "message": "Invalid SSO token",
        }

    except frappe.ValidationError as e:
        frappe.local.response.http_status_code = 401
        return {
            "success": False,
            "message": str(e),
        }

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Promot SSO Authentication Error",
        )
        frappe.local.response.http_status_code = 500
        return {
            "success": False,
            "message": "SSO authentication failed",
        }


# =========================================================
# LOGOUT
# =========================================================

@frappe.whitelist()
def logout():
    frappe.local.login_manager.logout()
    return {
        "success": True,
        "message": "Logged out successfully",
    }


# =========================================================
# CURRENT USER
# =========================================================

@frappe.whitelist()
def get_current_user():
    user = frappe.session.user

    if user == "Guest":
        return {
            "authenticated": False,
            "user": None,
        }

    return {
        "authenticated": True,
        "user": user,
    }


# =========================================================
# TEST TOKEN GENERATORS (DEV / STAGING TESTING)
# =========================================================

TEST_PRIVATE_KEY_PATH = frappe.get_app_path(
    "project_documentation",
    "keys",
    "test_private_key.pem",
)


@frappe.whitelist(allow_guest=True)
def generate_test_sso_token(email, expiry_seconds=30):
    """
    Simulates Promot generating an RS256 JWT SSO token.
    """
    if not email:
        frappe.throw("email is required")

    user = frappe.db.get_value(
        "User",
        {"email": email},
        ["name", "email", "enabled", "full_name", "custom_external_user_id"],
        as_dict=True,
    )

    if not user:
        frappe.throw("User does not exist in Frappe")

    if not user.enabled:
        frappe.throw("User is disabled")

    if not user.custom_external_user_id:
        frappe.throw("User does not have custom_external_user_id")

    if not os.path.exists(TEST_PRIVATE_KEY_PATH):
        frappe.throw("Test private key is missing")

    with open(TEST_PRIVATE_KEY_PATH, "r") as file:
        private_key = file.read()

    now = datetime.now(timezone.utc)
    expiry = now + timedelta(seconds=int(expiry_seconds or 30))

    payload = {
        "iss": SSO_ISSUER,
        "aud": SSO_AUDIENCE,
        "uid": user.custom_external_user_id,
        "email": user.email,
        "name": user.full_name,
        "roles": [],
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expiry.timestamp()),
    }

    token = jwt.encode(payload, private_key, algorithm=SSO_ALGORITHM)

    return {
        "success": True,
        "format": "RS256 JWT",
        "token": token,
        "payload": payload,
    }


@frappe.whitelist(allow_guest=True)
def generate_test_parent_token(email, expiry_seconds=30):
    """
    Simulates Promot generating an AES-GCM parent token.
    """
    if not email:
        frappe.throw("email is required")

    user = frappe.db.get_value(
        "User",
        {"email": email},
        ["name", "email", "enabled", "full_name", "custom_external_user_id"],
        as_dict=True,
    )

    if not user:
        frappe.throw("User does not exist in Frappe")

    if not user.enabled:
        frappe.throw("User is disabled")

    if not user.custom_external_user_id:
        frappe.throw("User does not have custom_external_user_id")

    now = datetime.now(timezone.utc)
    expiry = now + timedelta(seconds=int(expiry_seconds or 30))

    payload = {
        "iss": SSO_ISSUER,
        "aud": SSO_AUDIENCE,
        "uid": user.custom_external_user_id,
        "email": user.email,
        "name": user.full_name,
        "roles": [],
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expiry.timestamp()),
    }

    token = _encrypt_parent_token_payload(payload)

    return {
        "success": True,
        "format": "AES-GCM Parent Token",
        "token": token,
        "payload": payload,
    }
