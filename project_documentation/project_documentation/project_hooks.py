import frappe


DOCUMENTATION_SECTIONS = [
    "01 - Project Overview",
    "02 - Requirements",
    "03 - Architecture",
    "04 - Development",
    "05 - Testing",
    "06 - Deployment",
    "07 - Operations",
    "08 - Project Decisions",
]


def create_project_wiki_space(doc, method=None):
    """
    Legacy hook entry point.

    Wiki creation is now controlled explicitly through
    the Initialize Documentation action.

    This function is intentionally kept for compatibility
    with any existing references.
    """
    if getattr(frappe.flags, "skip_project_wiki_creation", False):
        return

    initialize_project_documentation(doc)


def initialize_project_documentation(doc):
    """
    Create and link a Wiki Space for a Project Documentation Project.

    This function does not create anything if the project
    already has a Wiki Space.
    """

    if doc.wiki_space:
        return frappe.get_doc("Wiki Space", doc.wiki_space)

    if not doc.project_code:
        frappe.throw("Project Code is required before initializing documentation.")

    if not doc.project_name:
        frappe.throw("Project Name is required before initializing documentation.")

    route = doc.project_code.strip().lower().replace(" ", "-")

    existing_space = frappe.db.get_value(
        "Wiki Space",
        {"route": route},
        "name",
    )

    if existing_space:
        frappe.throw(
            f"Wiki Space route '{route}' already exists. "
            "Please resolve the existing Wiki Space before initializing "
            "documentation for this project."
        )

    # Create Wiki Space.
    # Wiki Space creates its root Wiki Document during before_insert().
    space = frappe.get_doc({
        "doctype": "Wiki Space",
        "space_name": doc.project_name,
        "route": route,
    })

    space.insert(ignore_permissions=True)

    # Link Wiki Space to Project.
    frappe.db.set_value(
        "Project Documentation Project",
        doc.name,
        "wiki_space",
        space.name,
        update_modified=False,
    )

    # Create standard documentation structure.
    create_documentation_structure(space)

    return space


def create_documentation_structure(space):
    """
    Create the standard documentation groups inside a Wiki Space.
    """

    root_group = space.root_group

    if not root_group:
        frappe.throw("Wiki Space was created without a root group.")

    for title in DOCUMENTATION_SECTIONS:
        frappe.get_doc({
            "doctype": "Wiki Document",
            "title": title,
            "wiki_space": space.name,
            "parent_wiki_document": root_group,
            "is_group": 1,
            "is_published": 1,
        }).insert()