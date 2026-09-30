import frappe


def execute():
    """
    Queue automatic Wiki Space provisioning for active projects that do not
    yet have a linked Wiki Space.

    The patch only queues the background operation; it does not create Wiki
    records during migration.
    """
    from project_documentation.api.wiki_provisioning import (
        queue_missing_wiki_spaces,
    )

    queue_missing_wiki_spaces()
