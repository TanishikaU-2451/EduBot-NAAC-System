const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function(app) {
  console.log('[SETUP] Setting up proxy middleware...');

  app.use(
    '/api',
    createProxyMiddleware({
      target: 'http://localhost:8000',
      changeOrigin: true,
      timeout: 300000,
      proxyTimeout: 300000,
      logLevel: 'debug',
      onProxyReq: (proxyReq, req, res) => {
        console.log('[PROXY] Forwarding:', req.method, req.path, '→', `http://localhost:8000${req.path}`);
      },
      onProxyRes: (proxyRes, req, res) => {
        console.log('[PROXY] Response:', proxyRes.statusCode, req.path);
      },
      onError: (err, req, res) => {
        console.error('[PROXY] Error:', err.message);
        if (!res.headersSent) {
          res.writeHead(502, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ detail: 'Backend proxy error: ' + err.message }));
        }
      },
    })
  );

  console.log('[SETUP] Proxy middleware configured for /api → http://localhost:8000');
};
