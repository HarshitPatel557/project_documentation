# Project Documentation v5

## Fixes in this version

- PM Wiki role assignment no longer calls `User.save()` / `User.add_roles()`.
- Native Wiki roles and Project Documentation marker roles are assigned through `Has Role` with `ignore_permissions=True` after project-level authorization.
- User role caches are cleared after role changes.
- Wiki Space initialization remains entirely inside `project_documentation`; the Wiki app is not modified.
- PMs can initialize/open their project Wiki Space.
- Non-PMs are redirected to `/wiki-app/spaces/`.
- Team Access now includes a **Save All** button.
- Individual Save buttons remain available.
- Project selection smoothly scrolls to the selected project.
- Project Wiki links use `/wiki-app/spaces/<space-id>`.

## Install

```bash
cd ~/frappe-test
bench --site mysite.local migrate
bench --site mysite.local clear-cache
bench build --app project_documentation
bench restart
```

Then log in again through SSO and test `/project-documentation`.


## Access model in v6
- Project Documentation Reader: native read permission for Wiki Space and Wiki Document; no Wiki Manager role.
- Project Documentation Writer: native read/write/create documentation permission; no Wiki Manager/approval role.
- Project Documentation Manager: used for PM documentation permissions; PMs also receive Wiki Manager because Wiki's native review/merge UI requires it.
- Wiki Space initialization is provisioned in a short Administrator context inside project_documentation after PM validation; Wiki source is not modified.


## V7 changes
- Explicitly whitelisted API wrappers with allow_guest=False.
- Writers/readers no longer retain Wiki Manager or Wiki Approver roles.
- Project-space review and merge endpoints are wrapped so only the PM of the owning project can approve/merge; native Wiki source is unchanged.
- Standard DocType JSON definitions are included for the four Project Documentation DocTypes, with custom=0.
- A migration patch marks the existing site DocTypes as custom=0 without deleting records.
- Developer mode is a site setting, not a per-DocType property. Enable it with `bench --site mysite.local set-config developer_mode 1`.
