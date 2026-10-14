/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        dark: {
          900: "#0a0f0d",
          800: "#111816",
          700: "#1a2420",
        },
        accent: {
          500: "#10b981",
          400: "#34d399",
        },
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "Segoe UI", "sans-serif"],
        display: ["Space Grotesk", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};
