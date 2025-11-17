import axios from 'axios';
import Cookies from 'js-cookie';

const REACT_APP_CROSSBAR_LLM_ROOT_PATH = process.env.REACT_APP_CROSSBAR_LLM_ROOT_PATH || '/llm';

const baseURL = process.env.NODE_ENV === 'development' 
  ? `http://localhost:8000`
  : `https://crossbarv2.hubiodatalab.com${REACT_APP_CROSSBAR_LLM_ROOT_PATH}/api`;

const instance = axios.create({
  baseURL: baseURL, // Backend URL
  withCredentials: true, // Allow credentials (cookies) to be sent
  headers: {
    'Content-Type': 'application/json',
  },
});

// Function to get client IP address
const getClientIP = async () => {
  try {
    // Try to get IP from public API
    const response = await fetch('https://api.ipify.org?format=json');
    if (response.ok) {
      const data = await response.json();
      return data.ip;
    }
    return null;
  } catch (error) {
    console.error('Error getting client IP:', error);
    return null;
  }
};

// Add client IP to every request if possible
instance.interceptors.request.use(async (config) => {
  try {
    // Try to get IP from sessionStorage first (to avoid multiple calls)
    let clientIP = sessionStorage.getItem('client_ip');
    
    // If not in storage, try to fetch it
    if (!clientIP) {
      clientIP = await getClientIP();
      if (clientIP) {
        sessionStorage.setItem('client_ip', clientIP);
      }
    }
    
    // Add client IP to request headers
    if (clientIP) {
      config.headers['X-Client-IP'] = clientIP;
      
      // Also add to request body if it's a POST/PUT request with JSON body
      if (['post', 'put'].includes(config.method)) {
        if (config.data instanceof FormData) {
          // Handle FormData (for file uploads)
          config.data.append('client_ip', clientIP);
        } else if (typeof config.data === 'string') {
          // If data is already stringified JSON
          try {
            const data = JSON.parse(config.data);
            data.client_ip = clientIP;
            config.data = JSON.stringify(data);
          } catch (error) {
            console.error('Error parsing JSON string in request interceptor:', error);
          }
        } else if (config.data && typeof config.data === 'object') {
          // If data is a JavaScript object
          config.data = {
            ...config.data,
            client_ip: clientIP
          };
        }
      }
    }
    
    return config;
  } catch (error) {
    console.error('Error adding client IP to request:', error);
    return config;
  }
});

// CSRF token refresh function
const refreshCsrfToken = async () => {
  try {
    const clientIP = sessionStorage.getItem('client_ip');
    const headers = {};
    if (clientIP) {
      headers['X-Client-IP'] = clientIP;
    }
    
    const response = await axios.get('/csrf-token/', {
      baseURL: instance.defaults.baseURL,
      withCredentials: true,
      headers
    });
    
    console.log('CSRF token refreshed in api instance');
    const csrfToken = response.data.csrf_token;
    instance.defaults.headers['X-CSRF-Token'] = csrfToken;
    return csrfToken;
  } catch (error) {
    console.error('Error refreshing CSRF token:', error);
    throw error;
  }
};

// Add a response interceptor to handle CSRF token expiration
let isRefreshing = false;
let failedQueue = [];

const processQueue = (error, token = null) => {
  failedQueue.forEach(prom => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  
  failedQueue = [];
};

instance.interceptors.response.use(
  response => response,
  async error => {
    const originalRequest = error.config;
    
    // Check if error is related to CSRF token
    if (error.response && 
        (error.response.status === 400 || error.response.status === 403) && 
        (error.response.data?.detail?.includes('CSRF') || 
         error.response.data?.detail?.includes('csrf')) &&
        !originalRequest._retry) {
      
      // If we're already refreshing, add to queue
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        })
          .then(token => {
            originalRequest.headers['X-CSRF-Token'] = token;
            return instance(originalRequest);
          })
          .catch(err => {
            return Promise.reject(err);
          });
      }
      
      originalRequest._retry = true;
      isRefreshing = true;
      
      try {
        const token = await refreshCsrfToken();
        // Update original request with new token
        originalRequest.headers['X-CSRF-Token'] = token;
        
        // Process any requests in the queue
        processQueue(null, token);
        return instance(originalRequest);
      } catch (refreshError) {
        processQueue(refreshError, null);
        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }
    
    return Promise.reject(error);
  }
);

export const streamLogs = (onMessage, onError) => {
  const eventSource = new EventSource('/stream-logs');
  
  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.log) {
        onMessage(data.log);
      }
    } catch (error) {
      console.error('Error parsing log message:', error);
    }
  };

  eventSource.onerror = (error) => {
    console.error('EventSource failed:', error);
    if (onError) {
      onError(error);
    }
    eventSource.close();
  };

  return eventSource;
};

export const getAvailableModels = async () => {
  try {
    const response = await instance.get('/models/');
    return response.data;
  } catch (error) {
    console.error('Error fetching available models:', error);
    throw error;
  }
};

// Export the refreshCsrfToken function for explicit usage
export { refreshCsrfToken };

export default instance;