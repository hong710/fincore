import template from "./modal.html?raw";

export default {
  title: "Overlays/Modal",
};

export const Modal = () => {
  return `
    <div x-data="{}">
      ${template}
    </div>
  `;
};
