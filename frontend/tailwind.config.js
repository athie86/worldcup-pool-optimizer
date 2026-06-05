/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        'red-900': '#7A0019',
        'red-700': '#AA151B',
        'red-500': '#C91F25',
        'gold-500': '#F1BF00',
        'gold-300': '#FFD95A',
        'navy-950': '#07111F',
        'navy-900': '#0B1726',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Roboto Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
