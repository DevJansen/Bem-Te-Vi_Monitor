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
      keyframes: {
        "fade-in-up": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "pop-in": {
          "0%": { opacity: "0", transform: "scale(0.92)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "slide-up-in": {
          "0%": { opacity: "0", transform: "translateY(18px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "slide-in-right": {
          "0%": { opacity: "0", transform: "translateX(26px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
        "progress-stripes": {
          "0%": { backgroundPosition: "0 0" },
          "100%": { backgroundPosition: "2rem 0" },
        },
      },
      animation: {
        "fade-in-up": "fade-in-up 0.45s ease-out both",
        "pop-in": "pop-in 0.35s cubic-bezier(0.22, 1, 0.36, 1) both",
        shimmer: "shimmer 2.2s infinite",
        "slide-up-in": "slide-up-in 0.5s cubic-bezier(0.22, 1, 0.36, 1) both",
        "slide-in-right": "slide-in-right 0.45s cubic-bezier(0.22, 1, 0.36, 1) both",
        "pulse-soft": "pulse-soft 1.8s ease-in-out infinite",
        "progress-stripes": "progress-stripes 0.9s linear infinite",
      },
    },
  },
  plugins: [],
};
