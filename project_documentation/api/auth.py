import frappe
import jwt
import uuid

from datetime import datetime, timedelta, timezone

from jwt.exceptions import (
    InvalidTokenError,
    ExpiredSignatureError,
    InvalidAudienceError,
    InvalidIssuerError,
)

from frappe.utils import get_url
from frappe.www.login import redirect_post_login


# =========================================================
# PROMOT SSO CONFIGURATION
# =========================================================

SSO_ISSUER = "ProMot"
SSO_AUDIENCE = "workflow and asset management"
SSO_ALGORITHM = "RS256"

PUBLIC_KEY_PATH = frappe.get_app_path(
    "project_documentation",
    "keys",
    "promot_public_key.pem",
)


# =========================================================
# KEY
# =========================================================

def _get_public_key():
    try:
        with open(PUBLIC_KEY_PATH, "r") as file:
            return file.read()

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Promot SSO Public Key Error",
        )

        frappe.throw(
            "Promot SSO public key is not configured"
        )


# =========================================================
# TOKEN EXTRACTION
# =========================================================

def _get_sso_token(token=None):

    # Query/function argument
    if token:
        return token.strip()

    # JSON body
    try:
        data = frappe.request.get_json(silent=True) or {}

        if data.get("token"):
            return data["token"].strip()

    except Exception:
        pass

    # Form/query parameter
    token = frappe.form_dict.get("token")

    if token:
        return token.strip()

    # Authorization header
    authorization = frappe.get_request_header(
        "Authorization"
    )

    if authorization:

        parts = authorization.split(" ", 1)

        if (
            len(parts) == 2
            and parts[0].lower() == "bearer"
        ):
            return parts[1].strip()

    return None


# =========================================================
# VERIFY PROMOT TOKEN
# =========================================================

def verify_sso_token(token):

    if not token:
        frappe.throw("SSO token is required")

    public_key = _get_public_key()

    payload = jwt.decode(
        token,
        public_key,
        algorithms=[SSO_ALGORITHM],
        issuer=SSO_ISSUER,
        audience=SSO_AUDIENCE,
    )

    return payload


# =========================================================
# REQUIRED CLAIMS
# =========================================================

def _validate_claims(payload):

    required_claims = [
        "uid",
        "email",
        "jti",
        "iat",
        "exp",
    ]

    missing = [
        claim
        for claim in required_claims
        if not payload.get(claim)
    ]

    if missing:
        frappe.throw(
            "Missing SSO claims: "
            + ", ".join(missing)
        )


# =========================================================
# FIND IMPORTED USER
# =========================================================

def _find_imported_user(payload):

    uid = payload.get("uid")
    email = payload.get("email")

    user = None

    # -----------------------------------------------------
    # PRIMARY MAPPING
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

        frappe.throw(
            "Promot user is not registered in Frappe"
        )

    if not user.enabled:

        frappe.throw(
            "Frappe user account is disabled"
        )

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
        frappe.throw(
            "SSO token has already been used"
        )


# =========================================================
# LOG TOKEN
# =========================================================

def _create_sso_log(payload, user):

    log = frappe.get_doc({
        "doctype": "SSO Token Log",

        "jti": payload.get("jti"),

        "user_id": user["name"],

        "email": payload.get("email"),

        "user_name": payload.get("name"),

        "roles": frappe.as_json(
            payload.get("roles", [])
        ),
    })

    log.insert(
        ignore_permissions=True
    )


# =========================================================
# CREATE FRAPPE SESSION
# =========================================================

def _create_session(user):
    frappe.local.login_manager.login_as(user["name"])


# =========================================================
# PROMOT SSO LOGIN
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
        # 1. VERIFY TOKEN
        # -------------------------------------------------

        payload = verify_sso_token(token)

        # -------------------------------------------------
        # 2. VALIDATE CLAIMS
        # -------------------------------------------------

        _validate_claims(payload)

        # -------------------------------------------------
        # 3. CHECK REPLAY
        # -------------------------------------------------

        _check_token_replay(
            payload["jti"]
        )

        # -------------------------------------------------
        # 4. FIND IMPORTED USER
        # -------------------------------------------------

        user = _find_imported_user(
            payload
        )

        # -------------------------------------------------
        # 5. CREATE TOKEN LOG
        # -------------------------------------------------

        _create_sso_log(
            payload , user
        )

        # -------------------------------------------------
        # 6. CREATE FRAPPE SESSION
        # -------------------------------------------------
        # Use the dedicated session helper so both the LoginManager
        # session and frappe.local.user are updated for this request.
        # This is important because this endpoint is the SSO entry point
        # and the browser must receive a real Frappe session, not Guest.

        _create_session(user)

        frappe.db.commit()

        # -------------------------------------------------
        # 7. REDIRECT BY PROJECT ROLE
        # -------------------------------------------------
        # Project Managers enter the Project Documentation manager page.
        # Other authenticated users enter the Wiki Spaces list.
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

        return

    # -----------------------------------------------------
    # TOKEN ERRORS
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
# =========================================================
# TEMPORARY PROMOT MOCK
# =========================================================
#
# REMOVE THIS SECTION WHEN REAL PROMOT SSO IS AVAILABLE.
#
# This does NOT create temporary users/projects.
# It takes an EXISTING imported Frappe User and creates
# a token that behaves like a Promot token.
#
# =========================================================

TEST_PRIVATE_KEY_PATH = frappe.get_app_path(
    "project_documentation",
    "keys",
    "test_private_key.pem",
)


@frappe.whitelist(allow_guest=True)
def generate_test_sso_token(email):

    """
    TEMPORARY TEST ONLY.

    Simulates Promot generating an SSO token.

    The user must already exist in Frappe.
    """

    if not email:

        frappe.throw(
            "email is required"
        )

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

        frappe.throw(
            "User does not exist in Frappe"
        )

    if not user.enabled:

        frappe.throw(
            "User is disabled"
        )

    if not user.custom_external_user_id:

        frappe.throw(
            "User does not have custom_external_user_id"
        )

    try:

        with open(
            TEST_PRIVATE_KEY_PATH,
            "r",
        ) as file:

            private_key = file.read()

    except Exception:

        frappe.throw(
            "Temporary test private key is missing"
        )

    now = datetime.now(
        timezone.utc
    )

    payload = {

        "iss": SSO_ISSUER,

        "aud": SSO_AUDIENCE,

        "uid": user.custom_external_user_id,

        "email": user.email,

        "name": user.full_name,

        "roles": [],

        "jti": str(
            uuid.uuid4()
        ),

        "iat": int(
            now.timestamp()
        ),

        "exp": int(
            (
                now
                + timedelta(seconds=30)
            ).timestamp()
        ),
    }

    token = jwt.encode(
        payload,
        private_key,
        algorithm=SSO_ALGORITHM,
    )

    return {
        "success": True,
        "temporary": True,
        "message": "Temporary Promot SSO token generated",
        "token": token,
        "payload": payload,
    }
