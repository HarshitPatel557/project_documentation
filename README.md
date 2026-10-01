# Promot Wiki — Document Management System

A Frappe-based document management and project documentation system that integrates **Promot**, **Frappe Wiki**, and the custom **Project Documentation** application.

---

## Technology Stack

* **Frappe Framework:** v15
* **Frappe Wiki:** Custom Wiki application
* **Project Documentation:** Custom Frappe application
* **Promot:** Project and user management
* **Database:** MariaDB
* **Backend:** Python / Frappe Framework

---

# Installation & Setup

## 1. Initialize Frappe Bench

Create a new Frappe Bench using Frappe v15:

```bash
bench init project_wiki --frappe-branch version-15
```

Enter the newly created Bench:

```bash
cd project_wiki
```

> All subsequent Bench commands should be executed from the `project_wiki` directory.

---

## 2. Create Frappe Site

Create the site that will host Promot Wiki:

```bash
bench new-site promot_wiki.local
```

During site creation, Frappe will ask for:

* MariaDB root password
* Administrator password

---

## 3. Get Required Applications

### 3.1 Get Wiki

Clone the Wiki application from the `develop` branch:

```bash
bench get-app --branch develop https://github.com/HarshitPatel557/wiki.git
```

### 3.2 Get Project Documentation

Clone the Project Documentation application:

```bash
bench get-app --branch develop https://github.com/HarshitPatel557/project_documentation.git
```

After downloading the applications, the Bench structure will look approximately like:

```text
project_wiki/
├── apps/
│   ├── frappe/
│   ├── wiki/
│   └── project_documentation/
├── sites/
│   └── promot_wiki.local/
└── ...
```

---

## 4. Set the Default Site

Set `promot_wiki.local` as the default site:

```bash
bench use promot_wiki.local
```

Verify the selected site if required:

```bash
bench use
```

---

# 5. Configure Promot API

Open the site configuration file:

```bash
nano sites/promot_wiki.local/site_config.json
```

Add the required Promot configuration:

```json
{
    "promot_api_key": "sk-proj-.....",
    "promot_api_url": "https://...../NextAPI/get_userdetails",
    "server_script_enabled": true
}
```

> **Important:** Do not remove the existing Frappe configuration values from `site_config.json`. Add the Promot configuration alongside the existing settings.

### Security

Never commit the actual Promot API key to Git.

Use a placeholder in documentation:

```text
sk-proj-.....
```

Keep the actual API key only in the local/server `site_config.json`.

---

# 6. Install Applications

Install the Project Documentation application:

```bash
bench --site promot_wiki.local install-app project_documentation
```

Install the Wiki application:

```bash
bench --site promot_wiki.local install-app wiki
```

Verify the installed applications:

```bash
bench --site promot_wiki.local list-apps
```

Expected applications:

```text
frappe
wiki
project_documentation
```

---

# 7. Run Database Migration

Run the Frappe database migration:

```bash
bench --site promot_wiki.local migrate
```

This ensures that the required DocTypes, database tables, roles, and application changes are synchronized with the site.

---

# 8. Build Frontend Assets

Build the application assets:

```bash
bench build
```

---

# 9. Start Frappe Bench

Start the development server:

```bash
bench start
```

Keep this terminal running.

Open a **second terminal** for the Promot synchronization.

---

# 10. Run Promot Synchronization

In the second terminal, navigate to the Bench:

```bash
cd ~/project_wiki
```

Open the Frappe console:

```bash
bench --site promot_wiki.local console
```

Run the Promot synchronization:

```python
from project_documentation.api.promot_sync import run_sync

result = run_sync()

print(result)
```

The synchronization imports/synchronizes the required Promot data into the Project Documentation application.

Conceptually:

```text
                    PROMOT
                       │
                       │ API
                       ▼
             Promot Synchronization
                       │
                       ▼
              Project Documentation
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
        Users       Projects    User Mapping
```

---

# 11. Verify Project Documentation Roles

While inside the Frappe console, verify that the required roles exist:

```python
frappe.get_all(
    "Role",
    filters={
        "name": [
            "in",
            [
                "Project Documentation Manager",
                "Project Documentation Reader",
                "Project Documentation Writer"
            ]
        ]
    },
    pluck="name"
)
```

Expected result:

```python
[
    "Project Documentation Manager",
    "Project Documentation Reader",
    "Project Documentation Writer"
]
```

Exit the Frappe console:

```python
exit()
```

---

# 12. Clear Cache

Clear the Frappe cache:

```bash
bench --site promot_wiki.local clear-cache
```

Clear the website cache:

```bash
bench --site promot_wiki.local clear-website-cache
```

---

# 13. Restart Bench

For a development environment running with `bench start`, stop the existing process using:

