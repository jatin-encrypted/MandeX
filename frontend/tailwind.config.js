/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#14171A",
        "ink-raised": "#1D2125",
        paper: "#EFEEE7",
        "paper-line": "#D9D6C9",
        "text-ink": "#F4F2EA",
        "text-paper": "#1C1B18",
        gold: "#C9A46A",
        verified: "#3E7A54",
        blocked: "#B8433D",
      },
      fontFamily: {
        sans: ["Space Grotesk", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "monospace"],
      },
    },
  },
  plugins: [],
};
