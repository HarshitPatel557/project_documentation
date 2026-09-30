import frappe


STANDARD_DOCTYPES = [
    "SSO Token Log",
    "Project User Mapping",
    "Project Documentation Project",
    "Project Documentation Access",
]


def execute():
    for doctype in STANDARD_DOCTYPES:
        if frappe.db.exists("DocType", doctype):
            frappe.db.set_value("DocType", doctype, "custom", 0, update_modified=False)
            frappe.clear_cache(doctype=doctype)
    frappe.db.commit()
