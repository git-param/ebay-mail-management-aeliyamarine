import { defineConfig } from 'vite'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'
import { API_PROXY_PREFIX, DEFAULT_BACKEND_URL } from './src/constants/api.js'

function devRequestLogger() {
  return {
    name: 'dev-request-logger',
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const startedAt = Date.now()
        const method = req.method || 'GET'
        const url = req.url || '/'

        res.on('finish', () => {
          const elapsedMs = Date.now() - startedAt
          server.config.logger.info(
            `[vite:request] ${method} ${url} ${res.statusCode} ${elapsedMs}ms`,
          )
        })

        next()
      })
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  clearScreen: false,
  logLevel: 'info',
  server: {
    allowedHosts: [".trycloudflare.com"],

    proxy: {
      [API_PROXY_PREFIX]: {
        target: DEFAULT_BACKEND_URL,
        changeOrigin: true,
      },
    },
  },
  plugins: [
    react(),
    babel({ presets: [reactCompilerPreset()] }),
    devRequestLogger(),
  ],
})
