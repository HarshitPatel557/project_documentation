import frappe


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/project-documentation"
        raise frappe.Redirect

    # Project Documentation is a PM management entry point.
    # Non-PMs should go directly to the Wiki Spaces list.
    is_pm = bool(
        frappe.db.exists(
            "Project User Mapping",
            {
                "user": frappe.session.user,
                "project_designation": "PM",
                "still_involved": 1,
            },
        )
    )
    if not is_pm:
        frappe.local.flags.redirect_location = "/wiki-app/spaces/"
        raise frappe.Redirect
    context.no_cache = 1
    context.show_sidebar = False
    context.no_breadcrumbs = True
    context.title = "Project Documentation"
    return context
