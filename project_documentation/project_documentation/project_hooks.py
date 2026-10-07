import re
import frappe


def create_project_wiki_space(doc, method=None):
    """
    Hook entry point for Project Documentation Project after_insert.
    """
    if getattr(frappe.flags, "skip_project_wiki_creation", False):
        return

    initialize_project_documentation(doc)


def initialize_project_documentation(doc):
    """
    Create and link a Wiki Space for a Project Documentation Project.

    This function does not create anything if the project
    already has a Wiki Space. Only the Wiki Space is initialized;
    no extra child folders/documents are created.
    """
    if isinstance(doc, str):
        doc = frappe.get_doc("Project Documentation Project", doc)

    if doc.wiki_space:
        return frappe.get_doc("Wiki Space", doc.wiki_space)

    if not doc.project_code:
        frappe.throw("Project Code is required before initializing documentation.")

    if not doc.project_name:
        frappe.throw("Project Name is required before initializing documentation.")

    route = re.sub(r"[^a-z0-9]+", "-", doc.project_code.strip().lower()).strip("-")
    if not route:
        route = re.sub(r"[^a-z0-9]+", "-", doc.name.strip().lower()).strip("-")

    existing_space_name = frappe.db.get_value(
        "Wiki Space",
        {"route": route},
        "name",
    )

    if existing_space_name:
        space = frappe.get_doc("Wiki Space", existing_space_name)
    else:
        space = frappe.get_doc({
            "doctype": "Wiki Space",
            "space_name": doc.project_name,
            "route": route,
        })
        previous_ignore_permissions = getattr(frappe.flags, "ignore_permissions", False)
        frappe.flags.ignore_permissions = True
        try:
            space.insert(ignore_permissions=True)
        finally:
            frappe.flags.ignore_permissions = previous_ignore_permissions

    # Link Wiki Space to Project.
    frappe.db.set_value(
        "Project Documentation Project",
        doc.name,
        "wiki_space",
        space.name,
        update_modified=False,
    )
    doc.wiki_space = space.name

    return space