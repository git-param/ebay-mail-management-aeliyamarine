import { defineConfig } from 'vite'
import react, { reactCompilerPreset } from '@vitejs/plugin-react'
import babel from '@rolldown/plugin-babel'

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
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
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
