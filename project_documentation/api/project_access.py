import json
import re
from urllib.parse import quote

import frappe

ACCESS_DOCTYPE = "Project Documentation Access"
PM_DESIGNATION = "PM"
WIKI_SPACE_LIST_URL = "/wiki-app/spaces/"

# Wiki roles are owned by the Wiki app. We assign them from this app only
# after validating project membership/access. Marker roles let our permission
# hooks distinguish roles granted by Project Documentation from unrelated
# Wiki access a user may already have.
WIKI_MANAGER_ROLE = "Wiki Manager"
WIKI_APPROVER_ROLE = "Wiki Approver"
WIKI_USER_ROLE = "Wiki User"
# Project Documentation roles are the native Frappe roles used for the
# documentation access levels. They deliberately do NOT inherit Wiki Manager.
PD_MANAGER_ROLE = "Project Documentation Manager"
PD_WRITER_ROLE = "Project Documentation Writer"
PD_READER_ROLE = "Project Documentation Reader"

# Kept as aliases for compatibility with data created by earlier app versions.
PD_MANAGER_MARKER_ROLE = PD_MANAGER_ROLE
PD_WRITER_MARKER_ROLE = PD_WRITER_ROLE
PD_READER_MARKER_ROLE = PD_READER_ROLE


def _space_url(space_name):
    if not space_name:
        return None
    return f"{WIKI_SPACE_LIST_URL}{quote(str(space_name), safe='')}"


def _current_user(user=None):
    user = user or frappe.session.user
    if not user or user == "Guest":
        frappe.throw("Login is required.", frappe.PermissionError)
    return user


def _active_pm_projects(user=None):
    user = _current_user(user)

    rows = frappe.get_all(
        "Project User Mapping",
        filters={
            "user": user,
            "project_designation": PM_DESIGNATION,
            "still_involved": 1,
        },
        fields=["project"],
        distinct=True,
    )

    return {row.project for row in rows if row.project}


def _assert_pm_for_project(project, user=None):
    user = _current_user(user)

    if not project:
        frappe.throw("Project is required.")

    if project not in _active_pm_projects(user):
        frappe.throw(
            "You are not the active PM of this project.",
            frappe.PermissionError,
        )

    project_doc = frappe.get_doc("Project Documentation Project", project)

    if not project_doc.is_active:
        frappe.throw(
            "This project is inactive.",
            frappe.PermissionError,
        )

    return project_doc


def _project_member(project, user):
    """Return an active project mapping for a real Frappe user."""
    return frappe.db.get_value(
        "Project User Mapping",
        {
            "project": project,
            "user": user,
            "still_involved": 1,
        },
        [
            "name",
            "user",
            "employee_name",
            "project_designation",
            "actual_designation",
            "employee_id",
        ],
        as_dict=True,
    )


def _access_level(project, user):
    value = frappe.db.get_value(
        ACCESS_DOCTYPE,
        {
            "project": project,
            "user": user,
        },
        "access_level",
    )
    return value or None


def _ensure_role(role_name):
    """Ensure a non-desk documentation role exists."""
    if not frappe.db.exists("Role", role_name):
        role = frappe.get_doc(
            {
                "doctype": "Role",
                "role_name": role_name,
                "desk_access": 0,
            }
        )
        role.insert(ignore_permissions=True)


def _ensure_role_permission(doctype, role, *, read=0, write=0, create=0, delete=0, share=0):
    """Create/update the minimum native DocType permission needed by a PD role.

    Permission definitions are application-level configuration, not something
    the logged-in PM should need to own.  Frappe's permission helpers also
    operate on Custom DocPerm and ``add_permission`` displays an informational
    message when a matching Custom DocPerm already exists.  Check both the
    standard and custom permission tables first and run the mutation with
    ``ignore_permissions`` so PM page loads do not produce duplicate-rule
    popups or fail with ``Not permitted``.
    """
    from frappe.permissions import add_permission, update_permission_property

    previous_ignore_permissions = getattr(
        frappe.flags, "ignore_permissions", False
    )
    frappe.flags.ignore_permissions = True

    try:
        permission_filters = {
            "parent": doctype,
            "role": role,
            "permlevel": 0,
        }

        custom_exists = frappe.db.exists(
            "Custom DocPerm",
            {**permission_filters, "if_owner": 0},
        )
        standard_exists = frappe.db.exists(
            "DocPerm",
            permission_filters,
        )

        # add_permission() checks Custom DocPerm, so checking only DocPerm
        # causes Frappe to emit the "rule already exists" popup on every
        # project-documentation page load.
        if not custom_exists and not standard_exists:
            add_permission(doctype, role, 0)

        for ptype, value in {
            "read": read,
            "write": write,
            "create": create,
            "delete": delete,
            "share": share,
        }.items():
            update_permission_property(
                doctype,
                role,
                0,
                ptype,
                int(bool(value)),
            )

        frappe.clear_cache(doctype=doctype)
    finally:
        frappe.flags.ignore_permissions = previous_ignore_permissions


