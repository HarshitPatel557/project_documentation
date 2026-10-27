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

        # 3. Create Mentioned users
        for email, first, last in [
            ("test_mentioned_user@example.com", "Test", "Mentioned"),
            ("test_mentioned_user_2@example.com", "Test2", "Mentioned2"),
        ]:
            if not frappe.db.exists("User", email):
                m = frappe.new_doc("User")
                m.email = email
                m.first_name = first
                m.last_name = last
                m.send_welcome_email = 0
                m.flags.ignore_permissions = True
                m.flags.ignore_password_policy = True
                m.db_insert()
            else:
                frappe.db.set_value("User", email, "enabled", 1)

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

        for email, first, last in [
            ("test_mentioned_user@example.com", "Test", "Mentioned"),
            ("test_mentioned_user_2@example.com", "Test2", "Mentioned2"),
        ]:
            m_map = frappe.new_doc("Project User Mapping")
            m_map.project = "TMP"
            m_map.user = email
            m_map.employee_name = f"{first} {last}"
            m_map.project_designation = "Member"
            m_map.still_involved = 1
            m_map.insert(ignore_permissions=True)

        # Set Project Documentation Access
        frappe.db.delete("Project Documentation Access", {"project": "TMP"})
        acc = frappe.new_doc("Project Documentation Access")
        acc.project = "TMP"
        acc.user = "test_writer_user@example.com"
        acc.access_level = "Write"
        acc.insert(ignore_permissions=True)

        for email in ("test_mentioned_user@example.com", "test_mentioned_user_2@example.com"):
            m_acc = frappe.new_doc("Project Documentation Access")
            m_acc.project = "TMP"
            m_acc.user = email
            m_acc.access_level = "Read"
            m_acc.insert(ignore_permissions=True)

        _sync_user_wiki_roles("test_pm_user@example.com")
        _sync_user_wiki_roles("test_writer_user@example.com")
        _sync_user_wiki_roles("test_mentioned_user@example.com")
        _sync_user_wiki_roles("test_mentioned_user_2@example.com")

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

    def test_mention_tagging_stored_separately_from_assignment(self):
        cr = self._create_test_cr(
            "CR with Mention",
            description='<p>Check this <span data-type="mention" data-id="test_mentioned_user@example.com" data-label="Test Mentioned">@Test Mentioned</span></p>',
        )

        sync_cr_mention_assignments(cr.name)
        cr.reload()

        # 1. Stored in _user_tags
        tags = [t.strip() for t in (cr.get("_user_tags") or "").split(",") if t.strip()]
        self.assertIn("test_mentioned_user@example.com", tags)

        # 2. NOT in _assign
        raw_assign = cr.get("_assign") or "[]"
        assignees = json.loads(raw_assign) if isinstance(raw_assign, str) else raw_assign
        self.assertNotIn("test_mentioned_user@example.com", assignees)

        # 3. Visible in Tagged to Me filter, but NOT in Assigned to Me filter
        frappe.set_user("test_mentioned_user@example.com")
        tagged_crs = frappe.client.get_list(
            "Wiki Change Request",
            fields=["name", "_user_tags", "_assign", "status"],
            filters={"_user_tags": ["like", "%test_mentioned_user@example.com%"]},
        )
        self.assertIn(cr.name, [c["name"] for c in tagged_crs])

        assigned_crs = frappe.client.get_list(
            "Wiki Change Request",
            fields=["name", "_user_tags", "_assign", "status"],
            filters={
                "_assign": ["like", "%test_mentioned_user@example.com%"],
                "status": ["in", ["In Review", "Approved"]],
            },
        )
        self.assertNotIn(cr.name, [c["name"] for c in assigned_crs])

    def test_multiple_mentions_and_removal(self):
        # 1. Mention two users
        cr = self._create_test_cr(
            "CR with Multiple Mentions",
            description=(
                '<p><span data-type="mention" data-id="test_mentioned_user@example.com" data-label="Test 1">@Test 1</span> '
                'and <span data-type="mention" data-id="test_mentioned_user_2@example.com" data-label="Test 2">@Test 2</span></p>'
            ),
        )
        sync_cr_mention_assignments(cr.name)
        cr.reload()

        tags = [t.strip() for t in (cr.get("_user_tags") or "").split(",") if t.strip()]
        self.assertIn("test_mentioned_user@example.com", tags)
        self.assertIn("test_mentioned_user_2@example.com", tags)

        # 2. Remove mention for user 1, keep user 2
        cr.description = '<p><span data-type="mention" data-id="test_mentioned_user_2@example.com" data-label="Test 2">@Test 2</span></p>'
        cr.save(ignore_permissions=True)
        sync_cr_mention_assignments(cr.name)
        cr.reload()

        tags_after_edit = [t.strip() for t in (cr.get("_user_tags") or "").split(",") if t.strip()]
        self.assertNotIn("test_mentioned_user@example.com", tags_after_edit)
        self.assertIn("test_mentioned_user_2@example.com", tags_after_edit)

        # User 1 no longer sees it in tagged filter
        frappe.set_user("test_mentioned_user@example.com")
        tagged_for_user1 = frappe.client.get_list(
            "Wiki Change Request",
            fields=["name"],
            filters={"_user_tags": ["like", "%test_mentioned_user@example.com%"]},
        )
        self.assertNotIn(cr.name, [c["name"] for c in tagged_for_user1])

        # User 2 still sees it
        frappe.set_user("test_mentioned_user_2@example.com")
        tagged_for_user2 = frappe.client.get_list(
            "Wiki Change Request",
            fields=["name"],
            filters={"_user_tags": ["like", "%test_mentioned_user_2@example.com%"]},
        )
        self.assertIn(cr.name, [c["name"] for c in tagged_for_user2])

        # 3. Remove all mentions
        cr.description = "<p>No mentions anymore</p>"
        cr.save(ignore_permissions=True)
        sync_cr_mention_assignments(cr.name)
        cr.reload()

        tags_cleared = [t.strip() for t in (cr.get("_user_tags") or "").split(",") if t.strip()]
        self.assertEqual(tags_cleared, [])

    def test_tagged_view_across_pending_approved_and_rejected_statuses(self):
        user_email = "test_mentioned_user@example.com"
        mention_html = f'<span data-type="mention" data-id="{user_email}" data-label="Mentioned">@Mentioned</span>'

        # Pending CR
        cr_pending = self._create_test_cr("Pending CR", description=mention_html)
        cr_pending.status = "In Review"
        cr_pending.save(ignore_permissions=True)
        sync_cr_mention_assignments(cr_pending.name)

        # Approved CR
        cr_approved = self._create_test_cr("Approved CR", description=mention_html)
        cr_approved.status = "Approved"
        cr_approved.save(ignore_permissions=True)
        sync_cr_mention_assignments(cr_approved.name)

        # Rejected CR
        cr_rejected = self._create_test_cr("Rejected CR", description=mention_html)
        cr_rejected.status = "Rejected"
        cr_rejected.save(ignore_permissions=True)
        sync_cr_mention_assignments(cr_rejected.name)

        frappe.set_user(user_email)
        tagged_list = frappe.client.get_list(
            "Wiki Change Request",
            fields=["name", "status"],
            filters={"_user_tags": ["like", f"%{user_email}%"]},
        )
        found_names = [c["name"] for c in tagged_list]

        self.assertIn(cr_pending.name, found_names)
        self.assertIn(cr_approved.name, found_names)
        self.assertIn(cr_rejected.name, found_names)

    def test_approved_cr_cleared_assignment_disappears_from_assigned_remains_in_tagged(self):
        user_email = "test_mentioned_user@example.com"
        mention_html = f'<span data-type="mention" data-id="{user_email}" data-label="Mentioned">@Mentioned</span>'

        cr = self._create_test_cr("CR for Approval Test", description=mention_html)
        sync_cr_mention_assignments(cr.name)

        # Explicit reviewer assignment
        from frappe.desk.form.assign_to import add as add_assignment, remove as remove_assignment
        add_assignment({
            "assign_to": [user_email],
            "doctype": "Wiki Change Request",
            "name": cr.name,
        })
        cr.reload()

        # Both assigned and tagged
        frappe.set_user(user_email)
        assigned_list = frappe.client.get_list(
            "Wiki Change Request",
            fields=["name"],
            filters={"_assign": ["like", f"%{user_email}%"], "status": ["in", ["In Review", "Approved"]]},
        )
        tagged_list = frappe.client.get_list(
            "Wiki Change Request",
            fields=["name"],
            filters={"_user_tags": ["like", f"%{user_email}%"]},
        )
        self.assertIn(cr.name, [c["name"] for c in assigned_list])
        self.assertIn(cr.name, [c["name"] for c in tagged_list])

        # Manager approves CR
        frappe.set_user("test_pm_user@example.com")
        pm_only_approve_change_request(cr.name)
        cr.reload()
        self.assertEqual(cr.status, "Approved")

        # Assignment is cleared (reviewer finished review)
        remove_assignment("Wiki Change Request", cr.name, user_email)
        cr.reload()

        # Verify: Disappeared from Assigned to Me, but remains visible in Tagged to Me
        frappe.set_user(user_email)
        assigned_list_after = frappe.client.get_list(
            "Wiki Change Request",
            fields=["name"],
            filters={"_assign": ["like", f"%{user_email}%"], "status": ["in", ["In Review", "Approved"]]},
        )
        tagged_list_after = frappe.client.get_list(
            "Wiki Change Request",
            fields=["name"],
            filters={"_user_tags": ["like", f"%{user_email}%"]},
        )
        self.assertNotIn(cr.name, [c["name"] for c in assigned_list_after])
        self.assertIn(cr.name, [c["name"] for c in tagged_list_after])

    def test_tagged_user_permissions_enforced(self):
        user_email = "test_mentioned_user@example.com"
        mention_html = f'<span data-type="mention" data-id="{user_email}" data-label="Mentioned">@Mentioned</span>'
        cr = self._create_test_cr("CR for Permissions Test", description=mention_html)
        sync_cr_mention_assignments(cr.name)

        # Tagged user with project space access can read the CR
        frappe.set_user(user_email)
        can_read = frappe.has_permission("Wiki Change Request", "read", doc=cr, user=user_email)
        self.assertTrue(can_read)

        # Unrelated user without project space access CANNOT read the CR, even if mentioned
        unrelated_email = "unrelated_user@example.com"
        cr_unrelated = self._create_test_cr(
            "CR Unrelated Mention",
            description=f'<span data-type="mention" data-id="{unrelated_email}" data-label="Unrelated">@Unrelated</span>',
        )
        sync_cr_mention_assignments(cr_unrelated.name)

        frappe.set_user(unrelated_email)
        can_unrelated_read = frappe.has_permission("Wiki Change Request", "read", doc=cr_unrelated, user=unrelated_email)
        self.assertFalse(can_unrelated_read)

    def test_mention_notification_sent_on_tagging(self):
        user_email = "test_mentioned_user@example.com"
        frappe.db.delete("Notification Log", {"for_user": user_email})

        mention_html = f'<span data-type="mention" data-id="{user_email}" data-label="Mentioned">@Mentioned</span>'
        cr = self._create_test_cr("CR for Notification Test", description=mention_html)
        sync_cr_mention_assignments(cr.name)

        # Verify Notification Log was created for the tagged user
        notif = frappe.db.get_value(
            "Notification Log",
            {
                "for_user": user_email,
                "document_type": "Wiki Change Request",
                "document_name": cr.name,
                "type": "Mention",
            },
            ["name", "subject", "link"],
            as_dict=True,
        )
        self.assertIsNotNone(notif)
        self.assertIn("tagged you in Change Request", notif["subject"])
        self.assertEqual(notif["link"], f"/wiki-app/change-requests/{cr.name}")

        # Re-saving without changing mentions should NOT duplicate the notification
        count_before = frappe.db.count("Notification Log", {"for_user": user_email, "document_name": cr.name})
        sync_cr_mention_assignments(cr.name)
        count_after = frappe.db.count("Notification Log", {"for_user": user_email, "document_name": cr.name})
        self.assertEqual(count_before, count_after)

    def test_wiki_notifications_api(self):
        from wiki.api import get_wiki_notifications, mark_wiki_notification_as_read

        user_email = "test_mentioned_user@example.com"
        frappe.db.delete("Notification Log", {"for_user": user_email})

        mention_html = f'<span data-type="mention" data-id="{user_email}" data-label="Mentioned">@Mentioned</span>'
        cr = self._create_test_cr("CR for Wiki Notification API Test", description=mention_html)
        sync_cr_mention_assignments(cr.name)

        frappe.set_user(user_email)
        res = get_wiki_notifications()
        self.assertGreaterEqual(res["unread_count"], 1)
        self.assertGreaterEqual(res["tagged_count"], 1)
        self.assertTrue(any(n["document_name"] == cr.name for n in res["notifications"]))

        # Mark single notification as read
        notif_item = next(n for n in res["notifications"] if n["document_name"] == cr.name)
        mark_res = mark_wiki_notification_as_read(notif_item["name"])
        self.assertTrue(mark_res["success"])

        # Reload notifications
        res_after = get_wiki_notifications()
        updated_item = next(n for n in res_after["notifications"] if n["name"] == notif_item["name"])
        self.assertTrue(updated_item["read"])

