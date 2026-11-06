import type { Config } from "tailwindcss";

// Design tokens from the Hallmark-polished Stitch screens. Change colours here only.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        page: "#FAFAF9",      // page background, warm off-white
        panel: "#FFFFFF",     // cards and panels
        line: "#E7E5E4",      // 1px borders and dividers
        field: "#8C857F",     // form field borders (3:1 contrast)
        skeleton: "#EFEEED",
        hover: "#F5F5F4",
        ink: "#1C1917",       // primary text
        "ink-2": "#57534E",   // nav, secondary headings
        muted: "#6B6560",     // secondary text
        accent: "#1E3A8A",    // the only accent: primary buttons, links, current nav
        "accent-hover": "#172554",
        danger: "#B91C1C",    // failed, Sev 1, open
        warn: "#B45309",      // Sev 2, investigating
        ok: "#15803D",        // worked, resolved
        "chart-off": "#A8A29E",
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "ui-monospace", "monospace"],
      },
      fontSize: {
        xs: ["13px", "18px"],
        sm: ["15px", "22px"],
        base: ["16px", "24px"],
        lg: ["17px", "26px"],
        xl: ["20px", "28px"],
        "2xl": ["24px", "32px"],
        "3xl": ["30px", "38px"],
        code: ["14px", "20px"],
      },
      borderRadius: { DEFAULT: "4px", md: "6px", lg: "6px" },
      maxWidth: { page: "1200px" },
    },
  },
  plugins: [],
};
export default config;
