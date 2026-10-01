import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, useLocation } from 'react-router-dom';
import App from './App';
import DashboardApp from './dashboard/DashboardApp';
import './index.css';

// Chromium can emit this benign notification when responsive MUI/chart
// components resize each other within one frame. CRA's development overlay
// promotes it to a full-screen runtime error even though the browser retries
// delivery on the next frame and the application remains healthy.
if (process.env.NODE_ENV === 'development') {
  window.addEventListener('error', (event) => {
    if (
      event.message === 'ResizeObserver loop completed with undelivered notifications.'
      || event.message === 'ResizeObserver loop limit exceeded'
    ) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }, true);
}

function Root() {
  const location = useLocation();
  if (location.pathname.startsWith('/dashboard')) {
    return <DashboardApp />;
  }
  return <App />;
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(
  <React.StrictMode>
    <BrowserRouter basename={process.env.PUBLIC_URL || ''}>
      <Root />
    </BrowserRouter>
  </React.StrictMode>
);
