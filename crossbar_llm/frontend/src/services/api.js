import axios from 'axios';
import Cookies from 'js-cookie';

const REACT_APP_CROSSBAR_LLM_ROOT_PATH = process.env.REACT_APP_CROSSBAR_LLM_ROOT_PATH || '/llm';

const instance = axios.create({
  baseURL: `https://crossbarv2.hubiodatalab.com${REACT_APP_CROSSBAR_LLM_ROOT_PATH}/api`, // Backend URL
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

export default instance;