import type { Config } from 'tailwindcss';

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        accent: 'oklch(0.52 0.135 225)',
        accentSoft: 'oklch(0.93 0.035 225)',
        background: 'oklch(0.972 0.009 215)',
        border: 'oklch(0.86 0.018 220)',
        danger: 'oklch(0.585 0.15 28)',
        foreground: 'oklch(0.205 0.022 230)',
        muted: 'oklch(0.485 0.03 230)',
        panel: 'oklch(0.955 0.01 215)',
        paper: 'oklch(0.992 0.006 215)',
        success: 'oklch(0.59 0.12 155)',
        warning: 'oklch(0.675 0.135 80)'
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Consolas', 'monospace'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'Segoe UI', 'sans-serif']
      },
      boxShadow: {
        hairline: '0 0 0 1px oklch(0.86 0.018 220)',
        panel: '0 12px 30px rgb(36 51 66 / 0.08)'
      }
    }
  },
  plugins: []
} satisfies Config;
