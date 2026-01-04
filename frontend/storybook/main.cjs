const path = require("path");

/** @type { import('@storybook/html-vite').StorybookConfig } */
const config = {
  stories: ["./**/*.stories.@(js|mdx)"],
  addons: ["@storybook/addon-essentials", "@storybook/addon-interactions"],
  framework: {
    name: "@storybook/html-vite",
    options: {},
  },
  core: {
    disableTelemetry: true,
  },
  viteFinal: async (config) => {
    config.css = config.css || {};
    config.css.postcss = path.resolve(__dirname, "../postcss.config.js");
    return config;
  },
};

module.exports = config;