def _ensure_documentation_role_permissions():
    """Set native Wiki permissions for the three PD access roles.

    This is intentionally done from project_documentation and never edits the
    Wiki application's source. Read users receive native read permission;
    Write users receive read/write/create permission; only PMs receive the
    native Wiki Manager role needed for Wiki's review/merge controls.
    """
    for role in (PD_MANAGER_ROLE, PD_WRITER_ROLE, PD_READER_ROLE, WIKI_USER_ROLE):
        _ensure_role(role)

    # Reader: can enter/list project Wiki Spaces and read Wiki Documents & Settings.
    _ensure_role_permission("Wiki Space", PD_READER_ROLE, read=1)
    _ensure_role_permission("Wiki Document", PD_READER_ROLE, read=1)
    _ensure_role_permission("Wiki Settings", PD_READER_ROLE, read=1)

    # Writer: can read and edit documentation, revisions, items and blobs, but has no Wiki Manager/approval role.
    _ensure_role_permission("Wiki Space", PD_WRITER_ROLE, read=1, write=1)
    _ensure_role_permission("Wiki Document", PD_WRITER_ROLE, read=1, write=1, create=1)
    _ensure_role_permission("Wiki Change Request", PD_WRITER_ROLE, read=1, write=1, create=1)
    _ensure_role_permission("Wiki Revision", PD_WRITER_ROLE, read=1, write=1, create=1)
    _ensure_role_permission("Wiki Revision Item", PD_WRITER_ROLE, read=1, write=1, create=1)
    _ensure_role_permission("Wiki Content Blob", PD_WRITER_ROLE, read=1, write=1, create=1)
    _ensure_role_permission("Wiki Settings", PD_WRITER_ROLE, read=1)

    # PM: full documentation DocType rights; Wiki Manager is separately assigned
    # below so the Wiki's own approval/merge UI remains PM-only.
    _ensure_role_permission("Wiki Space", PD_MANAGER_ROLE, read=1, write=1, create=1, delete=1, share=1)
    _ensure_role_permission("Wiki Document", PD_MANAGER_ROLE, read=1, write=1, create=1, delete=1, share=1)
    _ensure_role_permission("Wiki Change Request", PD_MANAGER_ROLE, read=1, write=1, create=1, delete=1, share=1)
    _ensure_role_permission("Wiki Revision", PD_MANAGER_ROLE, read=1, write=1, create=1, delete=1, share=1)
    _ensure_role_permission("Wiki Revision Item", PD_MANAGER_ROLE, read=1, write=1, create=1, delete=1, share=1)
    _ensure_role_permission("Wiki Content Blob", PD_MANAGER_ROLE, read=1, write=1, create=1, delete=1, share=1)
    _ensure_role_permission("Wiki Settings", PD_MANAGER_ROLE, read=1)

    # Base read permissions for Wiki User and All so logged-in users pass DocPerm checks
    # (Fine-grained access is enforced by wiki_*_has_permission & query conditions)
    _ensure_role_permission("Wiki Space", WIKI_USER_ROLE, read=1)
    _ensure_role_permission("Wiki Document", WIKI_USER_ROLE, read=1)
    _ensure_role_permission("Wiki Space", "All", read=1)
    _ensure_role_permission("Wiki Document", "All", read=1)
    _ensure_role_permission("Wiki Change Request", "All", read=1)

def _user_roles(user):
    return set(frappe.get_roles(user))


def _clear_user_role_cache(user):
    """Clear cached roles after direct Has Role changes."""
    try:
        frappe.cache.hdel("roles", user)
    except Exception:
        pass
    try:
        frappe.cache.hdel("user_roles", user)
    except Exception:
        pass
    try:
        frappe.clear_cache(user=user)
    except Exception:
        pass


def _add_user_roles(user, *roles):
    """
    Assign native/marker roles without requiring the logged-in PM to have
    Desk write permission on the target User document.

    We intentionally write the Has Role child records directly with
    ignore_permissions=True after this app has already validated the
    project-level authorization. Using User.add_roles() calls User.save(),
    which performs a normal User write-permission check and fails for PMs.
    """
    roles = [role for role in roles if role]
    if not roles:
        return

    for role in roles:
        if not frappe.db.exists("Role", role):
            frappe.throw(f"Required role '{role}' is not available.")

    for role in roles:
        exists = frappe.db.exists(
            "Has Role",
            {
                "parent": user,
                "parenttype": "User",
                "parentfield": "roles",
                "role": role,
            },
        )
        if exists:
            continue

        frappe.get_doc(
            {
                "doctype": "Has Role",
                "parent": user,
                "parenttype": "User",
                "parentfield": "roles",
                "role": role,
            }
        ).insert(ignore_permissions=True)

    _clear_user_role_cache(user)


def _remove_user_roles(user, *roles):
    """Remove only the roles managed by Project Documentation."""
    roles = [role for role in roles if role]
    if not roles:
        return

    for role in roles:
        frappe.db.delete(
            "Has Role",
            {
                "parent": user,
                "parenttype": "User",
                "parentfield": "roles",
                "role": role,
            },
        )

    _clear_user_role_cache(user)


