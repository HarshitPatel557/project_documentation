# Promot Wiki — Project Documentation & Access Control

A custom Frappe v15 application that acts as the access management, SSO bridge, and project synchronization layer connecting **Promot** with **Frappe Wiki**.

---

## Overview

**Project Documentation** manages multi-project permissions, role mappings, single sign-on (SSO), and collaborative document workflows:

- **Promot Synchronization**: Ingests projects, members, and designation assignments from the Promot central platform via API.
- **Dynamic Access Control**: Automatically maps project designations to granular Wiki roles (`Manager`, `Writer`, `Reviewer`, `Reader`) with strict project isolation.
- **Dual-Mode SSO Authentication**: Seamless login from Promot supporting both **AES-256-GCM** encrypted tokens and **RS256 JWT** public-key signatures.
- **Mention & Notification Engine**: Extracts `@mentions` across Wiki Documents and Change Requests, auto-provisions view access to tagged users (`_user_tags`), and sends real-time in-app notifications.

---

## System Architecture

```text
                     ┌─────────────────────────────┐
                     │           PROMOT            │
                     │  (Users, Projects, Mappings)│
                     └──────────────┬──────────────┘
                                    │
                         REST API / SSO Token
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │             PROJECT DOCUMENTATION APP                   │
       │                                                         │
       │  • Promot Sync Service    • Role & Permission Sync     │
       │  • Dual-Mode SSO (AES/RS) • Mentions & User Tagging    │
       │  • PM Project Dashboard   • Notification Log & Events   │
       └────────────────────────────┬────────────────────────────┘
                                    │
                           Role & Space Binding
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │                    FRAPPE WIKI                          │
       │                                                         │
       │  • Wiki Spaces            • Change Requests (PR Flow)   │
       │  • Document Publishing    • In-App Notification Bell    │
       └─────────────────────────────────────────────────────────┘
```

---

## Technology Stack

- **Framework**: Frappe Framework v15
- **Language**: Python 3.10+ / JavaScript / Vue 3
- **Database**: MariaDB 10.6+
- **Companion Apps**: Frappe Wiki (`apps/wiki`), Frappe Core (`apps/frappe`)

---

## Installation & Setup

### 1. Initialize Bench & Create Site (New Setup)

If starting from a fresh environment:

```bash
# Initialize Frappe v15 Bench
bench init project_wiki --frappe-branch version-15
cd project_wiki

# Create Frappe site
bench new-site promot_wiki.local

# Set as default site
bench use promot_wiki.local
```

> If you already have an existing bench, navigate to your bench directory and ensure your active site is selected.

---

### 2. Fetch Applications

Clone the **Frappe Wiki** and **Project Documentation** applications into the bench:

```bash
# Clone Wiki
bench get-app --branch develop https://github.com/HarshitPatel557/wiki.git

# Clone Project Documentation
bench get-app --branch develop https://github.com/HarshitPatel557/project_documentation.git
```

---

### 3. Configure Site Settings (`site_config.json`)

Edit `sites/promot_wiki.local/site_config.json` to include the required API and SSO configurations:

```bash
nano sites/promot_wiki.local/site_config.json
```

Add your configuration keys alongside the existing Frappe settings:

```json
{
    "promot_api_key": "sk-proj-YOUR_API_KEY",
    "promot_api_url": "https://your-promot-domain.gov.in/NextAPI/get_userdetails",
    "sso_aes_key": "YOUR_32_BYTE_HEX_OR_BASE64_KEY",
    "sso_public_key": "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A...\n-----END PUBLIC KEY-----",
    "host_name": "http://127.0.0.1:8002",
    "server_script_enabled": true
}
```

> **Security Note**: Never commit actual API keys or private credentials to version control. Keep secrets in `site_config.json`.

---

### 4. Install Apps & Migrate Database

Install both applications and run migrations to create the required DocTypes and roles:

```bash
# Install applications
bench --site promot_wiki.local install-app project_documentation
bench --site promot_wiki.local install-app wiki

# Run database migrations
bench --site promot_wiki.local migrate

# Build frontend assets
bench build
```

---

### 5. Synchronize Promot Data

Execute the synchronization command to import projects, users, and mappings from Promot:

```bash
bench --site promot_wiki.local execute project_documentation.api.promot_sync.run_sync
```

This synchronizes:
- Promot users into the local `User` directory.
- Projects into `Project Documentation Project`.
- Team mappings into `Project User Mapping`.
- Role assignments (`Project Documentation Manager`, `Writer`, `Reader`, and Wiki roles).

---

### 6. Clear Cache & Start Bench

Clear the site cache and start the server:

```bash
bench --site promot_wiki.local clear-cache
bench --site promot_wiki.local clear-website-cache
bench start
```

For production environments managed by Supervisor/Systemd:

```bash
bench restart
```

---

## Key Features & Capabilities

### 1. Dual Token SSO (`api/auth.py`)
Allows users to seamlessly transition from Promot into the Wiki workspace using either:
- **AES-256-GCM Payload**: Encrypted user token decrypted locally via `sso_aes_key`.
- **RS256 JWT**: Cryptographically signed token verified using the Promot `sso_public_key`.

Tokens create an authenticated Frappe web session and redirect the user directly to `/wiki-app/`.

### 2. Mentions & User Tagging (`api/project_access.py`)
- Automatically detects `@username` mentions in Wiki Documents and Change Request descriptions.
- Tagged users are recorded in the `_user_tags` field.
- Generates a `Notification Log` for the recipient with a direct Wiki link (`/wiki-app/change-requests/<id>`).
- Emits real-time `wiki_mention` events over WebSockets to trigger live badges and toasts in the Wiki UI.

### 3. Role Hierarchy & Project Isolation

| Role | Permissions |
|---|---|
| **Project Documentation Manager** | Full administration over project Wiki spaces; can review, approve, and merge Change Requests. |
| **Project Documentation Writer** | Can create and edit Wiki pages and draft Change Requests within their assigned projects. |
| **Project Documentation Reader** | Read-only access to published project documentation and assigned reviews. |
| **Tagged User** | Granted scoped read access to Change Requests in which they are explicitly mentioned. |

---

## Running Automated Tests

Run the test suite to verify permissions, user tagging, role synchronization, and notification workflows:

```bash
bench --site promot_wiki.local run-tests --module project_documentation.tests.test_mention_and_cr_access
```

---

## Helpful Commands

```bash
# Check installed apps
bench --site promot_wiki.local list-apps

# Re-run Promot sync on demand
bench --site promot_wiki.local execute project_documentation.api.promot_sync.run_sync

# Clear application and website cache
bench --site promot_wiki.local clear-cache && bench --site promot_wiki.local clear-website-cache

# Run database migrations after code updates
bench --site promot_wiki.local migrate

# Rebuild frontend bundles
bench build
```

---

## License

MIT
