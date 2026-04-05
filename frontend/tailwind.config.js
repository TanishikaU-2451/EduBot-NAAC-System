/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  darkMode: 'class', // Enable class-based dark mode
  theme: {
    extend: {
      colors: {
        themeLight: {
          bg: '#fbf8f1',
          bgSecondary: '#f2ece4',
          accent: '#8b8070',
          text: '#2d2926',
          border: '#e4dac9',
          messageUser: '#f1eee6',
          messageAI: '#ffffff',
          buttonPrimary: '#5f6356',
          buttonHover: '#4e5246',
          orangeAccent: '#c35b3f',
        },
        themeDark: {
          bg: '#1e1c1a',
          bgSecondary: '#2a2725',
          accent: '#bfae98',
          text: '#e6ded3',
          border: '#3e3a36',
          messageUser: '#36322e',
          messageAI: '#262422',
          buttonPrimary: '#a5a99c',
          buttonHover: '#b5b9ab',
          orangeAccent: '#d9745a',
        },
        loginUI: {
          bg: '#ffffff',
          bgSecondary: '#fdfdfc',
          text: '#111827',
          bluePrimary: '#2563eb',
          blueHover: '#1d4ed8',
          border: '#e5e7eb',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        serif: ['ui-serif', 'Georgia', 'Cambria', '"Times New Roman"', 'Times', 'serif']
      },
      boxShadow: {
        'soft': '0 4px 20px -2px rgba(0, 0, 0, 0.05)',
        'soft-lg': '0 10px 30px -4px rgba(0, 0, 0, 0.08)',
        'soft-dark': '0 4px 20px -2px rgba(0, 0, 0, 0.4)',
        'soft-lg-dark': '0 10px 30px -4px rgba(0, 0, 0, 0.5)',
      }
    },
  },
  plugins: [
    require('@tailwindcss/typography'),
  ],
}