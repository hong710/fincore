import "./css/styles.css";

import Alpine from "alpinejs";
import htmx from "htmx.org";
import "preline";

window.Alpine = Alpine;
window.htmx = htmx;
Alpine.start();

// Re-initialize Alpine + Preline after HTMX swaps inject new markup.
document.addEventListener("htmx:afterSwap", (event) => {
  const target = event.detail?.target;
  if (target) {
    Alpine.initTree(target);
  }
  window.HSStaticMethods?.autoInit?.();
});
