import "./css/styles.css";

import Alpine from "alpinejs";
import "htmx.org";
import "preline";

window.Alpine = Alpine;
Alpine.start();

// Re-initialize Preline behaviors after HTMX swaps inject new markup.
document.addEventListener("htmx:afterSwap", () => {
  window.HSStaticMethods?.autoInit?.();
});
