export default {
  content: [
    "./src/**/*.{html,js,ts}",
    "../backend/**/*.html",
    "../templates/**/*.html",
    "./storybook/**/*.{html,js,mdx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["'Inter'", "ui-sans-serif", "system-ui"],
      },
    },
  },
  plugins: [],
};
