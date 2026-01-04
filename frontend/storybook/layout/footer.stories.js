import template from "./footer.html?raw";

export default {
  title: "Layout/Footer",
};

export const Footer = () => `
  <div class="bg-slate-50 p-4">
    ${template}
  </div>
`;
