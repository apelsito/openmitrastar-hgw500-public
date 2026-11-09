import { useEffect } from "preact/hooks";

/** Keyboard and screen-reader support around the unchanged firmware markup.
 * All activation is delegated to the retained controller's native controls. */
export default function ClassicAccessibility() {
  useEffect(() => {
    const sidebar = document.getElementById("primary-nav");
    const toggle = document.getElementById("nav-toggle");
    const scrim = document.getElementById("nav-scrim");
    const main = document.getElementById("main-content");
    const topbar = document.querySelector<HTMLElement>(".topbar");
    if (!sidebar || !toggle || !scrim || !main || !topbar) return;

    const restore: (() => void)[] = [];
    const set = (element: Element, name: string, value: string) => {
      const previous = element.getAttribute(name);
      restore.push(() => previous === null ? element.removeAttribute(name) : element.setAttribute(name, previous));
      element.setAttribute(name, value);
    };

    document.querySelectorAll(".nav-mark, .status-dot").forEach(element => set(element, "aria-hidden", "true"));
    for (const id of ["connection", "runtime-origin"]) {
      const element = document.getElementById(id);
      if (element) { set(element, "role", "status"); set(element, "aria-live", "polite"); set(element, "aria-atomic", "true"); }
    }
    document.querySelectorAll(".config-field").forEach(field => {
      const label = field.querySelector("label:not(.switch), .field-label")?.textContent?.trim();
      const description = field.querySelector("small")?.textContent?.trim();
      field.querySelectorAll<HTMLInputElement | HTMLSelectElement>("input, select").forEach(control => {
        if (label && !control.labels?.length) set(control, "aria-label", label);
        // A switch's enclosing label contains its visual track, but no name.
        if (label && control.closest(".switch")) set(control, "aria-label", label);
        if (description) set(control, "aria-description", description);
      });
    });
    document.querySelectorAll<HTMLFormElement>(".radio-form").forEach(form => {
      form.querySelectorAll<HTMLButtonElement>(".config-tab").forEach(tab => {
        const pane = form.querySelector<HTMLElement>(`[data-pane-panel="${tab.dataset.pane}"]`);
        if (!pane) return;
        const suffix = `${form.dataset.radio}-${tab.dataset.pane}`;
        if (!tab.id) set(tab, "id", `classic-tab-${suffix}`);
        if (!pane.id) set(pane, "id", `classic-pane-${suffix}`);
        set(tab, "aria-controls", pane.id);
        set(pane, "role", "tabpanel");
        set(pane, "aria-labelledby", tab.id);
        set(pane, "tabindex", "0");
      });
    });

    const close = document.createElement("button");
    close.type = "button";
    close.className = "console-nav-close";
    close.textContent = "Cerrar menú ×";
    close.setAttribute("aria-label", "Cerrar navegación");
    close.addEventListener("click", () => scrim.click());
    sidebar.prepend(close);

    const mobile = window.matchMedia("(max-width: 900px)");
    let wasOpen = false;
    let wasMobile: boolean | undefined;
    const originalRole = sidebar.getAttribute("role");
    const originalModal = sidebar.getAttribute("aria-modal");
    const originalHidden = sidebar.getAttribute("aria-hidden");
    const originalInert = [sidebar.inert, main.inert, topbar.inert];
    const syncDrawer = () => {
      if (!mobile.matches && document.body.classList.contains("nav-open")) scrim.click();
      const open = mobile.matches && document.body.classList.contains("nav-open");
      if (open === wasOpen && mobile.matches === wasMobile) return;
      sidebar.inert = mobile.matches && !open;
      main.inert = open;
      topbar.inert = open;
      if (mobile.matches) {
        sidebar.setAttribute("role", "dialog");
        sidebar.setAttribute("aria-modal", "true");
        sidebar.setAttribute("aria-hidden", String(!open));
      } else {
        sidebar.removeAttribute("role");
        sidebar.removeAttribute("aria-modal");
        sidebar.removeAttribute("aria-hidden");
      }
      toggle.setAttribute("aria-label", open ? "Cerrar navegación" : "Abrir navegación");
      if (open) close.focus({ preventScroll: true });
      else if (wasOpen && mobile.matches) toggle.focus({ preventScroll: true });
      else if (wasOpen) sidebar.querySelector<HTMLElement>(".section-link.active")?.focus({ preventScroll: true });
      wasOpen = open;
      wasMobile = mobile.matches;
    };
    const drawerObserver = new MutationObserver(syncDrawer);
    drawerObserver.observe(document.body, { attributes: true, attributeFilter: ["class"] });
    mobile.addEventListener("change", syncDrawer);
    syncDrawer();

    const onKeyDown = (event: KeyboardEvent) => {
      if (mobile.matches && document.body.classList.contains("nav-open")) {
        if (event.key === "Escape") { event.preventDefault(); scrim.click(); return; }
        if (event.key === "Tab") {
          const items = [...sidebar.querySelectorAll<HTMLElement>("button:not(:disabled), a[href], [tabindex=\"0\"]")]
            .filter(element => !element.hidden && element.getClientRects().length > 0);
          const first = items[0], last = items[items.length - 1];
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
        }
        return;
      }
      const target = event.target;
      if (!(target instanceof HTMLElement) || !target.matches(".config-tab")) return;
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      const tabs = [...(target.closest(".config-tabs")?.querySelectorAll<HTMLButtonElement>(".config-tab:not([hidden])") ?? [])];
      const index = tabs.indexOf(target as HTMLButtonElement);
      if (index < 0 || !tabs.length) return;
      event.preventDefault();
      const next = event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
      tabs[next].click();
      tabs[next].focus({ preventScroll: true });
      tabs[next].scrollIntoView({ block: "nearest", inline: "nearest", behavior: "instant" });
    };
    const onNavigation = (event: MouseEvent) => {
      if (event.target instanceof Element && event.target.closest(".section-link") && mobile.matches) {
        queueMicrotask(() => main.focus({ preventScroll: true }));
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    sidebar.addEventListener("click", onNavigation);

    return () => {
      drawerObserver.disconnect();
      mobile.removeEventListener("change", syncDrawer);
      document.removeEventListener("keydown", onKeyDown, true);
      sidebar.removeEventListener("click", onNavigation);
      close.remove();
      [sidebar.inert, main.inert, topbar.inert] = originalInert;
      for (const [name, value] of [["role", originalRole], ["aria-modal", originalModal], ["aria-hidden", originalHidden]] as const) {
        if (value === null) sidebar.removeAttribute(name); else sidebar.setAttribute(name, value);
      }
      restore.reverse().forEach(undo => undo());
    };
  }, []);
  return null;
}
