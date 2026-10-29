frappe.ready(() => {
  const $ = id => document.getElementById(id);
  let allProjects = [];
  let activeFilter = "all"; // "all" | "ready" | "pending"
  let searchQuery = "";

  const esc = value => String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

  function call(method, args = {}) {
    return new Promise((resolve, reject) => frappe.call({
      method,
      args,
      callback: r => r.exc ? reject(new Error(r._server_messages || "Request failed")) : resolve(r.message),
      error: reject
    }));
  }

  function getUserInitials(userName) {
    if (!userName) return "PM";
    const clean = String(userName).split("@")[0].replace(/[._-]/g, " ").trim();
    const parts = clean.split(/\s+/).filter(Boolean);
    if (parts.length >= 2) {
      return (parts[0][0] + parts[1][0]).toUpperCase();
    }
    return clean.slice(0, 2).toUpperCase() || "PM";
  }

  function renderSkeletons() {
    const container = $("pd-projects");
    if (!container) return;
    container.innerHTML = Array.from({ length: 6 }).map(() => `
      <div class="pd-project-card pd-skeleton-card" aria-hidden="true">
        <div class="pd-card-header">
          <div class="pd-avatar-wrap">
            <div class="pd-skeleton" style="width: 40px; height: 40px; border-radius: 9px;"></div>
          </div>
          <div class="pd-card-identity">
            <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px;">
              <div class="pd-skeleton" style="width: 65px; height: 16px;"></div>
              <div class="pd-skeleton" style="width: 60px; height: 16px; border-radius: 999px;"></div>
            </div>
            <div class="pd-skeleton" style="width: 85%; height: 16px; margin-bottom: 6px;"></div>
            <div class="pd-skeleton" style="width: 55%; height: 16px;"></div>
          </div>
        </div>
        <div class="pd-card-meta">
          <div class="pd-skeleton" style="width: 45%; height: 14px;"></div>
        </div>
        <div class="pd-card-footer">
          <div class="pd-skeleton" style="width: 90px; height: 16px;"></div>
          <div class="pd-skeleton" style="width: 80px; height: 26px; border-radius: 6px;"></div>
        </div>
      </div>
    `).join("");
  }

  function updateStatistics(projects) {
    const total = projects.length;
    const ready = projects.filter(p => Boolean(p.wiki_space)).length;
    const pending = total - ready;

    if ($("pd-stat-total")) $("pd-stat-total").textContent = total;
    if ($("pd-stat-ready")) $("pd-stat-ready").textContent = ready;
    if ($("pd-stat-pending")) $("pd-stat-pending").textContent = pending;

    if ($("pd-filter-all-count")) $("pd-filter-all-count").textContent = total;
    if ($("pd-filter-ready-count")) $("pd-filter-ready-count").textContent = ready;
    if ($("pd-filter-pending-count")) $("pd-filter-pending-count").textContent = pending;
  }

  function renderProjects(projects) {
    const container = $("pd-projects");
    if (!container) return;

    const visibleMeta = $("pd-project-visible");
    if (visibleMeta) {
      if (allProjects.length === projects.length) {
        visibleMeta.textContent = `Showing all ${projects.length} ${projects.length === 1 ? "project" : "projects"}`;
      } else {
        visibleMeta.textContent = `Showing ${projects.length} of ${allProjects.length} projects`;
      }
    }

    if (!projects.length) {
      const isFiltered = Boolean(searchQuery || activeFilter !== "all");
      container.innerHTML = `
        <div class="pd-empty-state">
          <div class="pd-empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="24" height="24" aria-hidden="true">
              <circle cx="11" cy="11" r="8"/>
              <line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
          </div>
          <h3 class="pd-empty-title">${isFiltered ? "No matching projects found" : "No assigned projects"}</h3>
          <p class="pd-empty-desc">${isFiltered ? "No projects match your current search criteria or filter. Try a different term or clear the filter." : "You do not have any active projects assigned as Project Manager at this time."}</p>
          ${isFiltered ? `<button id="pd-empty-reset" class="pd-btn pd-btn-secondary" type="button" style="margin-top: 14px;">Clear filters</button>` : ""}
        </div>`;

      const resetBtn = $("pd-empty-reset");
      if (resetBtn) {
        resetBtn.addEventListener("click", () => {
          searchQuery = "";
          activeFilter = "all";
          const input = $("pd-project-search");
          if (input) input.value = "";
          const clearBtn = $("pd-search-clear");
          if (clearBtn) clearBtn.style.display = "none";
          document.querySelectorAll(".pd-filter-tab").forEach(tab => {
            const isAll = tab.dataset.filter === "all";
            tab.classList.toggle("active", isAll);
            tab.setAttribute("aria-selected", isAll ? "true" : "false");
          });
          applyFilters();
        });
      }
      return;
    }

    container.innerHTML = projects.map(project => {
      const title = project.project_name || project.name || "Untitled Project";
      const code = project.project_code || project.name || "—";
      const initial = esc(title.trim().charAt(0).toUpperCase()) || "P";
      const ready = Boolean(project.wiki_space);
      const spaceUrl = project.space_url || (project.wiki_space ? `/wiki-app/spaces/${encodeURIComponent(project.wiki_space)}` : "");
      const manageUrl = `/project-documentation-project?project=${encodeURIComponent(project.name)}`;

      const isDirect = project.workflow_mode === "direct_publishing";
      const wfBadge = isDirect
        ? `<span class="pd-wf-badge pd-wf-direct" title="Workflow Mode: Direct Publishing enabled"><span class="pd-wf-dot"></span>Direct Publishing</span>`
        : `<span class="pd-wf-badge pd-wf-cr" title="Workflow Mode: Change Request (CR) review required"><span class="pd-wf-dot"></span>CR Workflow</span>`;

      const statusBadge = ready
        ? `<span class="pd-status-badge pd-status-ready" title="Wiki space is active and ready">
             <span class="pd-status-dot"></span>Ready
           </span>`
        : `<span class="pd-status-badge pd-status-pending" title="Wiki space pending initialization">
             <span class="pd-status-dot"></span>Pending
           </span>`;

      const metaParts = [];
      if (project.phase_name) {
        metaParts.push(`
          <span class="pd-meta-item" title="Phase">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12" aria-hidden="true">
              <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
            </svg>
            <span>${esc(project.phase_name)}</span>
          </span>
        `);
      }
      if (project.vertical) {
        metaParts.push(`
          <span class="pd-meta-item" title="Vertical">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12" aria-hidden="true">
              <rect x="2" y="7" width="20" height="14" rx="2" ry="2"/>
              <path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"/>
            </svg>
            <span>${esc(project.vertical)}</span>
          </span>
        `);
      }

      const metaContent = metaParts.length
        ? metaParts.join("")
        : `<span class="pd-meta-muted">Active Documentation Project</span>`;

      return `
        <article class="pd-project-card" data-project-href="${esc(manageUrl)}" tabindex="0" role="link" aria-label="${esc(title)}">
          <div class="pd-card-header">
            <div class="pd-avatar-wrap">
              <div class="pd-project-avatar" aria-hidden="true">${initial}</div>
            </div>
            <div class="pd-card-identity">
              <div class="pd-badge-row">
                <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
                  <span class="pd-code-badge" title="Project Code">${esc(code)}</span>
                  ${wfBadge}
                </div>
                ${statusBadge}
              </div>
              <h3 class="pd-project-title" title="${esc(title)}">${esc(title)}</h3>
            </div>
          </div>

          <div class="pd-card-meta">
            ${metaContent}
          </div>

          <div class="pd-card-footer">
            <span class="pd-action-manage">
              <span>Manage Access &amp; Workflow</span>
              <svg class="pd-arrow-icon" viewBox="0 0 20 20" fill="currentColor" width="14" height="14" aria-hidden="true">
                <path fill-rule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clip-rule="evenodd" />
              </svg>
            </span>

            <div class="pd-card-actions-right">
              <button class="pd-action-wf-btn" data-project="${esc(project.name)}" data-project-name="${esc(title)}" data-mode="${esc(project.workflow_mode || 'cr_workflow')}" title="Configure documentation workflow" type="button" onclick="event.stopPropagation()">
                ⚙ Workflow
              </button>
              ${ready ? `
                <a class="pd-wiki-button" href="${esc(spaceUrl)}" target="_blank" rel="noopener" title="Open Wiki in new tab" onclick="event.stopPropagation()">
                  <span>Open Wiki</span>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12" aria-hidden="true">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/>
                  </svg>
                </a>
              ` : `
                <span class="pd-pending-tag" title="Space initialization in progress">
                  <span class="pd-pending-dot"></span>Space Pending
                </span>
              `}
            </div>
          </div>
        </article>`;
    }).join("");
  }

  function applyFilters() {
    let filtered = allProjects.slice();

    if (activeFilter === "ready") {
      filtered = filtered.filter(p => Boolean(p.wiki_space));
    } else if (activeFilter === "pending") {
      filtered = filtered.filter(p => !p.wiki_space);
    }

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      filtered = filtered.filter(p =>
        [p.project_name, p.project_code, p.name, p.phase_name, p.vertical]
          .some(v => String(v || "").toLowerCase().includes(q))
      );
    }

    renderProjects(filtered);
  }

  async function load() {
    const refreshBtn = $("pd-refresh");
    if (refreshBtn) {
      refreshBtn.disabled = true;
      refreshBtn.classList.add("is-loading");
    }

    renderSkeletons();

    try {
      const result = await call("project_documentation.api.project_access.api_get_my_pm_projects");
      const userName = result.user || frappe.session.user || "Project Manager";

      if ($("pd-current-user")) $("pd-current-user").textContent = userName;
      if ($("pd-user-avatar")) $("pd-user-avatar").textContent = getUserInitials(userName);

      if (!result.is_pm) {
        window.location.replace("/wiki-app/spaces/");
        return;
      }

      allProjects = result.projects || [];
      updateStatistics(allProjects);
      applyFilters();
    } catch (error) {
      const container = $("pd-projects");
      if (container) {
        container.innerHTML = `
          <div class="pd-error-card">
            <h4 style="font-size: 14px; font-weight: 700; color: #991b1b; margin: 0 0 4px;">Unable to load projects</h4>
            <p style="font-size: 13px; color: #7f1d1d; margin: 0;">An error occurred while fetching your assigned projects from the server.</p>
            <button id="pd-retry-load" class="pd-btn pd-btn-secondary" type="button" style="margin-top: 10px;">Retry</button>
          </div>`;

        const retryBtn = $("pd-retry-load");
        if (retryBtn) retryBtn.addEventListener("click", load);
      }
    } finally {
      if (refreshBtn) {
        refreshBtn.disabled = false;
        refreshBtn.classList.remove("is-loading");
      }
    }
  }

  // Bind Events
  const refreshBtn = $("pd-refresh");
  if (refreshBtn) refreshBtn.addEventListener("click", load);

  const searchInput = $("pd-project-search");
  const clearBtn = $("pd-search-clear");
  if (searchInput) {
    searchInput.addEventListener("input", e => {
      searchQuery = e.target.value.trim();
      if (clearBtn) clearBtn.style.display = searchQuery ? "inline-flex" : "none";
      applyFilters();
    });
  }

  if (clearBtn && searchInput) {
    clearBtn.addEventListener("click", () => {
      searchInput.value = "";
      searchQuery = "";
      clearBtn.style.display = "none";
      searchInput.focus();
      applyFilters();
    });
  }

  // Filter Tabs Event
  const filterTabs = document.querySelectorAll(".pd-filter-tab");
  filterTabs.forEach(tab => {
    tab.addEventListener("click", () => {
      filterTabs.forEach(t => {
        t.classList.remove("active");
        t.setAttribute("aria-selected", "false");
      });
      tab.classList.add("active");
      tab.setAttribute("aria-selected", "true");
      activeFilter = tab.dataset.filter || "all";
      applyFilters();
    });
  });

  // Workflow Modal Management
  let modalProject = null;
  let modalCurrentMode = "cr_workflow";

  function alertMsg(msg, type = "info") {
    const el = $("pd-alert");
    if (!el) return;
    el.hidden = false;
    el.className = `pd-alert pd-alert-${type}`;
    el.textContent = msg;
    window.clearTimeout(alertMsg.timer);
    alertMsg.timer = window.setTimeout(() => el.hidden = true, 4000);
  }

  function openWorkflowModal(projectCode, projectName, currentMode) {
    modalProject = projectCode;
    modalCurrentMode = currentMode || "cr_workflow";

    const nameEl = $("pd-modal-project-name");
    if (nameEl) nameEl.textContent = projectName || projectCode;

    const isCr = modalCurrentMode === "cr_workflow";
    const radioCr = $("pd-m-radio-cr");
    const radioDirect = $("pd-m-radio-direct");
    if (radioCr) radioCr.checked = isCr;
    if (radioDirect) radioDirect.checked = !isCr;

    const cardCr = $("pd-m-card-cr");
    const cardDirect = $("pd-m-card-direct");
    if (cardCr) cardCr.classList.toggle("active", isCr);
    if (cardDirect) cardDirect.classList.toggle("active", !isCr);

    const warnBox = $("pd-m-warning");
    if (warnBox) warnBox.style.display = "none";

    const saveBtn = $("pd-m-save");
    if (saveBtn) saveBtn.disabled = true;

    const overlay = $("pd-modal-overlay");
    if (overlay) {
      overlay.style.display = "grid";
      overlay.setAttribute("aria-hidden", "false");
    }
  }

  function closeWorkflowModal() {
    const overlay = $("pd-modal-overlay");
    if (overlay) {
      overlay.style.display = "none";
      overlay.setAttribute("aria-hidden", "true");
    }
    modalProject = null;
  }

  function onModalRadioChange() {
    const selected = $("pd-m-radio-direct")?.checked ? "direct_publishing" : "cr_workflow";
    const cardCr = $("pd-m-card-cr");
    const cardDirect = $("pd-m-card-direct");
    if (cardCr) cardCr.classList.toggle("active", selected === "cr_workflow");
    if (cardDirect) cardDirect.classList.toggle("active", selected === "direct_publishing");

    const saveBtn = $("pd-m-save");
    const warnBox = $("pd-m-warning");
    const warnMsg = $("pd-m-warning-msg");

    if (selected !== modalCurrentMode) {
      if (saveBtn) saveBtn.disabled = false;
      if (warnBox && warnMsg) {
        warnBox.style.display = "flex";
        if (selected === "direct_publishing") {
          warnMsg.innerHTML = "<strong>Warning:</strong> Switching to <em>Direct Publishing</em> allows all authorized members with Write access to publish changes immediately without your review. Existing CRs and approval history will remain intact.";
        } else {
          warnMsg.innerHTML = "<strong>Warning:</strong> Switching to <em>CR Workflow Enabled</em> requires all documentation changes to follow the Change Request approval process before going live.";
        }
      }
    } else {
      if (saveBtn) saveBtn.disabled = true;
      if (warnBox) warnBox.style.display = "none";
    }
  }

  async function saveModalWorkflow() {
    if (!modalProject) return;
    const selected = $("pd-m-radio-direct")?.checked ? "direct_publishing" : "cr_workflow";
    const saveBtn = $("pd-m-save");
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving...";
    }

    try {
      await call("project_documentation.api.project_access.api_set_project_workflow_mode", {
        project: modalProject,
        workflow_mode: selected
      });

      // Update in allProjects list
      const p = allProjects.find(item => item.name === modalProject);
      if (p) p.workflow_mode = selected;

      applyFilters();
      closeWorkflowModal();
      alertMsg(`Workflow updated to ${selected === 'direct_publishing' ? 'Direct Publishing' : 'CR Workflow'} for ${p ? p.project_name : modalProject}.`, "success");
    } catch (e) {
      alertMsg(e.message || "Failed to update workflow mode.", "error");
      if (saveBtn) saveBtn.disabled = false;
    } finally {
      if (saveBtn) saveBtn.textContent = "Save Workflow";
    }
  }

  // Modal event listeners
  const modalClose = $("pd-modal-close");
  if (modalClose) modalClose.addEventListener("click", closeWorkflowModal);
  const modalCancel = $("pd-m-cancel");
  if (modalCancel) modalCancel.addEventListener("click", closeWorkflowModal);
  const modalOverlay = $("pd-modal-overlay");
  if (modalOverlay) {
    modalOverlay.addEventListener("click", e => {
      if (e.target === modalOverlay) closeWorkflowModal();
    });
  }
  const modalRadioCr = $("pd-m-radio-cr");
  if (modalRadioCr) modalRadioCr.addEventListener("change", onModalRadioChange);
  const modalRadioDirect = $("pd-m-radio-direct");
  if (modalRadioDirect) modalRadioDirect.addEventListener("change", onModalRadioChange);
  const modalSaveBtn = $("pd-m-save");
  if (modalSaveBtn) modalSaveBtn.addEventListener("click", saveModalWorkflow);

  // Card click navigation & workflow button
  const projectsContainer = $("pd-projects");
  if (projectsContainer) {
    projectsContainer.addEventListener("click", e => {
      const wfBtn = e.target.closest(".pd-action-wf-btn");
      if (wfBtn) {
        e.preventDefault();
        e.stopPropagation();
        openWorkflowModal(wfBtn.dataset.project, wfBtn.dataset.projectName, wfBtn.dataset.mode);
        return;
      }

      const interactive = e.target.closest("a, button, input");
      if (interactive) return;
      const card = e.target.closest(".pd-project-card");
      if (card && card.dataset.projectHref) {
        window.location.href = card.dataset.projectHref;
      }
    });

    projectsContainer.addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " ") {
        const interactive = e.target.closest("a, button, input");
        if (interactive) return;
        const card = e.target.closest(".pd-project-card");
        if (card && card.dataset.projectHref) {
          e.preventDefault();
          window.location.href = card.dataset.projectHref;
        }
      }
    });
  }

  load();
});