def _sync_user_wiki_roles(user):
    """Synchronize a user's project-documentation roles without User.save().

    DocType permissions are installed by the app migration patch and are not
    recreated/checked during ordinary user synchronization.
    """
    user = _current_user(user)

    pm_projects = _active_pm_projects(user)
    is_pm = bool(pm_projects)

    access_rows = frappe.get_all(
        ACCESS_DOCTYPE,
        filters={"user": user},
        fields=["project", "access_level"],
    )
    # Only resolve the projects this user has explicit access to. The old
    # implementation loaded every active project on every role sync, which
    # became expensive as the project table grew.
    access_project_names = [row.project for row in access_rows if row.project]
    if access_project_names:
        active_projects = set(
            frappe.get_all(
                "Project Documentation Project",
                filters={
                    "name": ["in", access_project_names],
                    "is_active": 1,
                },
                pluck="name",
            )
        )
        access_rows = [row for row in access_rows if row.project in active_projects]
    else:
        access_rows = []

    is_involved_member = bool(
        frappe.db.exists(
            "Project User Mapping",
            {"user": user, "still_involved": 1},
        )
    )

    roles = _user_roles(user)
    if is_pm:
        _add_user_roles(user, WIKI_MANAGER_ROLE, PD_MANAGER_ROLE, WIKI_USER_ROLE)
        _remove_user_roles(user, WIKI_APPROVER_ROLE, PD_WRITER_ROLE, PD_READER_ROLE)
    elif any(row.access_level == "Write" for row in access_rows):
        _remove_user_roles(user, WIKI_MANAGER_ROLE, WIKI_APPROVER_ROLE, PD_MANAGER_ROLE)
        _add_user_roles(user, PD_WRITER_ROLE, WIKI_USER_ROLE)
        _remove_user_roles(user, PD_READER_ROLE)
    elif any(row.access_level == "Read" for row in access_rows) or is_involved_member:
        _remove_user_roles(user, WIKI_MANAGER_ROLE, WIKI_APPROVER_ROLE, PD_MANAGER_ROLE, PD_WRITER_ROLE)
        _add_user_roles(user, PD_READER_ROLE, WIKI_USER_ROLE)
    else:
        _remove_user_roles(user, WIKI_MANAGER_ROLE, WIKI_APPROVER_ROLE, PD_MANAGER_ROLE, PD_WRITER_ROLE, PD_READER_ROLE)
        _add_user_roles(user, WIKI_USER_ROLE)


def ensure_pm_wiki_access(user=None):
    """Public helper used during PM login/page entry to repair Wiki roles."""
    user = _current_user(user)
    if _active_pm_projects(user):
        _sync_user_wiki_roles(user)
    return user


def _is_project_documentation_managed_user(user):
    roles = _user_roles(user)
    return bool(
        roles.intersection(
            {
                PD_MANAGER_MARKER_ROLE,
                PD_WRITER_MARKER_ROLE,
                PD_READER_MARKER_ROLE,
            }
        )
    )


def get_my_pm_projects():
    """Return active projects for which the current user is an active PM.

    This is a read-only page-load API. Role/permission synchronization is
    deliberately not performed here because it is configuration/mutation work
    and makes the PM dashboard slow. Role synchronization happens when access
    is changed and during PM authentication/provisioning.
    """
    user = _current_user()

    projects = _active_pm_projects(user)
    if not projects:
        return {
            "user": user,
            "is_pm": False,
            "projects": [],
        }

    rows = frappe.get_all(
        "Project Documentation Project",
        filters={
            "name": ["in", list(projects)],
            "is_active": 1,
        },
        fields=[
            "name",
            "project_code",
            "project_name",
            "external_project_id",
            "vertical",
            "phase_name",
            "wiki_space",
        ],
        order_by="project_name asc",
    )

    # Fetch all Wiki Space routes in one query instead of one query per
    # project. The PM dashboard should remain a lightweight list endpoint.
    space_names = [row.wiki_space for row in rows if row.wiki_space]
    routes_by_space = {}
    if space_names:
        space_rows = frappe.get_all(
            "Wiki Space",
            filters={"name": ["in", space_names]},
            fields=["name", "route"],
        )
        routes_by_space = {row.name: row.route for row in space_rows}

    for row in rows:
        row["route"] = routes_by_space.get(row.wiki_space)
        row["space_id"] = row.wiki_space or None
        row["space_url"] = _space_url(row.wiki_space)

    return {
        "user": user,
        "is_pm": True,
        "projects": rows,
    }


def get_pm_project(project):
    """Return project details for an active PM without loading its members."""
    project_doc = _assert_pm_for_project(project)

    route = None
    if project_doc.wiki_space:
        route = frappe.db.get_value(
            "Wiki Space",
            project_doc.wiki_space,
            "route",
        )

    return {
        "name": project_doc.name,
        "project_code": project_doc.project_code,
        "project_name": project_doc.project_name,
        "external_project_id": project_doc.external_project_id,
        "vertical": project_doc.vertical,
        "phase_name": project_doc.phase_name,
        "oic_id": project_doc.oic_id,
        "oic_name": project_doc.oic_name,
        "is_active": project_doc.is_active,
        "wiki_space": project_doc.wiki_space,
        "route": route,
        "space_id": project_doc.wiki_space or None,
        "space_url": _space_url(project_doc.wiki_space),
    }


