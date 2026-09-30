import frappe
from frappe.model.document import Document


class ProjectDocumentationAccess(Document):
    def validate(self):
        duplicate = frappe.db.exists(
            "Project Documentation Access",
            {
                "project": self.project,
                "user": self.user,
                "name": ["!=", self.name],
            },
        )
        if duplicate:
            frappe.throw("Documentation access already exists for this user and project.")