```text
Ctrl + C
```

Then start it again:

```bash
bench start
```

For a production/supervisor-managed environment:

```bash
bench restart
```

---

# Complete Installation Commands

The complete installation sequence is:

```bash
# 1. Initialize Frappe v15 Bench
bench init project_wiki --frappe-branch version-15

# 2. Enter Bench
cd project_wiki

# 3. Create Site
bench new-site promot_wiki.local

# 4. Get Wiki
bench get-app --branch develop https://github.com/HarshitPatel557/wiki.git

# 5. Get Project Documentation
bench get-app --branch develop https://github.com/HarshitPatel557/project_documentation.git

# 6. Set Default Site
bench use promot_wiki.local

# 7. Configure Promot API
nano sites/promot_wiki.local/site_config.json

# 8. Install Project Documentation
bench --site promot_wiki.local install-app project_documentation

# 9. Install Wiki
bench --site promot_wiki.local install-app wiki

# 10. Run Migration
bench --site promot_wiki.local migrate

# 11. Build Assets
bench build

# 12. Start Bench
bench start
```

Then, from a second terminal:

```bash
cd ~/project_wiki

# Open Frappe Console
bench --site promot_wiki.local console
```

Inside the console:

```python
from project_documentation.api.promot_sync import run_sync

result = run_sync()

print(result)

frappe.get_all(
    "Role",
    filters={
        "name": [
            "in",
            [
                "Project Documentation Manager",
                "Project Documentation Reader",
                "Project Documentation Writer"
            ]
        ]
    },
    pluck="name"
)

exit()
```

Finally:

```bash
# Clear cache
bench --site promot_wiki.local clear-cache

# Clear website cache
bench --site promot_wiki.local clear-website-cache
```

For development:

```bash
bench start
```

For a production/supervisor setup:

```bash
bench restart
```

---

# Project Structure

After installation, the main Bench structure is:

```text
project_wiki/
│
├── apps/
│   ├── frappe/
│   ├── wiki/
│   └── project_documentation/
│
├── sites/
│   ├── apps.txt
│   ├── common_site_config.json
│   └── promot_wiki.local/
│       ├── site_config.json
│       └── ...
│
└── ...
```

---

# Application Architecture

```text
                         ┌─────────────────────┐
                         │       PROMOT        │
                         │                     │
                         │ Users               │
                         │ Projects            │
                         │ Project/User Mapping│
                         └──────────┬──────────┘
                                    │
                                    │ API
                                    ▼
                         ┌─────────────────────┐
                         │ Promot Synchronizer │
                         └──────────┬──────────┘
                                    │
                                    ▼
                  ┌────────────────────────────────┐
                  │      Project Documentation      │
                  │                                │
                  │ Projects                       │
                  │ User Mapping                   │
                  │ Access Control                 │
                  │ Project Permissions            │
                  │ Roles                           │
                  └───────────────┬────────────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │   Frappe Wiki   │
                         │                  │
                         │ Wiki Spaces      │
                         │ Documents        │
                         │ Revisions        │
                         │ Publishing       │
                         └──────────────────┘
```

---

# Troubleshooting

### Check installed applications

```bash
bench --site promot_wiki.local list-apps
```

### Check Bench version

```bash
bench version
```

### Run migration

```bash
bench --site promot_wiki.local migrate
```

### Clear cache

```bash
bench --site promot_wiki.local clear-cache
bench --site promot_wiki.local clear-website-cache
```

### Open Frappe console

```bash
bench --site promot_wiki.local console
```

### Check current site

```bash
bench use
```

### Rebuild assets

```bash
bench build
```

### Start development server

```bash
bench start
```

---

# Security Notes

* Never commit the actual Promot API key to Git.
* Do not share `site_config.json` containing production credentials.
* Store API credentials in the site's configuration/environment-specific secret storage.
* Use HTTPS for production deployments.
* Use a production deployment configuration rather than `bench start` for production servers.

---

# Summary

The setup consists of three major components:

```text
Promot
   │
   │ API Synchronization
   ▼
Project Documentation
   │
   │ Project / User Access Control
   ▼
Frappe Wiki
   │
   ▼
Project Documentation & Knowledge Base
```

The **Project Documentation** application acts as the project-management and access-control layer, while **Frappe Wiki** provides the documentation and content-management functionality.
















### Project Documentation

Project for documentation

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app project_documentation
```

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/project_documentation
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### CI

This app can use GitHub Actions for CI. The following workflows are configured:

- CI: Installs this app and runs unit tests on every push to `develop` branch.
- Linters: Runs [Frappe Semgrep Rules](https://github.com/frappe/semgrep-rules) and [pip-audit](https://pypi.org/project/pip-audit/) on every pull request.


### License

mit
