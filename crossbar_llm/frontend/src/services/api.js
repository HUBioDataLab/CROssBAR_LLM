import axios from 'axios';
import Cookies from 'js-cookie';

const instance = axios.create({
  baseURL: 'https://crossbarv2.hubiodatalab.com/llm/api', // Backend URL
  withCredentials: true, // Allow credentials (cookies) to be sent
  headers: {
    'Content-Type': 'application/json',
  },
});



export default instance;