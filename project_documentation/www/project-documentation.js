frappe.ready(() => {
  const $ = id => document.getElementById(id);
  let allProjects = [];

  const esc = value => String(value ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");

  function call(method, args = {}) {
    return new Promise((resolve, reject) => frappe.call({
      method, args,
      callback: r => r.exc ? reject(new Error(r._server_messages || "Request failed")) : resolve(r.message),
      error: reject
    }));
  }

  function renderProjects(projects) {
    const container = $("pd-projects");
    $("pd-project-visible").textContent = `${projects.length} shown`;

    if (!projects.length) {
      container.innerHTML = `
        <div class="pd-empty">
          <div class="pd-empty-icon">⌕</div>
          <h3>No matching projects</h3>
          <p>Try a different project name or code.</p>
        </div>`;
      return;
    }

    container.innerHTML = projects.map(project => {
      const title = project.project_name || project.name;
      const code = project.project_code || project.name;
      const initial = esc(title.charAt(0).toUpperCase());
      const ready = Boolean(project.wiki_space);

      return `
        <a class="pd-project-card" href="/project-documentation-project?project=${encodeURIComponent(project.name)}">
          <div class="pd-project-icon">${initial}</div>
          <div class="pd-project-content">
            <strong>${esc(title)}</strong>
            <span>${esc(code)}${project.phase_name ? ` · ${esc(project.phase_name)}` : ""}</span>
            <small>${ready ? "Documentation ready" : "Documentation initializing"}</small>
          </div>
        </a>`;
    }).join("");
  }

  function filterProjects() {
    const query = $("pd-project-search").value.trim().toLowerCase();
    if (!query) return renderProjects(allProjects);

    renderProjects(allProjects.filter(p =>
      [p.project_name, p.project_code, p.name, p.phase_name, p.vertical]
        .some(v => String(v || "").toLowerCase().includes(query))
    ));
  }

  async function load() {
    $("pd-refresh").disabled = true;
    try {
      const result = await call("project_documentation.api.project_access.api_get_my_pm_projects");
      $("pd-current-user").textContent = result.user || frappe.session.user || "User";

      if (!result.is_pm) {
        window.location.replace("/wiki-app/spaces/");
        return;
      }

      allProjects = result.projects || [];
      $("pd-project-count").textContent = `${allProjects.length} ${allProjects.length === 1 ? "project" : "projects"}`;
      renderProjects(allProjects);
    } catch (error) {
      $("pd-projects").innerHTML = `
        <div class="pd-error">Unable to load your projects. Please refresh and try again.</div>`;
    } finally {
      $("pd-refresh").disabled = false;
    }
  }

  $("pd-refresh").addEventListener("click", load);
  $("pd-project-search").addEventListener("input", filterProjects);
  load();
});