def get_project_members(project):
    """Return only active Frappe users who are members of a PM's project."""
    _assert_pm_for_project(project)

    rows = frappe.get_all(
        "Project User Mapping",
        filters={
            "project": project,
            "still_involved": 1,
            "user": ["is", "set"],
        },
        fields=[
            "user",
            "employee_id",
            "employee_name",
            "project_designation",
            "actual_designation",
        ],
        order_by="employee_name asc",
    )

    user_names = [row.user for row in rows if row.user]
    access_by_user = {}

    if user_names:
        access_rows = frappe.get_all(
            ACCESS_DOCTYPE,
            filters={
                "project": project,
                "user": ["in", user_names],
            },
            fields=["user", "access_level"],
        )
        access_by_user = {
            row.user: row.access_level
            for row in access_rows
        }

    for row in rows:
        row["access_level"] = access_by_user.get(row.user)

    return rows


def get_project_access(project):
    """Return the project's explicit documentation access assignments."""
    _assert_pm_for_project(project)

    rows = frappe.get_all(
        ACCESS_DOCTYPE,
        filters={"project": project},
        fields=["name", "user", "access_level", "modified"],
        order_by="modified desc",
    )

    return rows


def create_wiki_space(project):
    """
    Create one Wiki Space for a PM's project and link it to
    Project Documentation Project.wiki_space.

    No documentation folders/groups are created here.
    Wiki's own Wiki Space creation behavior is left untouched.
    """
    project_doc = _assert_pm_for_project(project)
    _sync_user_wiki_roles(frappe.session.user)

    if project_doc.wiki_space:
        space = frappe.get_doc("Wiki Space", project_doc.wiki_space)
        return {
            "status": "ALREADY_EXISTS",
            "project": project_doc.name,
            "wiki_space": space.name,
            "route": space.route,
            "space_name": space.space_name,
            "space_id": space.name,
            "space_url": _space_url(space.name),
        }

    project_code = (project_doc.project_code or "").strip()
    project_name = (project_doc.project_name or "").strip()

    if not project_code:
        frappe.throw("Project Code is required before creating the Wiki Space.")

    if not project_name:
        frappe.throw("Project Name is required before creating the Wiki Space.")

    route = re.sub(r"[^a-z0-9]+", "-", project_code.lower()).strip("-")

    if not route:
        frappe.throw("A valid Wiki Space route could not be generated from the Project Code.")

    existing_space = frappe.db.get_value(
        "Wiki Space",
        {"route": route},
        ["name", "space_name", "route"],
        as_dict=True,
    )

    if existing_space:
        frappe.throw(
            f"Wiki Space route '{route}' already exists. "
            "The project was not linked to it automatically."
        )

    space = frappe.get_doc(
        {
            "doctype": "Wiki Space",
            "space_name": project_name,
            "route": route,
        }
    )
    # The PM has already been authorized by project membership. Wiki Space is
    # a Wiki-owned DocType, and Wiki Space creation can create related Wiki
    # Documents from Wiki hooks. Passing ignore_permissions=True only to the
    # outer insert does not necessarily propagate to those nested inserts.
    # Temporarily enable Frappe's global ignore-permissions flag for the whole
    # initialization transaction so the Wiki app can create its own related
    # records, without changing the Wiki app or granting the PM a global Wiki
    # role.
    previous_ignore_permissions = getattr(
        frappe.flags,
        "ignore_permissions",
        False,
    )
    # Wiki Space.before_insert() creates related Wiki records with normal
    # insert() calls. Enable Frappe's global ignore-permissions flag for this
    # single provisioning transaction so those nested inserts are allowed.
    # The current logged-in user is intentionally preserved; impersonating
    # Administrator with frappe.set_user() would overwrite the real session
    # SID and corrupt the browser session.
    frappe.flags.ignore_permissions = True
    try:
        space.insert(ignore_permissions=True)
    finally:
        frappe.flags.ignore_permissions = previous_ignore_permissions

    frappe.db.set_value(
        "Project Documentation Project",
        project_doc.name,
        "wiki_space",
        space.name,
        update_modified=False,
    )
    frappe.db.commit()

    return {
        "status": "CREATED",
        "project": project_doc.name,
        "wiki_space": space.name,
        "route": space.route,
        "space_name": space.space_name,
        "space_id": space.name,
        "space_url": _space_url(space.name),
    }


def _validate_access_user(project, user):
    if not user:
        frappe.throw("User is required.")

    member = _project_member(project, user)
    if not member:
        frappe.throw(
            "Only active members of this project can be assigned documentation access.",
            frappe.PermissionError,
        )

    return member


def set_member_access(project, user, access_level):
    """
    Create/update one explicit Read/Write assignment for a project member.
    Only the active PM of the project can perform this action.
    """
    _assert_pm_for_project(project)
    member = _validate_access_user(project, user)

    access_level = (access_level or "").strip().title()
    if access_level not in {"Read", "Write"}:
        frappe.throw("Access level must be Read or Write.")

    existing = frappe.db.get_value(
        ACCESS_DOCTYPE,
        {"project": project, "user": user},
        "name",
    )

    if existing:
        doc = frappe.get_doc(ACCESS_DOCTYPE, existing)
        doc.access_level = access_level
        doc.save(ignore_permissions=True)
    else:
        doc = frappe.get_doc(
            {
                "doctype": ACCESS_DOCTYPE,
                "project": project,
                "user": user,
                "access_level": access_level,
            }
        )
        doc.insert(ignore_permissions=True)

    _sync_user_wiki_roles(user)
    frappe.db.commit()

    return {
        "success": True,
        "project": project,
        "user": member.user,
        "employee_name": member.employee_name,
        "access_level": access_level,
    }


