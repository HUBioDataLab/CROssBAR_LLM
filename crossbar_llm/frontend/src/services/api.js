import axios from 'axios';
import Cookies from 'js-cookie';

const instance = axios.create({
  baseURL: 'http://localhost:8000', // Backend URL
  withCredentials: true, // Allow credentials (cookies) to be sent
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add a request interceptor to include the CSRF token
instance.interceptors.request.use((config) => {
  const csrfToken = Cookies.get('fastapi-csrf-token');
  console.log('CSRF token:', csrfToken);
  if (csrfToken) {
    config.headers['X-CSRF-Token'] = csrfToken;
  }
  return config;
}, (error) => {
  return Promise.reject(error);
});

export default instance;