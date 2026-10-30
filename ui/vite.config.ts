import { readFileSync, existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'

/* `vite --mode mock` (npm run dev:mock): serve the API from ui/mock/api/*.json, written by
 * scripts/snapshot_api.py, so the workbench runs without the dataset, the graph or any keys.
 * Reads only: anything that would change a case is refused with a clear message, never faked. */
function mockApi(): Plugin {
  return {
    name: 'redthread-mock-api',
    configureServer(server) {
      server.middlewares.use('/api', (req, res) => {
        res.setHeader('Content-Type', 'application/json')
        if (req.method !== 'GET' || req.url?.includes('/stream')) {
          res.statusCode = 503
          res.end(JSON.stringify({ detail: 'Mock mode is read-only: run the real backend to approve, challenge or investigate.' }))
          return
        }
        const file = resolve(__dirname, 'mock/api', `${(req.url ?? '').split('?')[0].replace(/^\//, '')}.json`)
        if (!existsSync(file)) {
          res.statusCode = 404
          res.end(JSON.stringify({ detail: 'Not in the mock snapshot: run scripts/snapshot_api.py.' }))
          return
        }
        res.end(readFileSync(file))
      })
    },
  }
}

export default defineConfig(({ mode }) => ({
  plugins: mode === 'mock' ? [react(), mockApi()] : [react()],
  server: mode === 'mock' ? {} : { proxy: { '/api': 'http://localhost:8000' } },
}))
