import frappe

from project_documentation.project_documentation.project_hooks import (
    initialize_project_documentation,
)


def initialize_documentation(project):
    """
    Initialize Wiki documentation for a Project Documentation Project.

    This remains available for an explicit/manual initialization action.
    Normal PROMOT project synchronization uses the background provisioning
    functions below so the sync request is not blocked by Wiki creation.
    """
    if not project:
        frappe.throw("Project is required.")

    doc = frappe.get_doc(
        "Project Documentation Project",
        project,
    )

    if doc.wiki_space:
        space = frappe.get_doc("Wiki Space", doc.wiki_space)
        return {
            "status": "ALREADY_EXISTS",
            "project": doc.name,
            "wiki_space": space.name,
            "route": space.route,
            "message": "Documentation is already initialized.",
        }

    space = initialize_project_documentation(doc)

    frappe.db.commit()

    return {
        "status": "CREATED",
        "project": doc.name,
        "wiki_space": space.name,
        "route": space.route,
        "message": "Documentation initialized successfully.",
    }


def provision_all_project_wiki_spaces():
    """
    Create Wiki Spaces for every active Project Documentation Project that
    does not already have one.

    This runs as a background job. It is intentionally idempotent and
    skips projects that already have a Wiki Space.
    """
    projects = frappe.get_all(
        "Project Documentation Project",
        filters={
            "is_active": 1,
            "wiki_space": ["is", "not set"],
        },
        fields=["name", "project_code", "project_name"],
        order_by="name asc",
    )

    result = {
        "total_candidates": len(projects),
        "created": 0,
        "already_initialized": 0,
        "failed": 0,
        "details": [],
    }

    for project in projects:
        try:
            doc = frappe.get_doc("Project Documentation Project", project.name)

            if doc.wiki_space:
                result["already_initialized"] += 1
                continue

            # Wiki Space creation may create related Wiki records internally.
            # Run this background operation with permissions bypassed while
            # preserving the background worker's user/session.
            previous_ignore_permissions = getattr(
                frappe.flags, "ignore_permissions", False
            )
            frappe.flags.ignore_permissions = True
            try:
                space = initialize_project_documentation(doc)
            finally:
                frappe.flags.ignore_permissions = previous_ignore_permissions

            frappe.db.commit()

            result["created"] += 1
            result["details"].append({
                "project": doc.name,
                "status": "CREATED",
                "wiki_space": space.name,
            })

        except Exception as exc:
            frappe.db.rollback()
            result["failed"] += 1
            result["details"].append({
                "project": project.name,
                "status": "FAILED",
                "error": str(exc),
            })
            frappe.log_error(
                frappe.get_traceback(),
                f"Project Wiki Space provisioning failed: {project.name}",
            )

    return result


def queue_missing_wiki_spaces():
    """
    Queue one background job that provisions Wiki Spaces for all active
    projects that do not have one.

    Safe to call repeatedly from migrations, PROMOT sync, and the scheduler.
    """
    try:
        frappe.enqueue(
            "project_documentation.api.wiki_provisioning.provision_all_project_wiki_spaces",
            queue="long",
            enqueue_after_commit=True,
            job_id="project_documentation_wiki_provisioning",
            deduplicate=True,
        )

        return {
            "queued": True,
            "job_id": "project_documentation_wiki_provisioning",
        }

    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "Wiki Space Provisioning Queue Failed",
        )

        return {
            "queued": False,
        }
