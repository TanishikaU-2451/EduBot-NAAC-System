const { createProxyMiddleware } = require('http-proxy-middleware')

module.exports = function (app) {
  app.use(
    '/api',
    createProxyMiddleware({
      target: 'http://localhost:8000',
      changeOrigin: true,
      timeout: 300000,        // 5 minutes
      proxyTimeout: 300000,   // 5 minutes
      onError: (err, req, res) => {
        console.error('[Proxy Error]', err.message)
        res.writeHead(502, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ detail: 'Backend proxy error: ' + err.message }))
      },
    })
  )
}
