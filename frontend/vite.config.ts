import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // `strictPort` on purpose. The backend opens CORS for exactly http://localhost:5173
    // (roia/api.py DEV_ORIGINS), so a Vite that quietly falls back to 5174 because the
    // port was busy would produce CORS failures that look like a backend bug. Fail loudly.
    port: 5173,
    strictPort: true,
  },
  // No dev proxy, deliberately: every API call — the SSE stream above all — goes straight
  // to VITE_API_BASE. A proxied event stream is buffered and arrives in one lump at the
  // end of the run, which is demo-spec.md §10's named risk.
})
