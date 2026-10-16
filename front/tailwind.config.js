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
        "pulse-ring": {
          "0%": { transform: "scale(0.75)", opacity: "0.7" },
          "100%": { transform: "scale(2.4)", opacity: "0" },
        },
        "scan-line": {
          "0%": { transform: "translateY(-110%)", opacity: "0" },
          "50%": { opacity: "0.9" },
          "100%": { transform: "translateY(110%)", opacity: "0" },
        },
        blink: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0" },
        },
        "core-glow": {
          "0%, 100%": { boxShadow: "0 0 16px 0 rgba(16,185,129,0.30)" },
          "50%": { boxShadow: "0 0 34px 4px rgba(16,185,129,0.55)" },
        },
        "data-flow": {
          "0%": { backgroundPosition: "0% 50%" },
          "100%": { backgroundPosition: "200% 50%" },
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
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.22, 1, 0.36, 1) infinite",
        "scan-line": "scan-line 2.6s ease-in-out infinite",
        blink: "blink 1.1s step-end infinite",
        "core-glow": "core-glow 2.8s ease-in-out infinite",
        "data-flow": "data-flow 3s linear infinite",
      },
    },
  },
  plugins: [],
};
