/**
 * Environment utility to check if we're in development or production mode.
 * This helps with conditional CSRF token handling and other environment-specific behavior.
 */

/**
 * Checks if the current environment is a development environment.
 * @param {Object} environmentInfo - Optional environment info object from API
 * @returns {boolean} True if in development environment, false otherwise
 */
export const isDevelopmentEnvironment = (environmentInfo = null) => {
  // If we received explicit environment info from the API, use it
  if (environmentInfo && typeof environmentInfo.isDevelopment === 'boolean') {
    return environmentInfo.isDevelopment;
  }

  // Check for development mode in React app
  if (process.env.NODE_ENV === 'development') {
    return true;
  }

  // Check for localhost or development domains
  const hostname = window.location.hostname;
  return hostname === 'localhost' || 
         hostname === '127.0.0.1' || 
         hostname.includes('dev.') || 
         hostname.includes('.local');
};

/**
 * Get a placeholder CSRF token for development mode.
 * @returns {string} A development-mode placeholder token
 */
export const getDevelopmentCsrfToken = () => {
  return 'development-mode-no-csrf-required';
};

/**
 * Check if CSRF is required for API requests.
 * @param {Object} environmentInfo - Optional environment info object from API
 * @returns {boolean} True if CSRF is required, false otherwise
 */
export const isCsrfRequired = (environmentInfo = null) => {
  // If we received explicit environment info from the API, use it
  if (environmentInfo && typeof environmentInfo.settings?.csrf_enabled === 'boolean') {
    return environmentInfo.settings.csrf_enabled;
  }
  
  // Otherwise, assume CSRF is required unless in development mode
  return !isDevelopmentEnvironment();
};

/**
 * Fetch environment information from the backend API.
 * @returns {Promise<Object>} Promise resolving to environment info
 */
export const fetchEnvironmentInfo = async () => {
  try {
    const response = await fetch('/environment-info/');
    if (!response.ok) {
      throw new Error(`Failed to fetch environment info: ${response.statusText}`);
    }
    return await response.json();
  } catch (error) {
    console.error('Error fetching environment info:', error);
    // Default to assuming production if we can't fetch info
    return {
      environment: 'production',
      isProduction: true,
      isDevelopment: false,
      settings: {
        csrf_enabled: true,
        rate_limiting_enabled: true
      }
    };
  }
};
