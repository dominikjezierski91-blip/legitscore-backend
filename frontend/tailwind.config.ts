import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
    "./lib/**/*.{js,ts,jsx,tsx}",
    "./hooks/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#020617",
        foreground: "#e5f9f5",
        muted: "#1f2933",
        "muted-foreground": "#94a3b8",
        border: "#1e293b",
        card: "rgba(15, 23, 42, 0.9)",
        "card-border": "rgba(148, 163, 184, 0.3)",
        accent: {
          DEFAULT: "#14b8a6",
          soft: "#0f766e",
        },
      },
      borderRadius: {
        lg: "1rem",
        xl: "1.5rem",
      },
      boxShadow: {
        glass: "0 18px 45px rgba(15, 23, 42, 0.75)",
      },
      backdropBlur: {
        xs: "2px",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;

