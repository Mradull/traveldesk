import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Vitest settings for `npm test` (Agile Spec v2.0 > Testing strategy: src/__tests__/*.test.jsx)
  test: {
    environment: 'jsdom', // browser-like DOM so React components can render in tests
    globals: true,        // describe / it / expect without imports
  },
})
