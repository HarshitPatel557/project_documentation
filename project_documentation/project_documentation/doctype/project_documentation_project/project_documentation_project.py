from frappe.model.document import Document
import frappe


class ProjectDocumentationProject(Document):
    def after_insert(self):
        if not self.wiki_space and getattr(self, "is_active", 1):
            if not getattr(frappe.flags, "skip_project_wiki_creation", False):
                from project_documentation.project_documentation.project_hooks import (
                    initialize_project_documentation,
                )
                initialize_project_documentation(self)