def remove_member_access(project, user):
    """Remove explicit documentation access from a project member."""
    _assert_pm_for_project(project)
    _validate_access_user(project, user)

    existing = frappe.db.get_value(
        ACCESS_DOCTYPE,
        {"project": project, "user": user},
        "name",
    )

    if existing:
        frappe.delete_doc(
            ACCESS_DOCTYPE,
            existing,
            ignore_permissions=True,
        )

    _sync_user_wiki_roles(user)
    frappe.db.commit()

    return {
        "success": True,
        "project": project,
        "user": user,
        "access_level": None,
    }


def get_space_access(space, user=None):
    """
    Return project documentation access for a Wiki Space.
    This is intentionally in project_documentation; Wiki app is untouched.
    """
    user = _current_user(user)

    project_info = frappe.db.get_value(
        "Project Documentation Project",
        {"wiki_space": space},
        ["name", "is_active"],
        as_dict=True,
    )

    if not project_info:
        return {
            "is_project_space": False,
            "can_read": None,
            "can_write": None,
            "access_level": None,
            "project": None,
        }

    project = project_info.name

    if not project_info.is_active:
        return {
            "is_project_space": True,
            "can_read": False,
            "can_write": False,
            "access_level": None,
            "project": project,
        }

    # An active PM is always the documentation manager for their project.
    if project in _active_pm_projects(user):
        return {
            "is_project_space": True,
            "can_read": True,
            "can_write": True,
            "access_level": "Manager",
            "project": project,
        }

    level = _access_level(project, user)
    if not level:
        is_member = bool(
            frappe.db.exists(
                "Project User Mapping",
                {"project": project, "user": user, "still_involved": 1},
            )
        )
        if is_member:
            level = "Read"

    return {
        "is_project_space": True,
        "can_read": level in {"Read", "Write"},
        "can_write": level == "Write",
        "access_level": level,
        "project": project,
    }


def _assert_pm_for_wiki_space(space, user=None):
    """Allow sensitive Wiki approval/merge actions only to the PM of the owning project."""
    user = _current_user(user)
    project = _space_project(space)
    if not project:
        # Do not interfere with native Wiki spaces.
        return None
    _assert_pm_for_project(project, user)
    return project


def _change_request_space(change_request_name):
    return frappe.db.get_value("Wiki Change Request", change_request_name, "wiki_space")


@frappe.whitelist(allow_guest=False)
def pm_only_approve_change_request(name):
    """Wrapper for Wiki approve_change_request; project-space approvals are PM-only."""
    space = _change_request_space(name)
    if space:
        _assert_pm_for_wiki_space(space)
    from wiki.frappe_wiki.doctype.wiki_change_request import wiki_change_request
    return wiki_change_request.approve_change_request(name)


@frappe.whitelist(allow_guest=False)
def pm_only_request_changes(name, comment):
    """Wrapper for Wiki request_changes; project-space change requests are PM-only."""
    space = _change_request_space(name)
    if space:
        _assert_pm_for_wiki_space(space)
    from wiki.frappe_wiki.doctype.wiki_change_request import wiki_change_request
    return wiki_change_request.request_changes(name, comment)


@frappe.whitelist(allow_guest=False)
def pm_only_reject_change_request(name, comment):
    """Wrapper for Wiki reject_change_request; project-space rejections are PM-only."""
    space = _change_request_space(name)
    if space:
        _assert_pm_for_wiki_space(space)
    from wiki.frappe_wiki.doctype.wiki_change_request import wiki_change_request
    return wiki_change_request.reject_change_request(name, comment)


@frappe.whitelist(allow_guest=False)
def pm_only_merge_change_request(name):
    """Wrapper for Wiki merge_change_request; project-space merges are PM-only."""
    space = _change_request_space(name)
    if space:
        _assert_pm_for_wiki_space(space)
    from wiki.frappe_wiki.doctype.wiki_change_request import wiki_change_request
    return wiki_change_request.merge_change_request(name)


@frappe.whitelist(allow_guest=False)
def pm_only_get_merge_conflicts(name):
    """Wrapper for Wiki get_merge_conflicts; project-space conflict views are PM-only."""
    space = _change_request_space(name)
    if space:
        _assert_pm_for_wiki_space(space)
    from wiki.frappe_wiki.doctype.wiki_change_request import wiki_change_request
    return wiki_change_request.get_merge_conflicts(name)


@frappe.whitelist(allow_guest=False)
def pm_only_resolve_merge_conflict(conflict_name, resolution):
    """Wrapper for Wiki resolve_merge_conflict; project-space conflict resolutions are PM-only."""
    conflict = frappe.get_doc("Wiki Merge Conflict", conflict_name)
    space = _change_request_space(conflict.change_request)
    if space:
        _assert_pm_for_wiki_space(space)
    from wiki.frappe_wiki.doctype.wiki_change_request import wiki_change_request
    return wiki_change_request.resolve_merge_conflict(conflict_name, resolution)


@frappe.whitelist(allow_guest=False)
def pm_only_retry_merge_after_resolution(name):
    """Wrapper for Wiki retry_merge_after_resolution; project-space merge retries are PM-only."""
    space = _change_request_space(name)
    if space:
        _assert_pm_for_wiki_space(space)
    from wiki.frappe_wiki.doctype.wiki_change_request import wiki_change_request
    return wiki_change_request.retry_merge_after_resolution(name)


