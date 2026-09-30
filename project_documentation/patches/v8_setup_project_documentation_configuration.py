import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

STANDARD_DOCTYPES = [
    "SSO Token Log",
    "Project User Mapping",
    "Project Documentation Project",
    "Project Documentation Access",
]

PROJECT_ROLES = [
    {"role_name": "Project Documentation Manager", "desk_access": 0},
    {"role_name": "Project Documentation Reader", "desk_access": 0},
    {"role_name": "Project Documentation Writer", "desk_access": 0},
]

USER_CUSTOM_FIELDS = {
    "User": [
        {
            "fieldname": "custom_external_user_id",
            "label": "External User ID",
            "fieldtype": "Data",
            "insert_after": "email",
            "unique": 1,
            "read_only": 1,
            "no_copy": 0,
        },
        {
            "fieldname": "custom_external_employee_id",
            "label": "External Employee ID",
            "fieldtype": "Int",
            "insert_after": "custom_external_user_id",
            "unique": 0,
            "read_only": 1,
            "no_copy": 0,
        },
        {
            "fieldname": "custom_designation",
            "label": "Designation",
            "fieldtype": "Data",
            "insert_after": "custom_external_employee_id",
            "unique": 0,
            "read_only": 1,
            "no_copy": 0,
        },
    ]
}

CUSTOM_DOCPERMS = [
    # Wiki Space
    {
        "parent": "Wiki Space",
        "role": "Project Documentation Manager",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "export": 1,
        "share": 1,
    },
    {
        "parent": "Wiki Space",
        "role": "Project Documentation Reader",
        "permlevel": 0,
        "read": 1,
        "write": 0,
        "create": 0,
        "delete": 0,
        "export": 1,
        "share": 0,
    },
    {
        "parent": "Wiki Space",
        "role": "Project Documentation Writer",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 0,
        "delete": 0,
        "export": 1,
        "share": 0,
    },
    {
        "parent": "Wiki Space",
        "role": "System Manager",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "email": 1,
        "export": 1,
        "print": 1,
        "report": 1,
        "share": 1,
    },
    {
        "parent": "Wiki Space",
        "role": "Wiki Approver",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "email": 1,
        "export": 1,
        "print": 1,
        "report": 1,
        "share": 1,
    },
    {
        "parent": "Wiki Space",
        "role": "Wiki Manager",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "email": 1,
        "export": 1,
        "print": 1,
        "share": 1,
    },
    {
        "parent": "Wiki Space",
        "role": "Wiki User",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 0,
        "delete": 0,
        "email": 1,
        "export": 1,
        "print": 1,
        "report": 1,
        "share": 1,
    },
    # Wiki Document
    {
        "parent": "Wiki Document",
        "role": "Project Documentation Manager",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "export": 1,
        "share": 1,
    },
    {
        "parent": "Wiki Document",
        "role": "Project Documentation Reader",
        "permlevel": 0,
        "read": 1,
        "write": 0,
        "create": 0,
        "delete": 0,
        "export": 1,
        "share": 0,
    },
    {
        "parent": "Wiki Document",
        "role": "Project Documentation Writer",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 0,
        "export": 1,
        "share": 0,
    },
    {
        "parent": "Wiki Document",
        "role": "System Manager",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "email": 1,
        "export": 1,
        "print": 1,
        "report": 1,
        "share": 1,
    },
    {
        "parent": "Wiki Document",
        "role": "Wiki Manager",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "email": 1,
        "export": 1,
        "print": 1,
        "report": 1,
        "share": 1,
    },
    {
        "parent": "Wiki Document",
        "role": "Wiki User",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 0,
        "delete": 0,
        "email": 1,
        "export": 1,
        "print": 1,
        "report": 1,
        "share": 1,
    },
    # Wiki Change Request
    {
        "parent": "Wiki Change Request",
        "role": "Project Documentation Manager",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "export": 1,
        "share": 1,
    },
    {
        "parent": "Wiki Change Request",
        "role": "Project Documentation Writer",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 0,
        "export": 1,
        "share": 0,
    },
    {
        "parent": "Wiki Change Request",
        "role": "System Manager",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "email": 1,
        "export": 1,
        "print": 1,
        "report": 1,
        "share": 1,
    },
    {
        "parent": "Wiki Change Request",
        "role": "Wiki Approver",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "email": 1,
        "export": 1,
        "print": 1,
        "report": 1,
        "share": 1,
    },
    {
        "parent": "Wiki Change Request",
        "role": "Wiki Manager",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "email": 1,
        "export": 1,
        "print": 1,
        "report": 1,
        "share": 1,
    },
    {
        "parent": "Wiki Change Request",
        "role": "Wiki User",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "email": 1,
        "export": 1,
        "print": 1,
        "report": 1,
        "share": 1,
    },
    {
        "parent": "Wiki Change Request",
        "role": "All",
        "permlevel": 0,
        "read": 1,
    },
    # Wiki Revision
    {
        "parent": "Wiki Revision",
        "role": "Project Documentation Manager",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "export": 1,
        "share": 1,
    },
    {
        "parent": "Wiki Revision",
        "role": "Project Documentation Writer",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "export": 1,
        "share": 0,
    },
    {
        "parent": "Wiki Revision",
        "role": "Project Documentation Reader",
        "permlevel": 0,
        "read": 1,
        "export": 1,
    },
    # Wiki Revision Item
    {
        "parent": "Wiki Revision Item",
        "role": "Project Documentation Manager",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "export": 1,
        "share": 1,
    },
    {
        "parent": "Wiki Revision Item",
        "role": "Project Documentation Writer",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "export": 1,
        "share": 0,
    },
    {
        "parent": "Wiki Revision Item",
        "role": "Project Documentation Reader",
        "permlevel": 0,
        "read": 1,
        "export": 1,
    },
    # Wiki Content Blob
    {
        "parent": "Wiki Content Blob",
        "role": "Project Documentation Manager",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "delete": 1,
        "export": 1,
        "share": 1,
    },
    {
        "parent": "Wiki Content Blob",
        "role": "Project Documentation Writer",
        "permlevel": 0,
        "read": 1,
        "write": 1,
        "create": 1,
        "export": 1,
        "share": 0,
    },
    {
        "parent": "Wiki Content Blob",
        "role": "Project Documentation Reader",
        "permlevel": 0,
        "read": 1,
        "export": 1,
    },
    # Wiki Settings
    {
        "parent": "Wiki Settings",
        "role": "Project Documentation Manager",
        "permlevel": 0,
        "read": 1,
        "export": 1,
    },
    {
        "parent": "Wiki Settings",
        "role": "Project Documentation Writer",
        "permlevel": 0,
        "read": 1,
        "export": 1,
    },
    {
        "parent": "Wiki Settings",
        "role": "Project Documentation Reader",
        "permlevel": 0,
        "read": 1,
        "export": 1,
    },
]

