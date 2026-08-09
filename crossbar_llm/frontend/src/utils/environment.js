/**
 * Environment utility to check if we're in development or production mode.
 *
 * Note: the agentic backend (FastAPI) uses an httpOnly browser-identity cookie and
 * does not use CSRF tokens, so the old CSRF / environment-info helpers were removed.
 */

/**
 * Checks if the current environment is a development environment.
 * @returns {boolean} True if in development environment, false otherwise
 */
export const isDevelopmentEnvironment = () => {
  if (process.env.NODE_ENV === 'development') {
    return true;
  }

  const hostname = window.location.hostname;
  return hostname === 'localhost' ||
         hostname === '127.0.0.1' ||
         hostname.includes('dev.') ||
         hostname.includes('.local');
};
