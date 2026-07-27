/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#172033",
        canvas: "#f6f7f9",
        line: "#d9dee7",
        accent: "#087f70",
        warning: "#a15c00",
      },
      boxShadow: {
        panel: "0 1px 2px rgb(23 32 51 / 0.06)",
      },
    },
  },
  plugins: [],
};
