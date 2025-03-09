import axios from 'axios';
import Cookies from 'js-cookie';

const instance = axios.create({
  baseURL: 'https://crossbarv2.hubiodatalab.com/llm/api', // Backend URL
  withCredentials: true, // Allow credentials (cookies) to be sent
  headers: {
    'Content-Type': 'application/json',
  },
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