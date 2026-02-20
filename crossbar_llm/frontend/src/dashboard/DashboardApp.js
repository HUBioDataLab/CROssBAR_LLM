import React, { createContext, useContext, useMemo, useState } from 'react';
import { Routes, Route } from 'react-router-dom';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { getTheme } from './theme';
import Layout from './components/Layout';
import Overview from './pages/Overview';
import LogsExplorer from './pages/LogsExplorer';
import LogDetail from './pages/LogDetail';

// ---------- Color Mode Context ----------

const ColorModeContext = createContext({ toggleColorMode: () => {} });

export const useColorMode = () => useContext(ColorModeContext);

// ---------- App ----------

export default function DashboardApp() {
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
        <Routes>
          <Route path="/dashboard" element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="logs" element={<LogsExplorer />} />
            <Route path="logs/:requestId" element={<LogDetail />} />
          </Route>
        </Routes>
      </ThemeProvider>
    </ColorModeContext.Provider>
  );
}
