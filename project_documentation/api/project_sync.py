import requests
import frappe

API_URL = "https://chambal.mp.gov.in/promotapi/api/ErpNextAPI/get_Projectetails"
API_KEY_HEADER = "PROMOT-API-KEY-ERPNEXT"


def fetch_external_projects():
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
        frappe.throw(f"Failed to fetch projects from PROMOT API: {e}")
    try:
        data = response.json()
    except ValueError:
        frappe.throw("PROMOT Project API returned invalid JSON.")
    if not isinstance(data, list):
        frappe.throw(f"PROMOT Project API returned {type(data).__name__}; expected a list.")
    return data


def normalize_string(value):
    return "" if value is None else str(value).strip()


def normalize_int(value):
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def normalize_active(value):
    if isinstance(value, bool):
        return 1 if value else 0
    value = normalize_string(value).lower()
    if value in ("active", "1", "true", "yes"):
        return 1
    if value in ("inactive", "0", "false", "no"):
        return 0
    return None


def validate_project(project):
    external_project_id = normalize_int(project.get("Project_Id"))
    project_code = normalize_string(project.get("Project_Code"))
    project_name = normalize_string(project.get("Project_Name"))
    if external_project_id is None:
        return False, "Project_Id is missing or invalid."
    if not project_code:
        return False, "Project_Code is missing."
    if not project_name:
        return False, "Project_Name is missing."
    return True, None


def project_values(project):
    return {
        "external_project_id": normalize_int(project.get("Project_Id")),
        "project_code": normalize_string(project.get("Project_Code")),
        "project_name": normalize_string(project.get("Project_Name")),
        "vertical": normalize_string(project.get("Vertical")),
        "phase_name": normalize_string(project.get("PhaseName")),
        "oic_id": normalize_int(project.get("OIC_Id")),
        "oic_name": normalize_string(project.get("OIC_Name")),
        "is_active": normalize_active(project.get("isActive")),
    }


def find_existing_project(external_project_id):
    return frappe.db.get_value(
        "Project Documentation Project",
        {"external_project_id": external_project_id},
        "name",
    )


def find_project_by_code(project_code):
    return frappe.db.get_value(
        "Project Documentation Project",
        {"project_code": project_code},
        "name",
    )


