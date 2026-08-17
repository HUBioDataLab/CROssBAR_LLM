import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, useLocation } from 'react-router-dom';
import App from './App';
import DashboardApp from './dashboard/DashboardApp';
import './index.css';

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