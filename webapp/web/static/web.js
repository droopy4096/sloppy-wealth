// The browser side of the Jinja builder (ADR-0069): the scenario lives in this tab's
// sessionStorage; every page and every form posts it, and every page that comes back
// carries the new one (<script id="scenario-state">), which is stored again.
// Navigation inside the app swaps <main> in place (history kept), so only closing the
// tab, a refresh or leaving the site unloads the page: those warn if there are changes
// since the last save or load.
(() => {
  const KEY = "wealthPlanner.scenario";
  const DIRTY = "wealthPlanner.unsaved";
  const stored = () => sessionStorage.getItem(KEY) || "";

  function keep(main, action) {
    // The nav is not swapped: it shows the jurisdiction the page names (ADR-0071).
    const label = document.getElementById("jurisdiction-name");
    if (label && main.dataset.jurisdiction) label.textContent = main.dataset.jurisdiction;
    const state = main.querySelector("#scenario-state");
    if (!state) return;
    const text = state.textContent;
    const before = stored();
    sessionStorage.setItem(KEY, text);
    if (action === "load" || action === "new") sessionStorage.removeItem(DIRTY);
    else if (before && text !== before) sessionStorage.setItem(DIRTY, "1");
  }

  async function show(url, form, action, again) {
    const body = form || new FormData();
    body.set("scenario", stored());
    let html;
    try {
      // Actions render the builder view they were sent from (ADR-0070 amendment).
      const view = location.pathname === "/flat" ? "flat" : "cards";
      const response = await fetch(url, { method: "POST", body,
                                          headers: { "X-Builder-View": view } });
      html = await response.text();
    } catch (e) {
      alert("The server could not be reached: " + e);
      return;
    }
    const page = new DOMParser().parseFromString(html, "text/html");
    const main = page.querySelector("main");
    if (!main) { document.open(); document.write(html); document.close(); return; }
    keep(main, action);
    document.querySelector("main").replaceWith(main);
    document.title = page.title;
    restoreOpen();
    wire();
    if (again && main.hasAttribute("data-refused") && again(main)) return;
    if (main.querySelector(".flash")) window.scrollTo(0, 0);
    else if (!form) {
      const target = location.hash && document.getElementById(location.hash.slice(1));
      if (target) target.scrollIntoView(); else window.scrollTo(0, 0);
    }
  }

  function go(url, push) {
    if (push) history.pushState(null, "", url);
    const u = new URL(url, location.href);
    show(u.pathname + u.search);
  }

  function inApp(a) {
    if (!a.href || a.target || a.hasAttribute("download")) return false;
    const u = new URL(a.href, location.href);
    if (u.origin !== location.origin || u.pathname.startsWith("/web/static")
        || u.pathname.startsWith("/static/") || u.pathname.startsWith("/api/")) return false;
    // A link to a place on this page only scrolls.
    return !(u.pathname === location.pathname && u.search === location.search && u.hash);
  }

  function save() {
    const text = stored();
    if (!text) return;
    const scenario = JSON.parse(text);
    const stem = (scenario.name || "").replace(/[^A-Za-z0-9._-]+/g, "_").replace(/^[._]+|[._]+$/g, "");
    const blob = new Blob([JSON.stringify(scenario, null, 2) + "\n"], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (stem || "scenario") + ".json";
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
    sessionStorage.removeItem(DIRTY);
  }

  function wire() {
    document.querySelectorAll("main form").forEach(form => {
      if (form.dataset.wired) return;
      form.dataset.wired = "1";
      form.addEventListener("submit", event => {
        event.preventDefault();
        if (form.dataset.confirm && !confirm(form.dataset.confirm)) return;
        if (form.dataset.confirmUnsaved && sessionStorage.getItem(DIRTY)
            && !confirm(form.dataset.confirmUnsaved)) return;
        if ((form.getAttribute("method") || "get").toLowerCase() === "get") {
          const u = new URL(form.getAttribute("action") || location.pathname, location.href);
          u.search = new URLSearchParams(new FormData(form)).toString();
          go(u.pathname + u.search, true);
          return;
        }
        const data = new FormData(form, event.submitter);
        const url = form.getAttribute("action") || location.pathname + location.search;
        show(url, data, data.get("action"), reopener(form));
      });
    });
  }

  // A refused add, edit or settings form comes back open, with what was typed and the
  // reasons above it, instead of being lost with the page it was on.
  function reopener(form) {
    if (form.classList.contains("inline")) return null;      // switches, deletes
    const typed = [...new FormData(form).entries()].filter(([, v]) => typeof v === "string");
    const opener = form.dataset.opener ? JSON.parse(form.dataset.opener) : null;
    const action = form.getAttribute("action");
    return main => {
      let again;
      if (opener && opener.edit) {
        const button = main.querySelector(`button[data-edit="${CSS.escape(opener.edit)}"]`);
        again = button && editForm(button);
      } else if (opener) {
        const button = [...main.querySelectorAll("button.add-kind")].find(b =>
          b.dataset.kind === opener.kind && (b.dataset.fixed || "{}") === opener.fixed);
        again = button && addForm(button);
      } else if (action) {
        again = [...main.querySelectorAll("form")].find(f => f.getAttribute("action") === action);
      }
      if (!again) return false;
      for (const [name, value] of typed) {
        const field = again.querySelector(`[name="${CSS.escape(name)}"]:not([type=hidden])`);
        if (field) field.value = value;
      }
      const reasons = [...main.querySelectorAll(":scope > .flash")].map(f => f.textContent);
      const box = document.createElement("div");
      box.className = "flash";
      box.textContent = reasons.join(" ");
      (again.querySelector("fieldset") || again).prepend(box);
      again.scrollIntoView({ block: "center" });
      return true;
    };
  }

  // "+ Add <type>" (ADR-0070): copy that type's form into place; the fields the card or
  // section fills in become hidden inputs.
  function addForm(button) {
    const holder = button.closest(".adders");
    const open = holder.nextElementSibling;
    if (open && open.classList.contains("add-open") && open.dataset.kind === button.dataset.kind) {
      open.remove();
      return;
    }
    if (open && open.classList.contains("add-open")) open.remove();
    const template = document.getElementById("form-" + button.dataset.kind);
    if (!template) return;
    const box = document.createElement("div");
    box.className = "add-open";
    box.dataset.kind = button.dataset.kind;
    box.appendChild(template.content.cloneNode(true));
    const fixed = JSON.parse(button.dataset.fixed || "{}");
    const form = box.querySelector("form");
    for (const [name, value] of Object.entries(fixed)) {
      const field = form.querySelector(`[name="${name}"]`);
      if (field) (field.closest("label") || field).remove();
      const hidden = document.createElement("input");
      hidden.type = "hidden"; hidden.name = name; hidden.value = value;
      form.appendChild(hidden);
    }
    form.dataset.opener = JSON.stringify({ kind: button.dataset.kind,
                                           fixed: button.dataset.fixed || "{}" });
    holder.after(box);
    wire();
    const first = form.querySelector("input:not([type=hidden]), select");
    if (first) first.focus();
    return form;
  }

  // Edit (ADR-0070 amendment): the item's type form, filled with its values, saved to
  // /items/<id>/update. Opened under the row, or at the top of the card.
  function editForm(button) {
    const id = button.dataset.edit;
    const existing = document.querySelector(`[data-editing="${CSS.escape(id)}"]`);
    if (existing) { existing.remove(); return; }
    const template = document.getElementById("form-" + button.dataset.kind);
    if (!template) return;
    const box = document.createElement("div");
    box.appendChild(template.content.cloneNode(true));
    const form = box.querySelector("form");
    form.classList.remove("add-form");
    form.classList.add("edit-form");
    form.action = `/items/${encodeURIComponent(id)}/update`;
    const values = JSON.parse(button.dataset.values || "{}");
    for (const [name, value] of Object.entries(values)) {
      const field = form.querySelector(`[name="${name}"]`);
      if (field) field.value = value;
    }
    const legend = form.querySelector("legend");
    if (legend) legend.textContent = "Edit " + (values.name || id);
    const save = form.querySelector("button[type=submit]");
    if (save) save.textContent = "Save";
    const cancel = document.createElement("button");
    cancel.type = "button"; cancel.textContent = "Cancel"; cancel.className = "cancel";
    if (save) save.after(cancel);
    let holder;
    const row = button.closest("tr");
    if (row) {
      holder = document.createElement("tr");
      holder.className = "edit-row";
      const cell = document.createElement("td");
      cell.colSpan = row.children.length;
      cell.appendChild(form);
      holder.appendChild(cell);
      row.after(holder);
    } else {
      const card = button.closest("details");
      card.open = true;
      holder = document.createElement("div");
      holder.appendChild(form);
      card.querySelector(":scope > summary").after(holder);
    }
    holder.dataset.editing = id;
    form.dataset.opener = JSON.stringify({ edit: id });
    cancel.addEventListener("click", () => holder.remove());
    wire();
    const first = form.querySelector("input:not([type=hidden]), select");
    if (first) first.focus();
    return form;
  }

  // "+" on a card: open it and show its "+ Add" buttons.
  function showAdders(button) {
    const card = button.closest("details");
    card.open = true;
    const adders = card.querySelector(":scope > .adders, :scope > p.adders");
    if (adders) {
      adders.scrollIntoView({ block: "nearest" });
      adders.classList.add("flash-adders");
      setTimeout(() => adders.classList.remove("flash-adders"), 1200);
    }
  }

  // Which sections, categories and cards are open is kept for the tab.
  const OPEN = "wealthPlanner.open";
  function restoreOpen() {
    const state = JSON.parse(sessionStorage.getItem(OPEN) || "{}");
    document.querySelectorAll("main details[data-key]").forEach(d => {
      if (d.dataset.key in state) d.open = state[d.dataset.key];
      d.addEventListener("toggle", () => {
        const now = JSON.parse(sessionStorage.getItem(OPEN) || "{}");
        now[d.dataset.key] = d.open;
        sessionStorage.setItem(OPEN, JSON.stringify(now));
      });
    });
    // A link to an item opens the details around it.
    const target = location.hash && document.getElementById(location.hash.slice(1));
    for (let d = target && target.closest("details"); d; d = d.parentElement.closest("details")) {
      d.open = true;
    }
  }

  document.addEventListener("click", event => {
    // Icons sit in a card's <summary>: they must not open or close it.
    const iconButton = event.target.closest("button.icon");
    if (iconButton) {
      if (iconButton.closest("summary")) event.preventDefault();
      if (iconButton.dataset.edit) { event.preventDefault(); editForm(iconButton); return; }
      if (iconButton.hasAttribute("data-open-add")) { showAdders(iconButton); return; }
      if (iconButton.type === "submit" && iconButton.closest("summary")) {
        iconButton.form.requestSubmit();
        return;
      }
    }
    const add = event.target.closest("button.add-kind");
    if (add) { event.preventDefault(); addForm(add); return; }
    const a = event.target.closest("a");
    if (!a || event.defaultPrevented || event.button !== 0
        || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (a.hasAttribute("data-save")) { event.preventDefault(); save(); return; }
    if (!inApp(a)) return;
    event.preventDefault();
    go(a.href, true);
  });

  window.addEventListener("popstate", () => go(location.href, false));

  window.addEventListener("beforeunload", event => {
    if (sessionStorage.getItem(DIRTY)) { event.preventDefault(); event.returnValue = ""; }
  });

  const main = document.querySelector("main");
  const FREE = ["/new", "/load", "/compare"];
  if (main && main.hasAttribute("data-shell")){
    if (!stored() && !FREE.includes(location.pathname)) history.replaceState(null, "", "/new");
    show(location.pathname + location.search);
  }
  else { if (main) keep(main); restoreOpen(); wire(); }
})();