def sync_projects(dry_run=True, limit=None):
    projects = fetch_external_projects()
    total_from_api = len(projects)
    if limit is not None:
        projects = projects[: int(limit)]

    result = {
        "total": total_from_api,
        "processed": len(projects),
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "failed": 0,
        "duplicate_external_id": 0,
        "duplicate_project_code": 0,
        "details": [],
    }

    seen_external_ids = set()
    seen_project_codes = set()

    for index, project in enumerate(projects, start=1):
        external_project_id = normalize_int(project.get("Project_Id"))
        project_code = normalize_string(project.get("Project_Code"))
        project_name = normalize_string(project.get("Project_Name"))
        try:
            valid, reason = validate_project(project)
            if not valid:
                result["skipped"] += 1
                result["details"].append({
                    "index": index,
                    "external_project_id": external_project_id,
                    "project_code": project_code,
                    "project_name": project_name,
                    "status": "SKIPPED",
                    "reason": reason,
                })
                continue

            if external_project_id in seen_external_ids:
                result["duplicate_external_id"] += 1
                result["skipped"] += 1
                result["details"].append({
                    "index": index,
                    "external_project_id": external_project_id,
                    "project_code": project_code,
                    "project_name": project_name,
                    "status": "SKIPPED",
                    "reason": f"Duplicate Project_Id {external_project_id} appeared more than once in the API response.",
                })
                continue
            seen_external_ids.add(external_project_id)

            if project_code in seen_project_codes:
                result["duplicate_project_code"] += 1
                result["skipped"] += 1
                result["details"].append({
                    "index": index,
                    "external_project_id": external_project_id,
                    "project_code": project_code,
                    "project_name": project_name,
                    "status": "SKIPPED",
                    "reason": f"Duplicate Project_Code '{project_code}' appeared more than once in the API response.",
                })
                continue
            seen_project_codes.add(project_code)

            values = project_values(project)
            existing_name = find_existing_project(external_project_id)

            if existing_name:
                doc = frappe.get_doc("Project Documentation Project", existing_name)
                code_owner = find_project_by_code(project_code)
                if code_owner and code_owner != doc.name:
                    result["duplicate_project_code"] += 1
                    result["skipped"] += 1
                    result["details"].append({
                        "index": index,
                        "external_project_id": external_project_id,
                        "project_code": project_code,
                        "project_name": project_name,
                        "status": "SKIPPED",
                        "frappe_project": doc.name,
                        "reason": f"Project_Code '{project_code}' already belongs to Frappe project {code_owner}.",
                    })
                    continue

                if dry_run:
                    result["updated"] += 1
                    result["details"].append({
                        "index": index,
                        "external_project_id": external_project_id,
                        "project_code": project_code,
                        "project_name": project_name,
                        "status": "WOULD UPDATE",
                        "frappe_project": doc.name,
                        "reason": "Existing project matched by external_project_id.",
                    })
                    continue

                for fieldname, value in values.items():
                    setattr(doc, fieldname, value)
                doc.save(ignore_permissions=True)
                if doc.is_active and not doc.wiki_space:
                    from project_documentation.project_documentation.project_hooks import (
                        initialize_project_documentation,
                    )
                    initialize_project_documentation(doc)
                frappe.db.commit()
                result["updated"] += 1
                result["details"].append({
                    "index": index,
                    "external_project_id": external_project_id,
                    "project_code": project_code,
                    "project_name": project_name,
                    "status": "UPDATED",
                    "frappe_project": doc.name,
                    "reason": "Updated by external_project_id.",
                })
            else:
                code_owner = find_project_by_code(project_code)
                if code_owner:
                    result["duplicate_project_code"] += 1
                    result["skipped"] += 1
                    result["details"].append({
                        "index": index,
                        "external_project_id": external_project_id,
                        "project_code": project_code,
                        "project_name": project_name,
                        "status": "SKIPPED",
                        "frappe_project": code_owner,
                        "reason": "Project_Code already exists but is linked to a different/no external project.",
                    })
                    continue

                if dry_run:
                    result["created"] += 1
                    result["details"].append({
                        "index": index,
                        "external_project_id": external_project_id,
                        "project_code": project_code,
                        "project_name": project_name,
                        "status": "WOULD CREATE",
                        "reason": "No existing project matched by external_project_id.",
                    })
                    continue

                doc = frappe.get_doc({
                    "doctype": "Project Documentation Project",
                    **values,
                })
                doc.insert(ignore_permissions=True)
                if doc.is_active and not doc.wiki_space:
                    from project_documentation.project_documentation.project_hooks import (
                        initialize_project_documentation,
                    )
                    initialize_project_documentation(doc)
                frappe.db.commit()
                result["created"] += 1
                result["details"].append({
                    "index": index,
                    "external_project_id": external_project_id,
                    "project_code": project_code,
                    "project_name": project_name,
                    "status": "CREATED",
                    "frappe_project": doc.name,
                    "reason": "Created from PROMOT Project API.",
                })

        except Exception as e:
            frappe.db.rollback()
            result["failed"] += 1
            result["details"].append({
                "index": index,
                "external_project_id": external_project_id,
                "project_code": project_code,
                "project_name": project_name,
                "status": "FAILED",
                "reason": str(e),
            })

    return result


@frappe.whitelist()
def dry_run_sync(limit=None):
    return sync_projects(dry_run=True, limit=limit)


@frappe.whitelist()
def run_sync(limit=None):
    return sync_projects(dry_run=False, limit=limit)
