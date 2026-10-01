app_name = "project_documentation"
app_title = "Project Documentation"
app_publisher = "Harshit"
app_description = "Project Documentation Management System"
app_email = "patelharshithp404@gmail.com"
app_license = "mit"

# Import API modules at app hook load time so their @frappe.whitelist
# decorators are registered in every Frappe web worker before RPC
# permission checks run. This is required for custom RPC methods because
# Frappe validates the whitelist before executing the requested method.
from project_documentation.api import auth as _auth_api  # noqa: F401
from project_documentation.api import project_access as _project_access_api  # noqa: F401
from project_documentation.api import user_search as _user_search_api  # noqa: F401



permission_query_conditions = {
    "Wiki Space": [
        "project_documentation.api.project_access.wiki_space_project_query_conditions",
    ],
    "Wiki Document": [
        "project_documentation.api.project_access.wiki_document_project_query_conditions",
    ],
    "Wiki Change Request": [
        "project_documentation.api.project_access.wiki_change_request_project_query_conditions",
    ],
}

has_permission = {
    "Wiki Space": [
        "project_documentation.api.project_access.wiki_space_has_permission",
    ],
    "Wiki Document": [
        "project_documentation.api.project_access.wiki_document_has_permission",
    ],
    "Wiki Change Request": [
        "project_documentation.api.project_access.wiki_change_request_has_permission",
    ],
}

doc_events = {
    "Wiki Change Request": {
        "on_update": "project_documentation.api.project_access.sync_cr_mention_assignments",
    },
}

scheduler_events = {
    "hourly": [
        "project_documentation.api.promot_sync.run_sync",
        "project_documentation.api.wiki_provisioning.queue_missing_wiki_spaces",
    ],
}

# After installation/migration, queue provisioning for any active projects
# already present in the database. The job is idempotent.
after_migrate = "project_documentation.api.wiki_provisioning.queue_missing_wiki_spaces"


override_whitelisted_methods = {
    "wiki.frappe_wiki.doctype.wiki_change_request.wiki_change_request.approve_change_request":
        "project_documentation.api.project_access.pm_only_approve_change_request",
    "wiki.frappe_wiki.doctype.wiki_change_request.wiki_change_request.request_changes":
        "project_documentation.api.project_access.pm_only_request_changes",
    "wiki.frappe_wiki.doctype.wiki_change_request.wiki_change_request.reject_change_request":
        "project_documentation.api.project_access.pm_only_reject_change_request",
    "wiki.frappe_wiki.doctype.wiki_change_request.wiki_change_request.merge_change_request":
        "project_documentation.api.project_access.pm_only_merge_change_request",
    "wiki.frappe_wiki.doctype.wiki_change_request.wiki_change_request.get_merge_conflicts":
        "project_documentation.api.project_access.pm_only_get_merge_conflicts",
    "wiki.frappe_wiki.doctype.wiki_change_request.wiki_change_request.resolve_merge_conflict":
        "project_documentation.api.project_access.pm_only_resolve_merge_conflict",
    "wiki.frappe_wiki.doctype.wiki_change_request.wiki_change_request.retry_merge_after_resolution":
        "project_documentation.api.project_access.pm_only_retry_merge_after_resolution",
    "wiki.api.get_space_capabilities":
        "project_documentation.api.project_access.custom_get_space_capabilities",
    "wiki.api.get_user_info":
        "project_documentation.api.project_access.custom_get_user_info",
}

fixtures = [
    {
        "dt": "Custom Field",
        "filters": [
            ["dt", "=", "User"],
            [
                "fieldname",
                "in",
                [
                    "custom_external_user_id",
                    "custom_external_employee_id",
                    "custom_designation",
                ],
            ],
        ],
    },
    {
        "dt": "Client Script",
        "filters": [
            ["name", "=", "project_documentation_project"]
        ],
    },
    {
        "dt": "Custom DocPerm",
        "filters": [
            [
                "parent",
                "in",
                [
                    "Wiki Space",
                    "Wiki Document",
                    "Wiki Change Request",
                    "Wiki Revision",
                    "Wiki Revision Item",
                    "Wiki Content Blob",
                    "Wiki Settings",
                ],
            ]
        ],
    },
    {
        "dt": "Role",
        "filters": [
            ["name", "in", [
                "Project Documentation Manager",
                "Project Documentation Reader",
                "Project Documentation Writer"
            ]]
        ]
    }
]