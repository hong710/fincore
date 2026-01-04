import "../src/css/styles.css";
import Alpine from "alpinejs";
import "preline";
import "htmx.org";

window.Alpine = Alpine;
Alpine.start();

document.addEventListener("DOMContentLoaded", () => {
  window.HSStaticMethods?.autoInit?.();
});

export const parameters = {
  controls: { expanded: true },
  actions: { argTypesRegex: "^on[A-Z].*" },
  layout: "fullscreen",
};