CLIENT_SCRIPT_CONTENT = """frappe.ui.form.on("Project Documentation Project", {
    refresh(frm) {
        if (frm.is_new()) {
            return;
        }

        if (frm.doc.wiki_space) {
            frm.add_custom_button(
                __("Open Documentation"),
                () => {
                    frappe.set_route(
                        "Form",
                        "Wiki Space",
                        frm.doc.wiki_space
                    );
                }
            );

            return;
        }

        frm.add_custom_button(
            __("Initialize Documentation"),
            () => {
                frappe.confirm(
                    __(
                        "Initialize documentation for this project?<br><br>" +
                        "This will create a Wiki Space and the standard " +
                        "8-section documentation structure."
                    ),
                    () => {
                        frappe.call({
                            method:
                                "project_documentation.api.wiki_provisioning.initialize_documentation",
                            args: {
                                project: frm.doc.name,
                            },
                            freeze: true,
                            freeze_message: __(
                                "Initializing documentation..."
                            ),
                            callback(r) {
                                if (r.message) {
                                    frappe.show_alert({
                                        message: r.message.message,
                                        indicator:
                                            r.message.status === "CREATED"
                                                ? "green"
                                                : "blue",
                                    });

                                    frm.reload_doc();
                                }
                            },
                        });
                    }
                );
            }
        );
    },
});"""


def execute():
    # 1. Standardize DocTypes
    for doctype in STANDARD_DOCTYPES:
        if frappe.db.exists("DocType", doctype):
            frappe.db.set_value("DocType", doctype, "custom", 0, update_modified=False)

    # 2. Setup Roles
    for role_def in PROJECT_ROLES:
        role_name = role_def["role_name"]
        if not frappe.db.exists("Role", role_name):
            role_doc = frappe.new_doc("Role")
            role_doc.role_name = role_name
            role_doc.desk_access = role_def.get("desk_access", 0)
            role_doc.insert(ignore_permissions=True)
        else:
            frappe.db.set_value(
                "Role",
                role_name,
                {"desk_access": role_def.get("desk_access", 0), "disabled": 0},
                update_modified=False,
            )

    # 3. Setup Custom Fields
    create_custom_fields(USER_CUSTOM_FIELDS, ignore_validate=True)

    # 4. Setup Custom DocPerms
    for perm in CUSTOM_DOCPERMS:
        parent = perm["parent"]
        role = perm["role"]
        permlevel = perm.get("permlevel", 0)

        existing = frappe.get_all(
            "Custom DocPerm",
            filters={"parent": parent, "role": role, "permlevel": permlevel},
            fields=["name"],
        )

        if existing:
            # Update the first matching row and remove any duplicates
            doc_name = existing[0].name
            doc = frappe.get_doc("Custom DocPerm", doc_name)
            doc.update({k: v for k, v in perm.items() if k not in ("parent", "role", "permlevel")})
            doc.save(ignore_permissions=True)

            for extra in existing[1:]:
                frappe.delete_doc("Custom DocPerm", extra.name, ignore_permissions=True)
        else:
            doc = frappe.new_doc("Custom DocPerm")
            doc.update(perm)
            doc.insert(ignore_permissions=True)

    # 5. Setup Client Script
    if not frappe.db.exists("Client Script", "project_documentation_project"):
        cs = frappe.new_doc("Client Script")
        cs.name = "project_documentation_project"
        cs.dt = "Project Documentation Project"
        cs.module = "Project Documentation"
        cs.view = "Form"
        cs.enabled = 1
        cs.script = CLIENT_SCRIPT_CONTENT
        cs.insert(ignore_permissions=True)
    else:
        frappe.db.set_value(
            "Client Script",
            "project_documentation_project",
            {
                "dt": "Project Documentation Project",
                "module": "Project Documentation",
                "view": "Form",
                "enabled": 1,
                "script": CLIENT_SCRIPT_CONTENT,
            },
            update_modified=False,
        )

    frappe.clear_cache()
    frappe.db.commit()
