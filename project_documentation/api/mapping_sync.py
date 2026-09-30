import hashlib
import requests
import frappe


API_URL = (
    "https://chambal.mp.gov.in/promotapi/api/ErpNextAPI/"
    "Get_Project_UserMapping"
)

API_KEY_HEADER = "PROMOT-API-KEY-ERPNEXT"


def fetch_external_mappings():
    """Fetch project-user mappings from the PROMOT API."""
    api_key = frappe.conf.get("promot_api_key")

    if not api_key:
        frappe.throw("promot_api_key is not configured in site_config.json")

    try:
        response = requests.get(
            API_URL,
            headers={API_KEY_HEADER: api_key},
            timeout=60,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        frappe.throw(f"Failed to fetch project mappings from PROMOT API: {e}")

    try:
        data = response.json()
    except ValueError:
        frappe.throw("PROMOT Mapping API returned invalid JSON.")

    if not isinstance(data, list):
        frappe.throw(
            f"PROMOT Mapping API returned {type(data).__name__}; "
            "expected a list."
        )

    return data


def normalize_string(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_int(value):
    if value in (None, ""):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_check(value):
    if isinstance(value, bool):
        return 1 if value else 0

    value = normalize_string(value).lower()

    if value in ("yes", "1", "true", "active"):
        return 1

    return 0


def normalize_date(value):
    """
    Normalize both PROMOT dates (DD/MM/YYYY) and Frappe
    date/datetime values to YYYY-MM-DD.
    """
    if value is None:
        return None

    from datetime import date, datetime

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, date):
        return value.isoformat()

    value = normalize_string(value)

    if not value:
        return None

    try:
        return datetime.strptime(value, "%d/%m/%Y").date().isoformat()
    except ValueError:
        return None


def make_fingerprint(mapping):
    """
    Create a deterministic identity for one assignment record.

    Project + Employee alone is NOT sufficient because an employee
    can have multiple historical assignments on the same project.
    """
    values = [
        normalize_int(mapping.get("Project_Id")),
        normalize_int(mapping.get("Employee_Id")),
        normalize_int(mapping.get("Role_Id")),
        normalize_date(mapping.get("Start_Date")),
        normalize_date(mapping.get("End_Date")),
        normalize_check(mapping.get("Still_Involved")),
        normalize_string(mapping.get("Project_Designation_Name")),
        normalize_string(mapping.get("Actual_Designation_Name")),
        normalize_string(mapping.get("Project_Current_Status")),
    ]

    raw = "|".join("" if value is None else str(value) for value in values)

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_mapping(mapping):
    """Validate minimum required mapping data."""

    project_id = normalize_int(mapping.get("Project_Id"))
    employee_id = normalize_int(mapping.get("Employee_Id"))

    if project_id is None:
        return False, "Project_Id is missing or invalid."

    if employee_id is None:
        return False, "Employee_Id is missing or invalid."

    return True, None


def find_project(project_id):
    """Find Project Documentation Project by PROMOT Project_Id."""
    return frappe.db.get_value(
        "Project Documentation Project",
        {"external_project_id": project_id},
        "name",
    )


def find_user(employee_id):
    """
    Find synchronized Frappe User by External Employee ID.

    User synchronization created:
        custom_external_employee_id
    """
    return frappe.db.get_value(
        "User",
        {"custom_external_employee_id": employee_id},
        "name",
    )


def mapping_values(mapping, project_name, user_name=None):
    """Map PROMOT mapping data into Project User Mapping."""

    return {
        "project": project_name,
        "employee_id": normalize_int(mapping.get("Employee_Id")),
        "employee_name": normalize_string(mapping.get("Employee_Name")),
        "user": user_name,
        "role_id": normalize_int(mapping.get("Role_Id")),
        "project_designation": normalize_string(
            mapping.get("Project_Designation_Name")
        ),
        "actual_designation": normalize_string(
            mapping.get("Actual_Designation_Name")
        ),
        "start_date": normalize_date(mapping.get("Start_Date")),
        "end_date": normalize_date(mapping.get("End_Date")),
        "still_involved": normalize_check(
            mapping.get("Still_Involved")
        ),
        "project_current_status": normalize_string(
            mapping.get("Project_Current_Status")
        ),
    }


def sync_mappings(dry_run=True, limit=None):
    """
    Sync PROMOT project-user mappings.

    Every distinct assignment is preserved.

    Matching:
        deterministic fingerprint of the assignment data.

    Missing Frappe User:
        mapping is still imported; User field remains empty.

    Args:
        dry_run: True = preview only, no database changes.
        limit: Optional number of API rows to process.
    """

    mappings = fetch_external_mappings()

    total_from_api = len(mappings)

    if limit is not None:
        mappings = mappings[: int(limit)]

    result = {
        "total": total_from_api,
        "processed": len(mappings),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "missing_project": 0,
        "missing_user": 0,
        "duplicate_api_rows": 0,
        "details": [],
    }

    seen_fingerprints = set()

    # Cache lookups because thousands of mappings may reference
    # the same projects and employees.
    project_cache = {}
    user_cache = {}

    for index, mapping in enumerate(mappings, start=1):

        project_id = normalize_int(mapping.get("Project_Id"))
        employee_id = normalize_int(mapping.get("Employee_Id"))
        employee_name = normalize_string(mapping.get("Employee_Name"))

        try:
            valid, reason = validate_mapping(mapping)

            if not valid:
                result["skipped"] += 1

                result["details"].append({
                    "index": index,
                    "project_id": project_id,
                    "employee_id": employee_id,
                    "employee_name": employee_name,
                    "status": "SKIPPED",
                    "reason": reason,
                })

                continue

            fingerprint = make_fingerprint(mapping)

            # Duplicate rows that are completely identical according
            # to our assignment fingerprint.
            if fingerprint in seen_fingerprints:
                result["duplicate_api_rows"] += 1
                result["skipped"] += 1

                result["details"].append({
                    "index": index,
                    "project_id": project_id,
                    "employee_id": employee_id,
                    "employee_name": employee_name,
                    "status": "SKIPPED",
                    "reason": (
                        "Duplicate assignment row appeared more than "
                        "once in the API response."
                    ),
                })

                continue

            seen_fingerprints.add(fingerprint)

            # -------------------------
            # Project lookup
            # -------------------------

            if project_id not in project_cache:
                project_cache[project_id] = find_project(project_id)

            project_name = project_cache[project_id]

            if not project_name:
                result["missing_project"] += 1
                result["skipped"] += 1

                result["details"].append({
                    "index": index,
                    "project_id": project_id,
                    "employee_id": employee_id,
                    "employee_name": employee_name,
                    "status": "SKIPPED",
                    "reason": (
                        f"No Project Documentation Project found for "
                        f"external_project_id {project_id}."
                    ),
                })

                continue

            # -------------------------
            # User lookup
            # -------------------------

            if employee_id not in user_cache:
                user_cache[employee_id] = find_user(employee_id)

            user_name = user_cache[employee_id]

            if not user_name:
                result["missing_user"] += 1

            values = mapping_values(
                mapping,
                project_name,
                user_name,
            )

            # -------------------------
            # Find existing mapping
            # -------------------------
            #
            # Since the DocType intentionally has no unique database
            # field for this assignment, we search its fields and
            # compare the deterministic fingerprint.

            existing_mapping = None

            candidates = frappe.get_all(
                "Project User Mapping",
                filters={
                    "project": project_name,
                    "employee_id": employee_id,
                },
                fields=[
                    "name",
                    "role_id",
                    "project_designation",
                    "actual_designation",
                    "start_date",
                    "end_date",
                    "still_involved",
                    "project_current_status",
                ],
            )

            for candidate in candidates:
                candidate_data = {
                    "Project_Id": project_id,
                    "Employee_Id": employee_id,
                    "Role_Id": candidate.role_id,
                    "Start_Date": candidate.start_date,
                    "End_Date": candidate.end_date,
                    "Still_Involved": candidate.still_involved,
                    "Project_Designation_Name": candidate.project_designation,
                    "Actual_Designation_Name": candidate.actual_designation,
                    "Project_Current_Status": candidate.project_current_status,
                }

                if make_fingerprint(candidate_data) == fingerprint:
                    existing_mapping = candidate.name
                    break

            # -------------------------
            # Existing mapping
            # -------------------------

            if existing_mapping:

                if dry_run:
                    result["updated"] += 1

                    result["details"].append({
                        "index": index,
                        "project_id": project_id,
                        "employee_id": employee_id,
                        "employee_name": employee_name,
                        "status": "WOULD UPDATE",
                        "mapping": existing_mapping,
                        "user": user_name,
                    })

                    continue

                doc = frappe.get_doc(
                    "Project User Mapping",
                    existing_mapping,
                )

                for fieldname, value in values.items():
                    setattr(doc, fieldname, value)

                doc.save(ignore_permissions=True)
                frappe.db.commit()

                result["updated"] += 1

                result["details"].append({
                    "index": index,
                    "project_id": project_id,
                    "employee_id": employee_id,
                    "employee_name": employee_name,
                    "status": "UPDATED",
                    "mapping": doc.name,
                    "user": user_name,
                })

            # -------------------------
            # New mapping
            # -------------------------

            else:

                if dry_run:
                    result["created"] += 1

                    result["details"].append({
                        "index": index,
                        "project_id": project_id,
                        "employee_id": employee_id,
                        "employee_name": employee_name,
                        "status": "WOULD CREATE",
                        "user": user_name,
                    })

                    continue

                doc = frappe.get_doc({
                    "doctype": "Project User Mapping",
                    **values,
                })

                doc.insert(ignore_permissions=True)
                frappe.db.commit()

                result["created"] += 1

                result["details"].append({
                    "index": index,
                    "project_id": project_id,
                    "employee_id": employee_id,
                    "employee_name": employee_name,
                    "status": "CREATED",
                    "mapping": doc.name,
                    "user": user_name,
                })

        except Exception as e:
            frappe.db.rollback()

            result["failed"] += 1

            result["details"].append({
                "index": index,
                "project_id": project_id,
                "employee_id": employee_id,
                "employee_name": employee_name,
                "status": "FAILED",
                "reason": str(e),
            })

    return result


@frappe.whitelist()
def dry_run_sync(limit=None):
    """Preview mapping synchronization without database changes."""
    return sync_mappings(dry_run=True, limit=limit)


@frappe.whitelist()
def run_sync(limit=None):
    """Run actual mapping synchronization."""
    return sync_mappings(dry_run=False, limit=limit)