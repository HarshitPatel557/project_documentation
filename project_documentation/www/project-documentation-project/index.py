import frappe

def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/project-documentation"
        raise frappe.Redirect
    context.no_cache = 1
    context.show_sidebar = False
    context.no_breadcrumbs = True
    context.title = "Project Details - Promot Wiki"
    return context