@frappe.whitelist(allow_guest=False)
def pm_only_review_action(name, reviewer=None, status=None, comment=None):
    """Backward-compatible wrapper for review action."""
    if status == "Approved":
        return pm_only_approve_change_request(name)
    elif status == "Changes Requested":
        return pm_only_request_changes(name, comment or "")
    elif status == "Rejected":
        return pm_only_reject_change_request(name, comment or "")
    else:
        space = _change_request_space(name)
        if space:
            _assert_pm_for_wiki_space(space)


@frappe.whitelist()
def custom_get_space_capabilities(space: str) -> dict:
    """Project-documentation aware space capabilities for frontend UI."""
    project = _space_project(space)
    if project:
        user = frappe.session.user
        if user == "Administrator":
            return {"can_read": True, "can_write": True, "can_contribute": True}
        is_pm = bool(project in _active_pm_projects(user))
        level = _access_level(project, user)
        can_read = is_pm or level in {"Read", "Write"}
        # can_write gates approve & merge buttons in the Wiki SPA UI
        can_write = is_pm
        can_contribute = is_pm or level == "Write"
        return {
            "can_read": can_read,
            "can_write": can_write,
            "can_contribute": can_contribute,
        }
    from wiki.api import get_space_capabilities as wiki_get_space_capabilities
    return wiki_get_space_capabilities(space)


@frappe.whitelist()
def custom_get_user_info() -> dict:
    """Enhanced user info that allows Project Documentation users into the Wiki SPA."""
    from wiki.api import get_user_info as wiki_get_user_info
    info = wiki_get_user_info()
    if not info.get("is_logged_in"):
        return info

    user = frappe.session.user
    if user == "Administrator":
        return info

    # Ensure any authenticated user has the baseline Wiki User entry to access the Wiki SPA
    existing_roles = [r.get("role") if isinstance(r, dict) else r.role for r in (info.get("roles") or [])]
    if "Wiki User" not in existing_roles:
        info["roles"] = list(info.get("roles") or []) + [{"role": "Wiki User"}]

    return info


def _space_project(space):
    return frappe.db.get_value(
        "Project Documentation Project",
        {"wiki_space": space},
        "name",
    )


def can_read_space(space, user=None):
    result = get_space_access(space, user)
    if not result["is_project_space"]:
        return None
    return result["can_read"]


def can_write_space(space, user=None):
    result = get_space_access(space, user)
    if not result["is_project_space"]:
        return None
    return result["can_write"]


def wiki_space_has_permission(doc, user=None, permission_type=None, *args, **kwargs):
    """
    Frappe has_permission hook for Wiki Space.
    None means this app does not control non-project Wiki Spaces.
    """
    if getattr(frappe.flags, "ignore_permissions", False):
        return True

    user = user or frappe.session.user
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return True

    project = _space_project(doc.name)

    if not project:
        return False if _is_project_documentation_managed_user(user) else None

    ptype = kwargs.get("ptype") or permission_type or "read"

    if ptype in {"read", "select"}:
        return bool(can_read_space(doc.name, user))

    if ptype in {"write", "create", "delete", "share"}:
        return bool(can_write_space(doc.name, user))

    return bool(can_read_space(doc.name, user))


def wiki_document_has_permission(doc, user=None, permission_type=None, *args, **kwargs):
    """Enforce project documentation permissions on Wiki Documents."""
    if getattr(frappe.flags, "ignore_permissions", False):
        return True

    user = user or frappe.session.user
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return True

    ptype = kwargs.get("ptype") or permission_type or "read"

    if not doc.wiki_space:
        return False if _is_project_documentation_managed_user(user) else None

    project = _space_project(doc.wiki_space)
    if not project:
        return False if _is_project_documentation_managed_user(user) else None

    if ptype in {"read", "select"}:
        return bool(can_read_space(doc.wiki_space, user))

    if ptype in {"write", "create", "delete", "share"}:
        return bool(can_write_space(doc.wiki_space, user))

    return bool(can_read_space(doc.wiki_space, user))


def wiki_change_request_has_permission(doc, user=None, permission_type=None, *args, **kwargs):
    """Enforce project documentation permissions on Wiki Change Requests."""
    if getattr(frappe.flags, "ignore_permissions", False):
        return True

    user = user or frappe.session.user
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return True

    ptype = kwargs.get("ptype") or permission_type or "read"

    # Mentioned / assigned users are allowed read access to the change request
    if ptype in {"read", "select"}:
        raw_assign = doc.get("_assign")
        if raw_assign:
            try:
                assignees = frappe.parse_json(raw_assign) if isinstance(raw_assign, str) else raw_assign
                if isinstance(assignees, list) and user in assignees:
                    return True
            except Exception:
                pass

    if not doc.wiki_space:
        return False if _is_project_documentation_managed_user(user) else None

    project = _space_project(doc.wiki_space)
    if not project:
        return False if _is_project_documentation_managed_user(user) else None

    # Change Requests are part of the write workflow.
    if ptype in {"read", "select"}:
        return bool(can_read_space(doc.wiki_space, user))

    return bool(can_write_space(doc.wiki_space, user))


