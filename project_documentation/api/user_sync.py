import requests
import frappe


API_URL = "promot_api_url"
API_KEY = "promot_api_key"
API_HEADER = "PROMOT-API-KEY-ERPNEXT"


def fetch_external_users():
    """Fetch users from the external PROMOT API."""

    url = frappe.conf.get(API_URL)
    api_key = frappe.conf.get(API_KEY)

    if not url:
        frappe.throw("PROMOT API URL is not configured.")

    if not api_key:
        frappe.throw("PROMOT API key is not configured.")

    response = requests.get(
        url,
        headers={
            API_HEADER: api_key,
            "Accept": "application/json",
        },
        timeout=30,
    )

    response.raise_for_status()

    users = response.json()

    if not isinstance(users, list):
        frappe.throw(
            "PROMOT API returned an unexpected response format."
        )

    return users


def normalize_email(value):
    if not value:
        return ""

    return str(value).strip().lower()


def normalize_external_id(value):
    if not value:
        return ""

    return str(value).strip()


def validate_user(user):
    errors = []

    if not user.get("UserId"):
        errors.append("Missing UserId")

    if not user.get("Employee_Id"):
        errors.append("Missing Employee_Id")

    if not user.get("User_Name"):
        errors.append("Missing User_Name")

    if not user.get("Email"):
        errors.append("Missing Email")

    if not user.get("Employee_Name"):
        errors.append("Missing Employee_Name")

    return errors


