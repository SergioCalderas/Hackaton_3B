import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import basicSsl from '@vitejs/plugin-basic-ssl';
import fs from 'node:fs';

// Cabeceras de seguridad (desarrollo y preview). HSTS se define en el hosting (ver public/_headers).
const headers = {
  'X-Content-Type-Options': 'nosniff',
  'Referrer-Policy': 'strict-origin-when-cross-origin',
  'X-Frame-Options': 'SAMEORIGIN',
  'Permissions-Policy': 'camera=(), microphone=(), geolocation=()',
};

// Content-Security-Policy: solo se inyecta en build (en dev rompería el HMR de Vite)
const csp = [
  "default-src 'self'",
  "script-src 'self' https://accounts.google.com/gsi/client",
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://accounts.google.com/gsi/style",
  'font-src https://fonts.gstatic.com',
  "img-src 'self' data: https://*.googleusercontent.com",
  "frame-src 'self' https://accounts.google.com https://maps.google.com https://www.google.com",
  "connect-src 'self' https://accounts.google.com",
  "object-src 'self'",
  "base-uri 'self'",
  "form-action 'self'",
  'upgrade-insecure-requests',
].join('; ');

const cspPlugin = {
  name: 'inject-csp',
  apply: 'build',
  transformIndexHtml: (html) => html.replace('<head>', `<head>\n    <meta http-equiv="Content-Security-Policy" content="${csp}" />`),
};

// Canal seguro local: certificado de confianza creado con mkcert (npm run https:setup).
// Si no existe, se usa un certificado autofirmado (el navegador mostrará una advertencia).
const hasCert = fs.existsSync('certs/localhost.pem') && fs.existsSync('certs/localhost-key.pem');
const https = hasCert ? { key: fs.readFileSync('certs/localhost-key.pem'), cert: fs.readFileSync('certs/localhost.pem') } : undefined;

export default defineConfig({
  plugins: [react(), ...(hasCert ? [] : [basicSsl()]), cspPlugin],
  server: { headers, https, proxy: { '/api': 'http://127.0.0.1:5000' } },
  preview: { headers, https },
});
