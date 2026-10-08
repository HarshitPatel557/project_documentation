import frappe
from frappe import _


@frappe.whitelist()
def search_mention_users(
    query: str = "",
    space: str | None = None,
    change_request: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """
    Search users for @ mentions and reviewer assignments in Frappe Wiki editor.
    Ranks members of the current project (derived from space or change_request) first,
    followed by non-project users.
    """
    if frappe.session.user == "Guest":
        return []

    query = (query or "").strip().lower()
    limit = int(limit or 20)

    if change_request and not space:
        space = frappe.db.get_value("Wiki Change Request", change_request, "wiki_space")

    project_name = None
    if space:
        project_name = frappe.db.get_value(
            "Project Documentation Project",
            {"wiki_space": space, "is_active": 1},
            "name",
        )

    project_members = []
    project_user_ids = set()

    if project_name:
        filters = {
            "project": project_name,
            "still_involved": 1,
        }
        or_filters = None
        if query:
            or_filters = {
                "employee_name": ["like", f"%{query}%"],
                "user": ["like", f"%{query}%"],
                "project_designation": ["like", f"%{query}%"],
            }

        mappings = frappe.get_all(
            "Project User Mapping",
            filters=filters,
            or_filters=or_filters,
            fields=["user", "employee_name", "project_designation"],
            order_by="employee_name asc",
            limit=limit,
        )

        for m in mappings:
            user_id = m.get("user")
            name = (m.get("employee_name") or "").strip()
            designation = (m.get("project_designation") or "").strip()

            if not user_id and not name:
                continue

            user_key = user_id or name
            if user_key in project_user_ids:
                continue
            project_user_ids.add(user_key)

            project_members.append(
                {
                    "id": user_key,
                    "value": user_id or user_key,
                    "label": name or user_id,
                    "designation": designation,
                    "group": "PROJECT MEMBERS",
                    "is_project_member": True,
                }
            )

    # Fetch other users from standard User table
    other_users = []
    user_fields = [
        "name",
        "full_name",
        "first_name",
        "last_name",
        "email",
        "custom_designation",
    ]
    user_filters = {
        "enabled": 1,
        "name": ["not in", list(project_user_ids) + ["Guest"]],
    }
    user_or_filters = None
    if query:
        user_or_filters = {
            "name": ["like", f"%{query}%"],
            "full_name": ["like", f"%{query}%"],
            "email": ["like", f"%{query}%"],
            "custom_designation": ["like", f"%{query}%"],
        }

    raw_users = frappe.get_all(
        "User",
        filters=user_filters,
        or_filters=user_or_filters,
        fields=user_fields,
        order_by="full_name asc",
        limit=limit,
    )

    for u in raw_users:
        user_id = u.get("name")
        full_name = (u.get("full_name") or f"{u.get('first_name') or ''} {u.get('last_name') or ''}").strip()
        email = (u.get("email") or "").strip()
        designation = (u.get("custom_designation") or "").strip()

        if not user_id:
            continue

        other_users.append(
            {
                "id": user_id,
                "value": user_id,
                "label": full_name or user_id,
                "designation": designation or email,
                "group": "OTHER USERS" if project_name else "USERS",
                "is_project_member": False,
            }
        )

    # Limit results while ensuring project members are ranked first
    max_pm = min(len(project_members), limit)
    remaining_limit = max(0, limit - max_pm)

    return project_members[:max_pm] + other_users[:remaining_limit]
