import frappe
from frappe.tests.utils import FrappeTestCase
from project_documentation.api.project_access import (
    set_member_access,
    custom_get_space_capabilities,
    _sync_user_wiki_roles,
    _ensure_documentation_role_permissions,
)
from wiki.permissions import can_write_space, can_read_space, can_contribute_to_space
from wiki.frappe_wiki.doctype.wiki_change_request.wiki_change_request import apply_cr_operations
from wiki.www.wiki_app import get_context as get_wiki_app_context


class TestReadonlyReaderRedirect(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        _ensure_documentation_role_permissions()

        # 1. Create PM user
        if not frappe.db.exists("User", "pm_redirect_test@example.com"):
            pm = frappe.new_doc("User")
            pm.email = "pm_redirect_test@example.com"
            pm.first_name = "PM"
            pm.send_welcome_email = 0
            pm.flags.ignore_permissions = True
            pm.flags.ignore_password_policy = True
            pm.db_insert()
        else:
            frappe.db.set_value("User", "pm_redirect_test@example.com", "enabled", 1)

        # 2. Create Member user
        if not frappe.db.exists("User", "member_redirect_test@example.com"):
            u = frappe.new_doc("User")
            u.email = "member_redirect_test@example.com"
            u.first_name = "Member"
            u.send_welcome_email = 0
            u.flags.ignore_permissions = True
            u.flags.ignore_password_policy = True
            u.db_insert()
        else:
            frappe.db.set_value("User", "member_redirect_test@example.com", "enabled", 1)

        # 3. Create Project A & Space A
        if not frappe.db.exists("Project Documentation Project", "PROJ_A"):
            p_a = frappe.new_doc("Project Documentation Project")
            p_a.project_name = "Project A"
            p_a.project_code = "PROJ_A"
            p_a.is_active = 1
            p_a.insert(ignore_permissions=True)
        else:
            p_a = frappe.get_doc("Project Documentation Project", "PROJ_A")

        space_a_name = frappe.db.get_value("Wiki Space", {"route": "proj-a-space"}, "name")
        if not space_a_name:
            s_a = frappe.new_doc("Wiki Space")
            s_a.space_name = "Project A Space"
            s_a.route = "proj-a-space"
            s_a.insert(ignore_permissions=True)
            space_a_name = s_a.name
        p_a.wiki_space = space_a_name
        p_a.save(ignore_permissions=True)
        self.space_a = space_a_name

        # Create Document A
        doc_a_name = frappe.db.get_value("Wiki Document", {"title": "Doc A in Space A"}, "name")
        root_group_a = frappe.db.get_value("Wiki Space", space_a_name, "root_group")
        if not doc_a_name:
            doc_a = frappe.new_doc("Wiki Document")
            doc_a.title = "Doc A in Space A"
            doc_a.wiki_space = space_a_name
            doc_a.parent_wiki_document = root_group_a
            doc_a.route = "proj-a-space/doc-a"
            doc_a.is_published = 1
            doc_a.insert(ignore_permissions=True)
            doc_a_name = doc_a.name
        else:
            frappe.db.set_value("Wiki Document", doc_a_name, "wiki_space", space_a_name)
            if root_group_a:
                frappe.db.set_value("Wiki Document", doc_a_name, "parent_wiki_document", root_group_a)
        self.doc_a = doc_a_name

        # 4. Create Project B & Space B (to test project isolation)
        if not frappe.db.exists("Project Documentation Project", "PROJ_B"):
            p_b = frappe.new_doc("Project Documentation Project")
            p_b.project_name = "Project B"
            p_b.project_code = "PROJ_B"
            p_b.is_active = 1
            p_b.insert(ignore_permissions=True)
        else:
            p_b = frappe.get_doc("Project Documentation Project", "PROJ_B")

        space_b_name = frappe.db.get_value("Wiki Space", {"route": "proj-b-space"}, "name")
        if not space_b_name:
            s_b = frappe.new_doc("Wiki Space")
            s_b.space_name = "Project B Space"
            s_b.route = "proj-b-space"
            s_b.insert(ignore_permissions=True)
            space_b_name = s_b.name
        p_b.wiki_space = space_b_name
        p_b.save(ignore_permissions=True)
        self.space_b = space_b_name

        # Project user mappings
        frappe.db.delete("Project User Mapping", {"project": ["in", ["PROJ_A", "PROJ_B"]]})
        for proj, role in [("PROJ_A", "PM"), ("PROJ_B", "PM")]:
            m = frappe.new_doc("Project User Mapping")
            m.project = proj
            m.user = "pm_redirect_test@example.com"
            m.employee_name = "PM Test"
            m.project_designation = role
            m.still_involved = 1
            m.insert(ignore_permissions=True)

        for proj, role in [("PROJ_A", "Developer"), ("PROJ_B", "Developer")]:
            m = frappe.new_doc("Project User Mapping")
            m.project = proj
            m.user = "member_redirect_test@example.com"
            m.employee_name = "Member Test"
            m.project_designation = role
            m.still_involved = 1
            m.insert(ignore_permissions=True)

        frappe.db.delete("Project Documentation Access", {"project": ["in", ["PROJ_A", "PROJ_B"]]})
        frappe.db.commit()

    def test_read_only_capabilities_and_reader_url(self):
        """1. Read-only user receives is_read_only=True, correct reader_url, and cannot edit."""
        frappe.set_user("pm_redirect_test@example.com")
        set_member_access("PROJ_A", "member_redirect_test@example.com", "Read")

        frappe.set_user("member_redirect_test@example.com")
        caps = custom_get_space_capabilities(self.space_a, page=self.doc_a)
        self.assertTrue(caps.get("can_read"))
        self.assertFalse(caps.get("can_write"))
        self.assertFalse(caps.get("can_contribute"))
        self.assertTrue(caps.get("is_read_only"))
        self.assertEqual(caps.get("reader_url"), "/proj-a-space/doc-a")

        # Without page parameter, reader_url points to space root
        caps_space = custom_get_space_capabilities(self.space_a)
        self.assertEqual(caps_space.get("reader_url"), "/proj-a-space/")

        # Verify reader page _can_show_edit returns False
        doc = frappe.get_doc("Wiki Document", self.doc_a)
        space_doc = frappe.get_doc("Wiki Space", self.space_a)
        self.assertFalse(doc._can_show_edit(space_doc, user="member_redirect_test@example.com"))

    def test_direct_url_access_redirects_in_wiki_app(self):
        """2. Direct URL access to wiki-app spaces/page triggers frappe.Redirect to reader_url."""
        frappe.set_user("pm_redirect_test@example.com")
        set_member_access("PROJ_A", "member_redirect_test@example.com", "Read")

        frappe.set_user("member_redirect_test@example.com")
        frappe.form_dict.app_path = f"spaces/{self.space_a}/page/{self.doc_a}"

        from frappe.exceptions import Redirect
        with self.assertRaises(Redirect):
            get_wiki_app_context()

        self.assertEqual(frappe.flags.redirect_location, "/proj-a-space/doc-a")
        frappe.form_dict.clear()

    def test_direct_write_rejected_by_backend(self):
        """3. Read-only user submitting direct write or apply_cr_operations is rejected."""
        frappe.set_user("pm_redirect_test@example.com")
        set_member_access("PROJ_A", "member_redirect_test@example.com", "Read")

        # Create a CR as Administrator first
        frappe.set_user("Administrator")
        rev1 = frappe.new_doc("Wiki Revision")
        rev1.wiki_space = self.space_a
        rev1.message = "Base"
        rev1.insert(ignore_permissions=True)

        rev2 = frappe.new_doc("Wiki Revision")
        rev2.wiki_space = self.space_a
        rev2.message = "Head"
        rev2.insert(ignore_permissions=True)

        cr = frappe.new_doc("Wiki Change Request")
        cr.wiki_space = self.space_a
        cr.title = "Test CR"
        cr.status = "Draft"
        cr.base_revision = rev1.name
        cr.head_revision = rev2.name
        cr.insert(ignore_permissions=True)

        frappe.set_user("member_redirect_test@example.com")
        # apply_cr_operations must throw PermissionError
        with self.assertRaises(frappe.PermissionError):
            apply_cr_operations(
                name=cr.name,
                base_version=0,
                operations=[{"type": "update_content", "doc_key": self.doc_a, "content": "Hacked content"}]
            )

        # Direct wiki document save must throw PermissionError
        doc = frappe.get_doc("Wiki Document", self.doc_a)
        doc.content = "Unauthorized change"
        with self.assertRaises(frappe.PermissionError):
            doc.save()

    def test_pm_changes_write_to_read_and_read_to_write(self):
        """4 & 5. PM changes Write -> Read -> Write toggles capabilities, editor availability, and permissions."""
        frappe.set_user("pm_redirect_test@example.com")
        # Initially Write
        set_member_access("PROJ_A", "member_redirect_test@example.com", "Write")

        frappe.set_user("member_redirect_test@example.com")
        caps_write = custom_get_space_capabilities(self.space_a, page=self.doc_a)
        self.assertTrue(caps_write.get("can_contribute"))
        self.assertFalse(caps_write.get("is_read_only"))
        doc = frappe.get_doc("Wiki Document", self.doc_a)
        space_doc = frappe.get_doc("Wiki Space", self.space_a)
        self.assertTrue(doc._can_show_edit(space_doc, user="member_redirect_test@example.com"))

        # PM changes Write -> Read
        frappe.set_user("pm_redirect_test@example.com")
        set_member_access("PROJ_A", "member_redirect_test@example.com", "Read")

        frappe.set_user("member_redirect_test@example.com")
        caps_read = custom_get_space_capabilities(self.space_a, page=self.doc_a)
        self.assertFalse(caps_read.get("can_write"))
        self.assertFalse(caps_read.get("can_contribute"))
        self.assertTrue(caps_read.get("is_read_only"))
        self.assertFalse(doc._can_show_edit(space_doc, user="member_redirect_test@example.com"))

        # PM changes Read -> Write
        frappe.set_user("pm_redirect_test@example.com")
        set_member_access("PROJ_A", "member_redirect_test@example.com", "Write")

        frappe.set_user("member_redirect_test@example.com")
        caps_write_again = custom_get_space_capabilities(self.space_a, page=self.doc_a)
        self.assertTrue(caps_write_again.get("can_contribute"))
        self.assertFalse(caps_write_again.get("is_read_only"))
        self.assertTrue(doc._can_show_edit(space_doc, user="member_redirect_test@example.com"))

    def test_access_in_other_projects_unaffected(self):
        """6. Changing access to Read in Project A leaves Write access in Project B unaffected."""
        frappe.set_user("pm_redirect_test@example.com")
        set_member_access("PROJ_A", "member_redirect_test@example.com", "Read")
        set_member_access("PROJ_B", "member_redirect_test@example.com", "Write")

        frappe.set_user("member_redirect_test@example.com")
        caps_a = custom_get_space_capabilities(self.space_a)
        caps_b = custom_get_space_capabilities(self.space_b)

        # Space A is Read-only
        self.assertTrue(caps_a.get("is_read_only"))
        self.assertFalse(caps_a.get("can_contribute"))

        # Space B is Writable
        self.assertFalse(caps_b.get("is_read_only"))
        self.assertTrue(caps_b.get("can_contribute"))

    def test_empty_space_capabilities(self):
        """7. Empty space returns reader_url=None and has_documents=False for read-only user."""
        frappe.set_user("pm_redirect_test@example.com")
        set_member_access("PROJ_B", "member_redirect_test@example.com", "Read")

        frappe.set_user("member_redirect_test@example.com")
        caps_b = custom_get_space_capabilities(self.space_b)
        self.assertTrue(caps_b.get("is_read_only"))
        self.assertFalse(caps_b.get("has_documents"))
        self.assertFalse(caps_b.get("has_published_documents"))
        self.assertIsNone(caps_b.get("reader_url"))
