frappe.ready(() => {
  const $ = id => document.getElementById(id);
  const params = new URLSearchParams(window.location.search);
  const project = params.get("project");
  let allMembers = [];

  const esc = v => String(v ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");

  function call(method, args = {}) {
    return new Promise((resolve, reject) => frappe.call({
      method, args,
      callback: r => r.exc ? reject(new Error(r._server_messages || "Request failed")) : resolve(r.message),
      error: reject
    }));
  }

  function alertMsg(msg, type = "info") {
    const e = $("pd-alert");
    e.hidden = false;
    e.className = `pd-alert pd-alert-${type}`;
    e.textContent = msg;
    window.clearTimeout(alertMsg.timer);
    alertMsg.timer = window.setTimeout(() => e.hidden = true, 4000);
  }

  function updateCount(visible = allMembers) {
    const read = allMembers.filter(m => m.access_level === "Read").length;
    const write = allMembers.filter(m => m.access_level === "Write").length;
    $("pd-member-count").textContent =
      `${visible.length} shown · ${read} Read · ${write} Write`;
  }

  function renderMembers(members) {
    updateCount(members);

    if (!members.length) {
      $("pd-members").innerHTML = `
        <div class="pd-empty">
          <div class="pd-empty-icon">⌕</div>
          <h3>No matching members</h3>
          <p>Try a different name, designation, or email.</p>
        </div>`;
      return;
    }

    $("pd-members").innerHTML = `
      <div class="pd-table-wrap">
        <table class="pd-table">
          <thead>
            <tr>
              <th>Team Member</th>
              <th>Project Role</th>
              <th>Frappe User</th>
              <th>Documentation Access</th>
            </tr>
          </thead>
          <tbody>
            ${members.map(m => {
              const name = m.employee_name || m.user || "Unknown";
              const initial = esc(name.charAt(0).toUpperCase());
              return `
              <tr>
                <td>
                  <div class="pd-person">
                    <span class="pd-avatar">${initial}</span>
                    <div>
                      <strong>${esc(name)}</strong>
                      <small>${esc(m.actual_designation || "Project member")}</small>
                    </div>
                  </div>
                </td>
                <td><strong style="font-size:12px;color:#475467">${esc(m.project_designation || "—")}</strong></td>
                <td><span class="pd-user-cell">${esc(m.user || "No Frappe User")}</span></td>
                <td>
                  <select class="pd-select" data-user="${esc(m.user || "")}" ${m.user ? "" : "disabled"}>
                    <option value="">No access</option>
                    <option value="Read" ${m.access_level === "Read" ? "selected" : ""}>Read</option>
                    <option value="Write" ${m.access_level === "Write" ? "selected" : ""}>Write</option>
                  </select>
                </td>
              </tr>`;
            }).join("")}
          </tbody>
        </table>
      </div>`;
  }

  function filterMembers() {
    const q = $("pd-member-search").value.trim().toLowerCase();
    if (!q) return renderMembers(allMembers);

    renderMembers(allMembers.filter(m =>
      [m.employee_name, m.user, m.project_designation, m.actual_designation]
        .some(v => String(v || "").toLowerCase().includes(q))
    ));
  }

  async function loadMembers() {
    allMembers = await call(
      "project_documentation.api.project_access.api_get_project_members",
      { project }
    ) || [];
    renderMembers(allMembers);
  }

  async function saveAll() {
    const btn = $("pd-save-all");
    const selects = [...document.querySelectorAll("[data-user]")]
      .filter(s => s.dataset.user);

    btn.disabled = true;
    btn.textContent = "Saving...";

    try {
      for (const s of selects) {
        if (s.value) {
          await call("project_documentation.api.project_access.api_set_member_access", {
            project, user: s.dataset.user, access_level: s.value
          });
        } else {
          await call("project_documentation.api.project_access.api_remove_member_access", {
            project, user: s.dataset.user
          });
        }
      }

      await loadMembers();
      alertMsg("Documentation access saved successfully.", "success");
    } catch (e) {
      alertMsg("Unable to save documentation access.", "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Save changes";
    }
  }

  async function load() {
    if (!project) {
      window.location.replace("/project-documentation");
      return;
    }

    try {
      const p = await call(
        "project_documentation.api.project_access.api_get_pm_project",
        { project }
      );

      $("pd-current-user").textContent = frappe.session.user || "User";
      $("pd-project-title").textContent = p.project_name || p.name;
      $("pd-project-meta").textContent =
        `${p.project_code || p.name}${p.external_project_id ? ` · ${p.external_project_id}` : ""}`;
      $("pd-project-code").textContent = p.project_code || p.name;
      $("pd-phase").textContent = p.phase_name || "—";
      $("pd-vertical").textContent = p.vertical || "—";
      $("pd-oic").textContent = p.oic_name || "—";

      const status = $("pd-space-status");
      if (p.wiki_space) {
        status.textContent = "Wiki Space ready";
        const a = $("pd-open-space");
        a.hidden = false;
        a.href = p.space_url || `/wiki-app/spaces/${encodeURIComponent(p.wiki_space)}`;
      } else {
        status.textContent = "Wiki Space initializing";
      }

      await loadMembers();
    } catch (e) {
      $("pd-members").innerHTML = `
        <div class="pd-error">Unable to load this project. You may not be an active PM for it.</div>`;
    }
  }

  $("pd-save-all").addEventListener("click", saveAll);
  $("pd-member-search").addEventListener("input", filterMembers);
  load();
});
