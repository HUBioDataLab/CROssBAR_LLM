import axios from 'axios';
import Cookies from 'js-cookie';

const instance = axios.create({
  baseURL: 'http://localhost:8000', // Backend URL
  withCredentials: true, // Allow credentials (cookies) to be sent
  headers: {
    'Content-Type': 'application/json',
  },
});



export default instance;