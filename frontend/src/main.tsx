import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

// Application root — full implementation in Item 7 (Frontend)
const rootEl = document.getElementById('root');
if (!rootEl) throw new Error('Root element not found');

createRoot(rootEl).render(
  <StrictMode>
    <div>
      <h1>Price Pulse</h1>
      <p>Frontend scaffold — full implementation coming in Item 7.</p>
    </div>
  </StrictMode>
);