def sync_users(dry_run=True, limit=None):
    """
    Synchronize external PROMOT users with Frappe User.

    dry_run=True:
        No database changes.

    dry_run=False:
        Create/update users.

    limit:
        Optional number of API users to process.
        Useful for controlled testing.
    """

    users = fetch_external_users()

    if limit:
        users = users[:limit]

    result = {
        "total": len(users),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "missing_email": 0,
        "duplicate_email": 0,
        "duplicate_external_id": 0,
        "details": [],
    }

    # ---------------------------------------------------------
    # Build duplicate indexes from API data
    # ---------------------------------------------------------

    external_id_map = {}
    email_map = {}

    for user in users:
        external_id = normalize_external_id(
            user.get("UserId")
        )

        email = normalize_email(
            user.get("Email")
        )

        if external_id:
            external_id_map.setdefault(
                external_id,
                []
            ).append(user)

        if email:
            email_map.setdefault(
                email,
                []
            ).append(user)

    processed_external_ids = set()

    # ---------------------------------------------------------
    # Frappe User creation throttle
    #
    # Frappe throttles User creation unless in_import is True.
    # Keep this flag enabled for the ENTIRE actual sync loop.
    # ---------------------------------------------------------

    previous_in_import = getattr(
        frappe.flags,
        "in_import",
        False,
    )

    # Frappe User.on_update() enqueues create_contact after commit.
    # During a bulk import this can flood the background queue and make
    # frappe.db.commit() raise "Too many queued background jobs".
    #
    # We suppress ONLY this specific contact job for the duration of this
    # sync. No Frappe core files are modified, and the original enqueue
    # function is restored in finally.
    original_enqueue = frappe.enqueue

    def sync_enqueue(method, *args, **kwargs):
        if method == "frappe.core.doctype.user.user.create_contact":
            return None
        return original_enqueue(method, *args, **kwargs)

    if not dry_run:
        frappe.flags.in_import = True
        frappe.enqueue = sync_enqueue

    try:

        # -----------------------------------------------------
        # Process users individually
        # -----------------------------------------------------

        for user in users:

            external_id = normalize_external_id(
                user.get("UserId")
            )

            email = normalize_email(
                user.get("Email")
            )

            employee_id = user.get("Employee_Id")
            employee_name = user.get("Employee_Name")

            try:

                # -------------------------------------------------
                # Validate
                # -------------------------------------------------

                validation_errors = validate_user(user)

                if validation_errors:

                    result["skipped"] += 1

                    if "Missing Email" in validation_errors:
                        result["missing_email"] += 1

                    result["details"].append({
                        "status": "SKIPPED",
                        "external_id": external_id,
                        "employee_id": employee_id,
                        "email": email,
                        "name": employee_name,
                        "reason": ", ".join(
                            validation_errors
                        ),
                    })

                    continue

                # -------------------------------------------------
                # Duplicate external ID
                # -------------------------------------------------

                if external_id in processed_external_ids:

                    result["skipped"] += 1
                    result["duplicate_external_id"] += 1

                    result["details"].append({
                        "status": "SKIPPED",
                        "external_id": external_id,
                        "employee_id": employee_id,
                        "email": email,
                        "name": employee_name,
                        "reason": (
                            "Duplicate UserId in external API."
                        ),
                    })

                    continue

                processed_external_ids.add(external_id)

                # -------------------------------------------------
                # Find existing User by external UserId
                # -------------------------------------------------

                existing_user = frappe.db.get_value(
                    "User",
                    {
                        "custom_external_user_id": external_id
                    },
                    "name",
                )

                # -------------------------------------------------
                # UPDATE existing user
                # -------------------------------------------------

                if existing_user:

                    if dry_run:

                        result["updated"] += 1

                        result["details"].append({
                            "status": "WOULD UPDATE",
                            "external_id": external_id,
                            "employee_id": employee_id,
                            "email": email,
                            "name": employee_name,
                            "frappe_user": existing_user,
                        })

                    else:

                        doc = frappe.get_doc(
                            "User",
                            existing_user,
                        )

                        # Do NOT change doc.email.
                        # Email is the Frappe login identifier.

                        doc.username = user.get(
                            "User_Name"
                        )

                        doc.first_name = employee_name

                        doc.mobile_no = user.get(
                            "Phone"
                        )

                        doc.enabled = (
                            1
                            if str(
                                user.get(
                                    "Active_Status",
                                    ""
                                )
                            ).strip().lower()
                            == "active"
                            else 0
                        )

                        doc.custom_external_user_id = (
                            external_id
                        )

                        doc.custom_external_employee_id = (
                            employee_id
                        )

                        doc.custom_designation = (
                            user.get("Designation")
                            or ""
                        )

                        doc.save(
                            ignore_permissions=True
                        )

                        frappe.db.commit()

                        # Increment ONLY after successful save.
                        result["updated"] += 1

                        result["details"].append({
                            "status": "UPDATED",
                            "external_id": external_id,
                            "employee_id": employee_id,
                            "email": email,
                            "name": employee_name,
                            "frappe_user": existing_user,
                        })

                    continue

                # -------------------------------------------------
                # Check whether email already belongs to Frappe
                # -------------------------------------------------

                frappe_user_by_email = frappe.db.get_value(
                    "User",
                    {
                        "name": email
                    },
                    "name",
                )

                if frappe_user_by_email:

                    result["skipped"] += 1

                    result["details"].append({
                        "status": "SKIPPED",
                        "external_id": external_id,
                        "employee_id": employee_id,
                        "email": email,
                        "name": employee_name,
                        "frappe_user": frappe_user_by_email,
                        "reason": (
                            "Email already belongs to a Frappe "
                            "User with a different external ID."
                        ),
                    })

                    continue

                # -------------------------------------------------
                # Duplicate email in API
                # -------------------------------------------------

                if len(email_map.get(email, [])) > 1:

                    result["skipped"] += 1
                    result["duplicate_email"] += 1

                    result["details"].append({
                        "status": "SKIPPED",
                        "external_id": external_id,
                        "employee_id": employee_id,
                        "email": email,
                        "name": employee_name,
                        "reason": (
                            "Duplicate email in external API. "
                            "Manual review required."
                        ),
                    })

                    continue

                # -------------------------------------------------
                # Duplicate mobile number
                #
                # Only check this for CREATE. Existing users were
                # already matched by external UserId above and should
                # be allowed to retain/update their existing mobile.
                # -------------------------------------------------

                mobile_no = user.get("Phone")

                if mobile_no:
                    frappe_user_by_mobile = frappe.db.get_value(
                        "User",
                        {"mobile_no": mobile_no},
                        "name",
                    )

                    if frappe_user_by_mobile:
                        result["skipped"] += 1

                        result["details"].append({
                            "status": "SKIPPED",
                            "external_id": external_id,
                            "employee_id": employee_id,
                            "email": email,
                            "name": employee_name,
                            "frappe_user": frappe_user_by_mobile,
                            "reason": (
                                f"Mobile number {mobile_no} already belongs "
                                f"to Frappe User {frappe_user_by_mobile}."
                            ),
                        })

                        continue

                # -------------------------------------------------
                # CREATE
                # -------------------------------------------------

                if dry_run:

                    result["created"] += 1

                    result["details"].append({
                        "status": "WOULD CREATE",
                        "external_id": external_id,
                        "employee_id": employee_id,
                        "email": email,
                        "name": employee_name,
                    })

                    continue

                # -------------------------------------------------
                # Actual User creation
                # -------------------------------------------------

                doc = frappe.get_doc({
                    "doctype": "User",

                    "email": email,

                    "username": user.get(
                        "User_Name"
                    ),

                    "first_name": employee_name,

                    "mobile_no": user.get(
                        "Phone"
                    ),

                    "enabled": (
                        1
                        if str(
                            user.get(
                                "Active_Status",
                                ""
                            )
                        ).strip().lower()
                        == "active"
                        else 0
                    ),

                    "custom_external_user_id": external_id,

                    "custom_external_employee_id": (
                        employee_id
                    ),

                    "custom_designation": (
                        user.get("Designation")
                        or ""
                    ),

                    "send_welcome_email": 0,
                })

                doc.insert(
                    ignore_permissions=True
                )

                frappe.db.commit()

                # Increment ONLY after successful insert.
                result["created"] += 1

                result["details"].append({
                    "status": "CREATED",
                    "external_id": external_id,
                    "employee_id": employee_id,
                    "email": email,
                    "name": employee_name,
                    "frappe_user": doc.name,
                })

            except Exception as e:

                # Make sure a failed transaction does not
                # affect the next user.

                frappe.db.rollback()

                result["failed"] += 1

                result["details"].append({
                    "status": "FAILED",
                    "external_id": external_id,
                    "employee_id": employee_id,
                    "email": email,
                    "name": employee_name,
                    "reason": str(e),
                })

    finally:

        # Always restore the original Frappe enqueue function and flag.
        if not dry_run:
            frappe.enqueue = original_enqueue

        frappe.flags.in_import = previous_in_import

    return result


@frappe.whitelist()
def dry_run_sync():
    """Preview synchronization without database changes."""

    return sync_users(dry_run=True)


@frappe.whitelist()
def run_sync():
    """Run actual synchronization."""

    return sync_users(dry_run=False)