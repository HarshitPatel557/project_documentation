import json
import frappe
from frappe.tests.utils import FrappeTestCase
from project_documentation.api.project_access import (
    pm_only_approve_change_request,
    pm_only_request_changes,
    pm_only_reject_change_request,
    pm_only_merge_change_request,
    custom_get_space_capabilities,
    sync_cr_mention_assignments,
    extract_user_mentions_from_text,
    _ensure_documentation_role_permissions,
    _sync_user_wiki_roles,
)


class TestMentionAndCRAccess(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        _ensure_documentation_role_permissions()

        # 1. Create PM user
        if not frappe.db.exists("User", "test_pm_user@example.com"):
            pm = frappe.new_doc("User")
            pm.email = "test_pm_user@example.com"
            pm.first_name = "Test"
            pm.last_name = "PM"
            pm.send_welcome_email = 0
            pm.flags.ignore_permissions = True
            pm.flags.ignore_password_policy = True
            pm.db_insert()
        else:
            frappe.db.set_value("User", "test_pm_user@example.com", "enabled", 1)

        # 2. Create Writer user
        if not frappe.db.exists("User", "test_writer_user@example.com"):
            w = frappe.new_doc("User")
            w.email = "test_writer_user@example.com"
            w.first_name = "Test"
            w.last_name = "Writer"
            w.send_welcome_email = 0
            w.flags.ignore_permissions = True
            w.flags.ignore_password_policy = True
            w.db_insert()
        else:
            frappe.db.set_value("User", "test_writer_user@example.com", "enabled", 1)

        # 3. Create Mentioned user
        if not frappe.db.exists("User", "test_mentioned_user@example.com"):
            m = frappe.new_doc("User")
            m.email = "test_mentioned_user@example.com"
            m.first_name = "Test"
            m.last_name = "Mentioned"
            m.send_welcome_email = 0
            m.flags.ignore_permissions = True
            m.flags.ignore_password_policy = True
            m.db_insert()
        else:
            frappe.db.set_value("User", "test_mentioned_user@example.com", "enabled", 1)

        # 4. Create Project & Space
        if not frappe.db.exists("Project Documentation Project", "TMP"):
            proj = frappe.new_doc("Project Documentation Project")
            proj.project_name = "Test Mention Project"
            proj.project_code = "TMP"
            proj.is_active = 1
            proj.insert(ignore_permissions=True)
        else:
            proj = frappe.get_doc("Project Documentation Project", "TMP")

        space_name = frappe.db.get_value("Wiki Space", {"route": "test-mention-space"}, "name")
        if not space_name:
            space = frappe.new_doc("Wiki Space")
            space.space_name = "Test Mention Space"
            space.route = "test-mention-space"
            space.insert(ignore_permissions=True)
            space_name = space.name
        else:
            space = frappe.get_doc("Wiki Space", space_name)

        proj.wiki_space = space_name
        proj.save(ignore_permissions=True)
        self.space_name = space_name

        # 5. Setup Project User Mappings
        frappe.db.delete("Project User Mapping", {"project": "TMP"})
        pm_map = frappe.new_doc("Project User Mapping")
        pm_map.project = "TMP"
        pm_map.user = "test_pm_user@example.com"
        pm_map.employee_name = "Test PM"
        pm_map.project_designation = "PM"
        pm_map.still_involved = 1
        pm_map.insert(ignore_permissions=True)

        writer_map = frappe.new_doc("Project User Mapping")
        writer_map.project = "TMP"
        writer_map.user = "test_writer_user@example.com"
        writer_map.employee_name = "Test Writer"
        writer_map.project_designation = "Developer"
        writer_map.still_involved = 1
        writer_map.insert(ignore_permissions=True)

        # Set Project Documentation Access
        frappe.db.delete("Project Documentation Access", {"project": "TMP"})
        acc = frappe.new_doc("Project Documentation Access")
        acc.project = "TMP"
        acc.user = "test_writer_user@example.com"
        acc.access_level = "Write"
        acc.insert(ignore_permissions=True)

        _sync_user_wiki_roles("test_pm_user@example.com")
        _sync_user_wiki_roles("test_writer_user@example.com")

    def test_extract_user_mentions(self):
        text = 'Hello <span data-type="mention" data-id="test_mentioned_user@example.com" data-label="Test Mentioned">@Test Mentioned</span>, please review.'
        mentions = extract_user_mentions_from_text(text)
        self.assertIn("test_mentioned_user@example.com", mentions)

    def _create_test_cr(self, title="Test CR", description=None):
        rev1 = frappe.new_doc("Wiki Revision")
        rev1.wiki_space = self.space_name
        rev1.message = "Base"
        rev1.insert(ignore_permissions=True)

        rev2 = frappe.new_doc("Wiki Revision")
        rev2.wiki_space = self.space_name
        rev2.message = "Head"
        rev2.insert(ignore_permissions=True)

        cr = frappe.new_doc("Wiki Change Request")
        cr.title = title
        cr.description = description
        cr.wiki_space = self.space_name
        cr.base_revision = rev1.name
        cr.head_revision = rev2.name
        cr.status = "In Review"
        cr.insert(ignore_permissions=True)
        return cr

    def test_writer_cannot_approve_or_merge_cr(self):
        cr = self._create_test_cr("Test CR for Approval")

        # Writer tries to approve -> Must raise PermissionError
        frappe.set_user("test_writer_user@example.com")
        with self.assertRaises(frappe.PermissionError):
            pm_only_approve_change_request(cr.name)

        # Writer tries to request changes -> Must raise PermissionError
        with self.assertRaises(frappe.PermissionError):
            pm_only_request_changes(cr.name, "Change something")

        # Writer tries to reject -> Must raise PermissionError
        with self.assertRaises(frappe.PermissionError):
            pm_only_reject_change_request(cr.name, "Rejected")

        # Writer tries to merge -> Must raise PermissionError
        with self.assertRaises(frappe.PermissionError):
            pm_only_merge_change_request(cr.name)

        # Capabilities: writer can contribute, but can_write (approval/merge power) is False
        caps = custom_get_space_capabilities(self.space_name)
        self.assertTrue(caps["can_read"])
        self.assertTrue(caps["can_contribute"])
        self.assertFalse(caps["can_write"])

    def test_pm_can_review_cr(self):
        cr = self._create_test_cr("Test CR for PM Approval")

        frappe.set_user("test_pm_user@example.com")
        # PM approve should succeed
        pm_only_approve_change_request(cr.name)
        cr.reload()
        self.assertEqual(cr.status, "Approved")

        # PM capabilities: can_read, can_write, can_contribute are all True
        caps = custom_get_space_capabilities(self.space_name)
        self.assertTrue(caps["can_read"])
        self.assertTrue(caps["can_write"])
        self.assertTrue(caps["can_contribute"])

    def test_writer_can_edit_and_save_wiki_page_without_permission_error(self):
        # 1. Setup a published document in the space
        frappe.set_user("Administrator")
        doc = frappe.new_doc("Wiki Document")
        doc.wiki_space = self.space_name
        doc.title = "Published Page"
        doc.doc_key = "pub_page_1"
        doc.route = "test-mention-space/published-page"
        doc.is_published = 1
        doc.insert(ignore_permissions=True)

        # 2. Switch to Writer user
        frappe.set_user("test_writer_user@example.com")

        from wiki.frappe_wiki.doctype.wiki_change_request.wiki_change_request import (
            get_or_create_draft_change_request,
            create_cr_page,
            update_cr_page,
        )

        # 3. Standard Wiki CR is automatically created/used
        draft_cr = get_or_create_draft_change_request(self.space_name, title="Writer Edit")
        self.assertIsNotNone(draft_cr.get("name"))

        # 4. Writer creates and updates a page in CR
        new_key = create_cr_page(
            name=draft_cr["name"],
            parent_key=None,
            title="Draft Sub Page",
            content="# Subpage Content\nWritten by writer",
        )
        self.assertIsNotNone(new_key)

        # Update the page content
        update_cr_page(
            name=draft_cr["name"],
            doc_key=new_key,
            fields={"title": "Updated Sub Page", "content": "# Updated Content"},
        )

        # Verify revision items and blobs exist and have correct permissions
        item = frappe.get_doc("Wiki Revision Item", {"doc_key": new_key, "revision": draft_cr["head_revision"]})
        self.assertEqual(item.title, "Updated Sub Page")

    def test_custom_get_user_info_allows_wiki_spa_access(self):
        from project_documentation.api.project_access import custom_get_user_info

        # Writer user
        frappe.set_user("test_writer_user@example.com")
        info = custom_get_user_info()
        roles = [r.get("role") if isinstance(r, dict) else r.role for r in info.get("roles", [])]
        self.assertIn("Wiki User", roles)

        # Non-project user without PD roles
        if not frappe.db.exists("User", "unrelated_user@example.com"):
            u = frappe.new_doc("User")
            u.email = "unrelated_user@example.com"
            u.first_name = "Unrelated"
            u.flags.ignore_permissions = True
            u.flags.ignore_password_policy = True
            u.db_insert()
        else:
            frappe.db.set_value("User", "unrelated_user@example.com", "enabled", 1)

        frappe.set_user("unrelated_user@example.com")
        unrelated_info = custom_get_user_info()
        unrelated_roles = [r.get("role") if isinstance(r, dict) else r.role for r in unrelated_info.get("roles", [])]
        self.assertNotIn("Wiki User", unrelated_roles)

    def test_new_wiki_space_project_isolation(self):
        # Authorized writer can access the space
        frappe.set_user("test_writer_user@example.com")
        caps = custom_get_space_capabilities(self.space_name)
        self.assertTrue(caps["can_read"])
        self.assertTrue(caps["can_contribute"])

        # Unrelated user cannot access the project space
        frappe.set_user("unrelated_user@example.com")
        unrelated_caps = custom_get_space_capabilities(self.space_name)
        self.assertFalse(unrelated_caps["can_read"])
        self.assertFalse(unrelated_caps["can_contribute"])
        self.assertFalse(unrelated_caps["can_write"])

    def test_mention_syncs_to_assigned_to_me(self):
        cr = self._create_test_cr(
            "CR with Mention",
            description='<p>Check this <span data-type="mention" data-id="test_mentioned_user@example.com" data-label="Test Mentioned">@Test Mentioned</span></p>',
        )

        # Run mention sync
        sync_cr_mention_assignments(cr.name)

        # Reload CR and check _assign
        cr.reload()
        raw_assign = cr.get("_assign") or "[]"
        assignees = json.loads(raw_assign) if isinstance(raw_assign, str) else raw_assign
        self.assertIn("test_mentioned_user@example.com", assignees)

        # Mentioned user should have permission to read the CR
        frappe.set_user("test_mentioned_user@example.com")
        has_perm = frappe.has_permission("Wiki Change Request", "read", doc=cr, user="test_mentioned_user@example.com")
        self.assertTrue(has_perm)