def _readable_project_spaces(user):
    """Return project Wiki Spaces the user is explicitly allowed to read."""
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return {
            row.wiki_space
            for row in frappe.get_all(
                "Project Documentation Project",
                filters={"is_active": 1},
                fields=["wiki_space"],
            )
            if row.wiki_space
        }

    project_rows = frappe.get_all(
        "Project Documentation Project",
        filters={"is_active": 1},
        fields=["name", "wiki_space"],
    )
    project_rows = [row for row in project_rows if row.wiki_space]

    pm_projects = _active_pm_projects(user)
    readable_projects = set(pm_projects)

    # 1. Projects where user is an active team member in Project User Mapping
    member_project_rows = frappe.get_all(
        "Project User Mapping",
        filters={
            "user": user,
            "still_involved": 1,
        },
        fields=["project"],
    )
    readable_projects.update(row.project for row in member_project_rows if row.project)

    # 2. Projects where user has explicit Read or Write access
    access_rows = frappe.get_all(
        ACCESS_DOCTYPE,
        filters={
            "user": user,
            "access_level": ["in", ["Read", "Write"]],
        },
        fields=["project"],
    )
    readable_projects.update(row.project for row in access_rows if row.project)

    return {
        row.wiki_space
        for row in project_rows
        if row.name in readable_projects
    }


def wiki_space_project_query_conditions(user=None, doctype=None):
    """Limit project-controlled Wiki Space queries to readable spaces."""
    user = user or frappe.session.user

    if user == "Guest":
        return "1 = 0"

    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return ""

    project_spaces = {
        row.wiki_space
        for row in frappe.get_all(
            "Project Documentation Project",
            filters={"is_active": 1},
            fields=["wiki_space"],
        )
        if row.wiki_space
    }
    readable_spaces = _readable_project_spaces(user)

    if not project_spaces:
        return ""

    escaped_project = ", ".join(
        frappe.db.escape(space) for space in project_spaces
    )

    if _is_project_documentation_managed_user(user):
        if not readable_spaces:
            return "1 = 0"
        escaped_readable = ", ".join(
            frappe.db.escape(space) for space in readable_spaces
        )
        return f"`tabWiki Space`.`name` IN ({escaped_readable})"

    if readable_spaces:
        escaped_readable = ", ".join(
            frappe.db.escape(space) for space in readable_spaces
        )
        return (
            f"(`tabWiki Space`.`name` NOT IN ({escaped_project}) "
            f"OR `tabWiki Space`.`name` IN ({escaped_readable}))"
        )

    # Preserve native Wiki Spaces, but hide every project-controlled space.
    return f"`tabWiki Space`.`name` NOT IN ({escaped_project})"


def wiki_document_project_query_conditions(user=None, doctype=None):
    """Limit project-controlled Wiki Documents to readable spaces."""
    user = user or frappe.session.user

    if user == "Guest":
        return "1 = 0"

    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return ""

    project_spaces = {
        row.wiki_space
        for row in frappe.get_all(
            "Project Documentation Project",
            filters={"is_active": 1},
            fields=["wiki_space"],
        )
        if row.wiki_space
    }
    if not project_spaces:
        return ""

    readable_spaces = _readable_project_spaces(user)
    escaped_project = ", ".join(
        frappe.db.escape(space) for space in project_spaces
    )

    if _is_project_documentation_managed_user(user):
        if not readable_spaces:
            return "1 = 0"
        escaped_readable = ", ".join(
            frappe.db.escape(space) for space in readable_spaces
        )
        return f"`tabWiki Document`.`wiki_space` IN ({escaped_readable})"

    # Non-project documents remain governed by native Wiki rules.
    condition = (
        f"(`tabWiki Document`.`wiki_space` IS NULL "
        f"OR `tabWiki Document`.`wiki_space` NOT IN ({escaped_project})"
    )

    if readable_spaces:
        escaped_readable = ", ".join(
            frappe.db.escape(space) for space in readable_spaces
        )
        condition += (
            f" OR `tabWiki Document`.`wiki_space` IN ({escaped_readable})"
        )

    return condition + ")"


def wiki_change_request_project_query_conditions(user=None, doctype=None):
    """Limit project-controlled Change Requests to readable spaces or assigned CRs."""
    user = user or frappe.session.user

    if user == "Guest":
        return "1 = 0"

    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return ""

    project_spaces = {
        row.wiki_space
        for row in frappe.get_all(
            "Project Documentation Project",
            filters={"is_active": 1},
            fields=["wiki_space"],
        )
        if row.wiki_space
    }
    if not project_spaces:
        return ""

    readable_spaces = _readable_project_spaces(user)
    escaped_user = frappe.db.escape(f"%{user}%")
    assigned_cond = f"`tabWiki Change Request`.`_assign` LIKE {escaped_user}"

    if _is_project_documentation_managed_user(user):
        if not readable_spaces:
            return assigned_cond
        escaped_readable = ", ".join(
            frappe.db.escape(space) for space in readable_spaces
        )
        return f"(`tabWiki Change Request`.`wiki_space` IN ({escaped_readable}) OR {assigned_cond})"

    escaped_project = ", ".join(
        frappe.db.escape(space) for space in project_spaces
    )
    condition = (
        f"(`tabWiki Change Request`.`wiki_space` IS NULL "
        f"OR `tabWiki Change Request`.`wiki_space` NOT IN ({escaped_project})"
    )

    if readable_spaces:
        escaped_readable = ", ".join(
            frappe.db.escape(space) for space in readable_spaces
        )
        condition += (
            f" OR `tabWiki Change Request`.`wiki_space` IN ({escaped_readable})"
        )

    condition += f" OR {assigned_cond})"
    return condition


