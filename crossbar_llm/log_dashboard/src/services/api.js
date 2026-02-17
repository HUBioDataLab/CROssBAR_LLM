import axios from 'axios';

// Determine the API base URL based on environment
const getApiBaseUrl = () => {
  // If explicitly set, use it
  if (process.env.REACT_APP_API_URL) {
    return process.env.REACT_APP_API_URL;
  }
  
  // In development, use localhost
  if (process.env.NODE_ENV === 'development') {
    return 'http://localhost:8000';
  }
  
  // In production, derive from the current location
  // Remove /dashboard from the path if present
  const basePath = window.location.pathname.split('/dashboard')[0] || '';
  return `${window.location.origin}${basePath}/api`;
};

const API_BASE = getApiBaseUrl();

const api = axios.create({
  baseURL: `${API_BASE}/dashboard`,
  headers: { 'Content-Type': 'application/json' },
});

// Stats
export const getStats = (days = 30) =>
  api.get('/api/stats', { params: { days } }).then((r) => r.data);

export const getTimeline = (days = 7, granularity = 'hour') =>
  api.get('/api/stats/timeline', { params: { days, granularity } }).then((r) => r.data);

// Logs
export const getLogs = (params) =>
  api.get('/api/logs', { params }).then((r) => r.data);

export const getLogDetail = (requestId) =>
  api.get(`/api/logs/${requestId}`).then((r) => r.data);

// Filters
export const getFilters = () =>
  api.get('/api/filters').then((r) => r.data);

export default api;
