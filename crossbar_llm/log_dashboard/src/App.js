import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { getTheme } from './theme';
import { verifyToken } from './services/api';
import Layout from './components/Layout';
import Login from './pages/Login';
import Overview from './pages/Overview';
import LogsExplorer from './pages/LogsExplorer';
import LogDetail from './pages/LogDetail';
import LiveLogs from './pages/LiveLogs';

// ---------- Auth Context ----------

const AuthContext = createContext(null);

export const useAuth = () => useContext(AuthContext);

function AuthProvider({ children }) {
  const [authenticated, setAuthenticated] = useState(null); // null = loading

  const checkAuth = async () => {
    const token = localStorage.getItem('dashboard_token');
    if (!token) {
      setAuthenticated(false);
      return;
    }
    try {
      await verifyToken();
      setAuthenticated(true);
    } catch {
      localStorage.removeItem('dashboard_token');
      setAuthenticated(false);
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  const loginSuccess = (token) => {
    localStorage.setItem('dashboard_token', token);
    setAuthenticated(true);
  };

  const logout = () => {
    localStorage.removeItem('dashboard_token');
    setAuthenticated(false);
  };

  return (
    <AuthContext.Provider value={{ authenticated, loginSuccess, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// ---------- Protected Route ----------

function ProtectedRoute({ children }) {
  const { authenticated } = useAuth();
  if (authenticated === null) return null; // loading
  if (!authenticated) return <Navigate to="/login" replace />;
  return children;
}

// ---------- Color Mode Context ----------

const ColorModeContext = createContext({ toggleColorMode: () => {} });

export const useColorMode = () => useContext(ColorModeContext);

// ---------- App ----------

export default function App() {
  const [mode, setMode] = useState(() => {
    return localStorage.getItem('dashboard_theme') || 'dark';
  });

  const colorMode = useMemo(
    () => ({
      mode,
      toggleColorMode: () => {
        setMode((prev) => {
          const next = prev === 'dark' ? 'light' : 'dark';
          localStorage.setItem('dashboard_theme', next);
          return next;
        });
      },
    }),
    [mode]
  );

  const theme = useMemo(() => getTheme(mode), [mode]);

  return (
    <ColorModeContext.Provider value={colorMode}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route
                path="/*"
                element={
                  <ProtectedRoute>
                    <Layout />
                  </ProtectedRoute>
                }
              >
                <Route index element={<Overview />} />
                <Route path="logs" element={<LogsExplorer />} />
                <Route path="logs/:requestId" element={<LogDetail />} />
                <Route path="live" element={<LiveLogs />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ThemeProvider>
    </ColorModeContext.Provider>
  );
}