def extract_user_mentions_from_text(text: str) -> set[str]:
    """Extract mentioned user emails or user IDs from structured HTML/markdown text."""
    if not text or not isinstance(text, str):
        return set()
    mentions = set()
    # 1. Match TipTap mention tag: <span data-type="mention" data-id="user@example.com" ...>
    pattern_tag = r'<span[^>]*data-type=["\']mention["\'][^>]*data-id=["\']([^"\']+)["\']'
    pattern_tag_rev = r'<span[^>]*data-id=["\']([^"\']+)["\'][^>]*data-type=["\']mention["\']'
    for m in re.finditer(pattern_tag, text, re.IGNORECASE):
        mentions.add(m.group(1).strip())
    for m in re.finditer(pattern_tag_rev, text, re.IGNORECASE):
        mentions.add(m.group(1).strip())

    # 2. Match raw @email pattern
    pattern_email = r'@([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)'
    for m in re.finditer(pattern_email, text):
        mentions.add(m.group(1).strip())

    return mentions


def sync_cr_mention_assignments(doc, method=None):
    """
    When a Wiki Change Request is updated or created, extract all mentioned users across its
    revisions/blobs/description/title and assign them so it appears in 'Assigned to Me'.
    """
    if getattr(frappe.flags, "in_sync_cr_mentions", False):
        return

    try:
        frappe.flags.in_sync_cr_mentions = True
        _sync_cr_mentions_internal(doc)
    finally:
        frappe.flags.in_sync_cr_mentions = False


def _sync_cr_mentions_internal(doc):
    cr_name = doc.name if hasattr(doc, "name") else doc
    if not cr_name:
        return

    try:
        cr = frappe.get_doc("Wiki Change Request", cr_name) if isinstance(cr_name, str) else doc
    except Exception:
        return

    if not cr or not cr.get("head_revision"):
        return

    mentioned_users = set()

    if cr.get("title"):
        mentioned_users.update(extract_user_mentions_from_text(cr.title))
    if cr.get("description"):
        mentioned_users.update(extract_user_mentions_from_text(cr.description))

    # Check all content blobs linked to the CR's head revision
    revision_items = frappe.get_all(
        "Wiki Revision Item",
        filters={"revision": cr.head_revision, "is_deleted": 0},
        fields=["content_blob"],
    )
    blob_names = [it.content_blob for it in revision_items if it.content_blob]
    if blob_names:
        blobs = frappe.get_all(
            "Wiki Content Blob",
            filters={"name": ["in", blob_names]},
            fields=["content"],
        )
        for b in blobs:
            if b.content:
                mentioned_users.update(extract_user_mentions_from_text(b.content))

    if not mentioned_users:
        return

    # Check which users exist and are enabled
    valid_users = set(
        frappe.get_all(
            "User",
            filters={"name": ["in", list(mentioned_users)], "enabled": 1},
            pluck="name",
        )
    )

    if not valid_users:
        return

    existing_assigned = set()
    raw_assign = cr.get("_assign")
    if raw_assign:
        try:
            parsed = json.loads(raw_assign) if isinstance(raw_assign, str) else raw_assign
            if isinstance(parsed, list):
                existing_assigned = set(parsed)
        except Exception:
            pass

    users_to_assign = valid_users - existing_assigned
    if not users_to_assign:
        return

    from frappe.desk.form.assign_to import _add as add_assignment

    for user in users_to_assign:
        try:
            add_assignment(
                {
                    "assign_to": [user],
                    "doctype": "Wiki Change Request",
                    "name": cr.name,
                    "description": f"Mentioned in Change Request: {cr.title or cr.name}",
                },
                ignore_permissions=True,
            )
            # Guarantee read permission for the mentioned user
            if not frappe.db.exists("DocShare", {"user": user, "share_doctype": "Wiki Change Request", "share_name": cr.name}):
                frappe.share.add("Wiki Change Request", cr.name, user=user, read=1, flags={"ignore_permissions": True})
        except Exception as e:
            frappe.log_error(f"Failed to assign mentioned user {user} to CR {cr.name}: {e}")




@frappe.whitelist(allow_guest=False)
def api_get_my_pm_projects():
    return get_my_pm_projects()


@frappe.whitelist(allow_guest=False)
def api_get_pm_project(project):
    return get_pm_project(project)


@frappe.whitelist(allow_guest=False)
def api_get_project_members(project):
    return get_project_members(project)


@frappe.whitelist(allow_guest=False)
def api_get_project_access(project):
    return get_project_access(project)


@frappe.whitelist(allow_guest=False)
def api_create_wiki_space(project):
    return create_wiki_space(project)


@frappe.whitelist(allow_guest=False)
def api_set_member_access(project, user, access_level):
    return set_member_access(project, user, access_level)


@frappe.whitelist(allow_guest=False)
def api_remove_member_access(project, user):
    return remove_member_access(project, user)


@frappe.whitelist(allow_guest=False)
def api_get_space_access(space):
    return get_space_access(space)
