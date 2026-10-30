import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

/* `npm run dev:mock`: serve the API from ../ui/mock/api/*.json, the snapshot the backend writes with
 * scripts/snapshot_api.py. It is shared with ui/, so a fresh snapshot reaches both. Reads only: anything
 * that would change a case is refused with a clear message, never faked. */
const MOCK = resolve(__dirname, '../ui/mock/api')

function mockApi(): Plugin {
  return {
    name: 'redthread-mock-api',
    configureServer(server) {
      server.middlewares.use('/api', (req, res) => {
        res.setHeader('Content-Type', 'application/json')
        if (req.method !== 'GET' || req.url?.includes('/stream')) {
          res.statusCode = 503
          res.end(JSON.stringify({ detail: 'This is the recorded snapshot, so it is read-only. Connect the live backend to approve, challenge or investigate.' }))
          return
        }
        const file = resolve(MOCK, `${(req.url ?? '').split('?')[0].replace(/^\//, '')}.json`)
        if (!file.startsWith(MOCK) || !existsSync(file)) {
          res.statusCode = 404
          res.end(JSON.stringify({ detail: 'Not found.' }))
          return
        }
        res.end(readFileSync(file))
      })
    },
  }
}

export default defineConfig(({ mode }) => ({
  plugins: mode === 'mock' ? [react(), tailwindcss(), mockApi()] : [react(), tailwindcss()],
  resolve: { alias: { '@': resolve(__dirname, 'src') } },
  server: mode === 'mock' ? { port: 5180 } : { port: 5181, proxy: { '/api': 'http://localhost:8000' } },
}))
