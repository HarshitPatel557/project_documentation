import frappe
from frappe.tests.utils import FrappeTestCase
from project_documentation.api.user_search import search_mention_users


class TestUserSearch(FrappeTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")

        # Create test users
        if not frappe.db.exists("User", "test_pm_member1@example.com"):
            user1 = frappe.new_doc("User")
            user1.email = "test_pm_member1@example.com"
            user1.first_name = "Harshit"
            user1.last_name = "Patel"
            user1.send_welcome_email = 0
            user1.flags.ignore_permissions = True
            user1.flags.ignore_password_policy = True
            user1.db_insert()
        else:
            frappe.db.set_value("User", "test_pm_member1@example.com", {"first_name": "Harshit", "last_name": "Patel", "enabled": 1})

        if not frappe.db.exists("User", "test_pm_member2@example.com"):
            user2 = frappe.new_doc("User")
            user2.email = "test_pm_member2@example.com"
            user2.first_name = "Harish"
            user2.last_name = "Sharma"
            user2.send_welcome_email = 0
            user2.flags.ignore_permissions = True
            user2.flags.ignore_password_policy = True
            user2.db_insert()
        else:
            frappe.db.set_value("User", "test_pm_member2@example.com", {"first_name": "Harish", "last_name": "Sharma", "enabled": 1})

        if not frappe.db.exists("User", "test_other_user@example.com"):
            user3 = frappe.new_doc("User")
            user3.email = "test_other_user@example.com"
            user3.first_name = "Harendra"
            user3.last_name = "Singh"
            user3.custom_designation = "DBA"
            user3.send_welcome_email = 0
            user3.flags.ignore_permissions = True
            user3.flags.ignore_password_policy = True
            user3.db_insert()
        else:
            frappe.db.set_value("User", "test_other_user@example.com", {"first_name": "Harendra", "last_name": "Singh", "custom_designation": "DBA", "enabled": 1})


        # Create or find test Wiki Space
        existing_space = frappe.db.get_value("Wiki Space", {"route": "test-mention-space"}, "name")
        if not existing_space:
            space = frappe.new_doc("Wiki Space")
            space.space_name = "Test Mention Space"
            space.route = "test-mention-space"
            space.insert(ignore_permissions=True)
            self.space_name = space.name
        else:
            self.space_name = existing_space


        # Create test Project Documentation Project
        self.project_name = "PROJ-TEST-MENTION-001"
        if not frappe.db.exists("Project Documentation Project", self.project_name):
            proj = frappe.new_doc("Project Documentation Project")
            proj.project_code = self.project_name
            proj.project_name = "Test Mention Project"
            proj.wiki_space = self.space_name
            proj.is_active = 1
            proj.insert(ignore_permissions=True)
        else:
            frappe.db.set_value(
                "Project Documentation Project",
                self.project_name,
                {"wiki_space": self.space_name, "is_active": 1},
            )

        # Create Project User Mappings
        frappe.db.delete("Project User Mapping", {"project": self.project_name})

        mapping1 = frappe.new_doc("Project User Mapping")
        mapping1.project = self.project_name
        mapping1.user = "test_pm_member1@example.com"
        mapping1.employee_name = "Harshit Patel"
        mapping1.project_designation = "Developer"
        mapping1.still_involved = 1
        mapping1.insert(ignore_permissions=True)

        mapping2 = frappe.new_doc("Project User Mapping")
        mapping2.project = self.project_name
        mapping2.user = "test_pm_member2@example.com"
        mapping2.employee_name = "Harish Sharma"
        mapping2.project_designation = "Tech Lead"
        mapping2.still_involved = 1
        mapping2.insert(ignore_permissions=True)

    def test_search_mention_users_ranks_project_members_first(self):
        results = search_mention_users(query="har", space=self.space_name, limit=20)
        self.assertTrue(len(results) >= 3)

        # First entries must be Project Members
        pm_results = [r for r in results if r["is_project_member"]]
        other_results = [r for r in results if not r["is_project_member"]]

        self.assertEqual(len(pm_results), 2)
        self.assertEqual(pm_results[0]["group"], "PROJECT MEMBERS")
        self.assertEqual(pm_results[0]["label"], "Harish Sharma")
        self.assertEqual(pm_results[0]["designation"], "Tech Lead")

        self.assertEqual(pm_results[1]["group"], "PROJECT MEMBERS")
        self.assertEqual(pm_results[1]["label"], "Harshit Patel")
        self.assertEqual(pm_results[1]["designation"], "Developer")

        # Non project members come after
        other_labels = [r["label"] for r in other_results]
        self.assertIn("Harendra Singh", other_labels)

        # Verify order in results list: all project members come before all other users
        pm_indices = [i for i, r in enumerate(results) if r["is_project_member"]]
        other_indices = [i for i, r in enumerate(results) if not r["is_project_member"]]
        self.assertTrue(max(pm_indices) < min(other_indices))

    def test_search_mention_users_designation_filtering(self):
        results = search_mention_users(query="DBA", space=self.space_name, limit=10)
        labels = [r["label"] for r in results]
        self.assertIn("Harendra Singh", labels)

    def test_search_mention_users_guest_blocked(self):
        frappe.set_user("Guest")
        results = search_mention_users(query="har", space=self.space_name, limit=10)
        self.assertEqual(results, [])
