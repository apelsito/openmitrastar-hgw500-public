import { useEffect } from "preact/hooks";
import ClassicMarkup from "./classic/ClassicMarkup";
import ClassicAccessibility from "./classic/ClassicAccessibility";
import ClassicDfs from "./classic-dfs";
import { installClassicChannels } from "./classic-channels.ts";
import { installClassicLabLabel } from "./classic-lab.ts";
import "./classic/app.css";
import "./classic/layout-fixes.css";
import "./classic/capabilities.css";
import "./classic/f313-console.css";
import "./classic/console-polish.css";

// Preserve the proven presentation and controller while typed handlers are
// migrated individually. Never render the experimental redesign by default.
export default function ClassicApp() {
  useEffect(() => {
    let disposed = false;
    let removeChannels: (() => void) | undefined;
    let removeLab: (() => void) | undefined;
    void import("./classic/controller.js").then(() => {
      if (!disposed) {
        removeChannels = installClassicChannels(document);
        void installClassicLabLabel(document).then(remove => { if (disposed) remove(); else removeLab = remove; });
      }
    }).catch(() => {
      const status = document.getElementById("connection");
      if (status) {
        status.textContent = "No se pudo iniciar la consola";
        status.setAttribute("role", "alert");
      }
    });
    return () => { disposed = true; removeChannels?.(); removeLab?.(); };
  }, []);
  return <><ClassicMarkup /><ClassicDfs /><ClassicAccessibility /></>;
}
