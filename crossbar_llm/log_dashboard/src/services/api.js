import axios from 'axios';

const API_BASE =
  process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: `${API_BASE}/dashboard`,
  headers: { 'Content-Type': 'application/json' },
});

// Attach JWT to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('dashboard_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On 401, redirect to login
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('dashboard_token');
      // Only redirect if not already on login page
      if (!window.location.pathname.includes('/login')) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(err);
  }
);

// Auth
export const login = (password) =>
  api.post('/auth/login', { password }).then((r) => r.data);

export const verifyToken = () =>
  api.get('/auth/verify').then((r) => r.data);

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

// Live stream URL (uses query-param auth for EventSource)
export const getStreamUrl = () => {
  const token = localStorage.getItem('dashboard_token');
  return `${API_BASE}/dashboard/api/stream?token=${token}`;
};

export default api;
