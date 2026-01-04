import template from "./sidebar.html?raw";

export default {
  title: "Layout/Sidebar",
};

export const Sidebar = () => `
  <div class="h-screen bg-slate-50" x-data="{ sidebarOpen: true, salesOpen: false, expenseOpen: false, reportOpen: false }">
    ${template}
  </div>
`;
