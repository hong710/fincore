import template from "./help_drawer.html?raw";

export default {
  title: "Components/Help Drawer",
};

export const HelpDrawer = () => `
  <div class="relative h-96 bg-slate-50" x-data="{ docsOpen: true }">
    ${template}
  </div>
`;
