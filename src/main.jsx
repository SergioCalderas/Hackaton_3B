import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import { StoreProvider } from './store.jsx';
import { FiltroProvider } from './lib/filtro.jsx';
import './styles.css';

// HTTPS forzado: cualquier acceso por http (fuera de localhost) se redirige a https.
if (location.protocol === 'http:' && !['localhost', '127.0.0.1'].includes(location.hostname)) {
  location.replace(`https:${location.href.slice(location.protocol.length)}`);
}

createRoot(document.getElementById('root')).render(
  <StoreProvider>
    <FiltroProvider>
      <App />
    </FiltroProvider>
  </StoreProvider>
);
