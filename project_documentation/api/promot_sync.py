import frappe

from project_documentation.api.user_sync import sync_users
from project_documentation.api.project_sync import sync_projects
from project_documentation.api.mapping_sync import sync_mappings


SYNC_LOCK_KEY = "promot_sync_running"
SYNC_LOCK_TIMEOUT = 60 * 60  # 1 hour


def is_sync_running():
    """Return True when another PROMOT sync is currently running."""
    return frappe.cache().get_value(SYNC_LOCK_KEY) == "1"


def acquire_sync_lock():
    """
    Acquire the PROMOT synchronization lock.

    Returns False when another sync is already running.
    """
    if is_sync_running():
        return False

    frappe.cache().set_value(
        SYNC_LOCK_KEY,
        "1",
        expires_in_sec=SYNC_LOCK_TIMEOUT,
    )

    return True


def release_sync_lock():
    """Release the PROMOT synchronization lock."""
    frappe.cache().delete_value(SYNC_LOCK_KEY)


def build_result(dry_run):
    return {
        "dry_run": dry_run,
        "status": "STARTED",
        "users": None,
        "projects": None,
        "mappings": None,
        "overall": {
            "failed": 0,
            "stopped": False,
            "stop_reason": None,
        },
    }


def sync_all(
    dry_run=True,
    user_limit=None,
    project_limit=None,
    mapping_limit=None,
):
    """
    Synchronize all PROMOT data in dependency order:

        Users
          ↓
        Projects
          ↓
        Project User Mappings

    Safety features:
    - Prevents overlapping PROMOT sync jobs.
    - Stops dependent syncs when Users or Projects fail.
    - Always releases the synchronization lock.
    - Supports dry-run mode.
    """

    # =========================================================
    # ACQUIRE LOCK
    # =========================================================

    if not acquire_sync_lock():
        frappe.logger().warning(
            "PROMOT sync skipped because another sync is already running."
        )

        return {
            "dry_run": dry_run,
            "status": "SKIPPED",
            "users": None,
            "projects": None,
            "mappings": None,
            "overall": {
                "failed": 0,
                "stopped": True,
                "stop_reason": (
                    "Another PROMOT synchronization is already running."
                ),
            },
        }

    result = build_result(dry_run)

    try:
        # =====================================================
        # 1. USERS
        # =====================================================

        frappe.logger().info(
            f"PROMOT sync started - Users (dry_run={dry_run})"
        )

        try:
            users_result = sync_users(
                dry_run=dry_run,
                limit=user_limit,
            )

            result["users"] = users_result

        except Exception:
            error = frappe.get_traceback()

            frappe.log_error(
                error,
                "PROMOT User Sync Failed",
            )

            result["users"] = {
                "failed": 1,
                "error": error,
            }

            result["overall"]["failed"] += 1
            result["overall"]["stopped"] = True
            result["overall"]["stop_reason"] = (
                "User synchronization raised an unexpected exception. "
                "Project and mapping synchronization was not started."
            )
            result["status"] = "FAILED"

            return result

        # -----------------------------------------------------
        # Stop if User sync has failures
        # -----------------------------------------------------

        user_failures = users_result.get("failed", 0)

        if user_failures:
            result["overall"]["failed"] += user_failures
            result["overall"]["stopped"] = True
            result["overall"]["stop_reason"] = (
                f"User synchronization reported "
                f"{user_failures} failure(s). "
                "Project and mapping synchronization was not started."
            )
            result["status"] = "FAILED"

            frappe.logger().error(
                result["overall"]["stop_reason"]
            )

            return result

        # =====================================================
        # 2. PROJECTS
        # =====================================================

        frappe.logger().info(
            f"PROMOT sync started - Projects (dry_run={dry_run})"
        )

        try:
            projects_result = sync_projects(
                dry_run=dry_run,
                limit=project_limit,
            )

            result["projects"] = projects_result

        except Exception:
            error = frappe.get_traceback()

            frappe.log_error(
                error,
                "PROMOT Project Sync Failed",
            )

            result["projects"] = {
                "failed": 1,
                "error": error,
            }

            result["overall"]["failed"] += 1
            result["overall"]["stopped"] = True
            result["overall"]["stop_reason"] = (
                "Project synchronization raised an unexpected exception. "
                "Mapping synchronization was not started."
            )
            result["status"] = "FAILED"

            return result

        # -----------------------------------------------------
        # Stop if Project sync has failures
        # -----------------------------------------------------

        project_failures = projects_result.get("failed", 0)

        if project_failures:
            result["overall"]["failed"] += project_failures
            result["overall"]["stopped"] = True
            result["overall"]["stop_reason"] = (
                f"Project synchronization reported "
                f"{project_failures} failure(s). "
                "Mapping synchronization was not started."
            )
            result["status"] = "FAILED"

            frappe.logger().error(
                result["overall"]["stop_reason"]
            )

            return result

        # =====================================================
        # 3. PROJECT USER MAPPINGS
        # =====================================================

        frappe.logger().info(
            f"PROMOT sync started - Mappings (dry_run={dry_run})"
        )

        try:
            mappings_result = sync_mappings(
                dry_run=dry_run,
                limit=mapping_limit,
            )

            result["mappings"] = mappings_result

        except Exception:
            error = frappe.get_traceback()

            frappe.log_error(
                error,
                "PROMOT Mapping Sync Failed",
            )

            result["mappings"] = {
                "failed": 1,
                "error": error,
            }

            result["overall"]["failed"] += 1
            result["overall"]["stopped"] = True
            result["overall"]["stop_reason"] = (
                "Project User Mapping synchronization "
                "raised an unexpected exception."
            )
            result["status"] = "FAILED"

            return result

        # =====================================================
        # FINAL SUMMARY
        # =====================================================

        mapping_failures = mappings_result.get("failed", 0)

        result["overall"]["failed"] += mapping_failures

        if mapping_failures:
            result["status"] = "FAILED"
            result["overall"]["stopped"] = False
            result["overall"]["stop_reason"] = (
                f"Mapping synchronization reported "
                f"{mapping_failures} failure(s)."
            )
        else:
            result["status"] = "SUCCESS"

        frappe.logger().info(
            "PROMOT sync completed - "
            f"status={result['status']}, "
            f"failed={result['overall']['failed']}"
        )

        # Wiki Spaces are provisioned asynchronously after the complete
        # Users -> Projects -> Mappings sync succeeds. This keeps the PROMOT
        # synchronization request fast while ensuring every active project
        # receives a Wiki Space by default.
        if not dry_run and result["status"] == "SUCCESS":
            from project_documentation.api.wiki_provisioning import (
                queue_missing_wiki_spaces,
            )

            result["wiki_provisioning"] = queue_missing_wiki_spaces()
        return result

    finally:
        # =====================================================
        # ALWAYS RELEASE LOCK
        # =====================================================

        release_sync_lock()

        frappe.logger().info(
            "PROMOT synchronization lock released."
        )


@frappe.whitelist()
def dry_run_sync(
    user_limit=None,
    project_limit=None,
    mapping_limit=None,
):
    """
    Run a complete PROMOT synchronization as a dry run.
    No database changes are made.
    """

    return sync_all(
        dry_run=True,
        user_limit=user_limit,
        project_limit=project_limit,
        mapping_limit=mapping_limit,
    )


@frappe.whitelist()
def run_sync(
    user_limit=None,
    project_limit=None,
    mapping_limit=None,
):
    """
    Run a complete PROMOT synchronization.
    """

    return sync_all(
        dry_run=False,
        user_limit=user_limit,
        project_limit=project_limit,
        mapping_limit=mapping_limit,
    )