import template from "./header.html?raw";

export default {
  title: "Layout/Header",
};

export const Header = () => `
  <div x-data="{ docsOpen: false }">
    ${template}
  </div>
`;
