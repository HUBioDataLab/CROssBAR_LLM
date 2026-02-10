import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material';
import {
  PlayArrow as PlayIcon,
  Pause as PauseIcon,
  Delete as ClearIcon,
  VerticalAlignBottom as AutoScrollIcon,
  VerticalAlignCenter as NoScrollIcon,
  Circle as DotIcon,
  Search as SearchIcon,
} from '@mui/icons-material';
import { getStreamUrl } from '../services/api';

// ---------- Constants ----------

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'];

const LEVEL_COLORS = {
  DEBUG: '#94a3b8',
  INFO: '#60a5fa',
  WARNING: '#fbbf24',
  ERROR: '#f87171',
  CRITICAL: '#ef4444',
};

const MAX_LINES = 2000;

// ---------- Helpers ----------

function parseLogLevel(line) {
  for (const level of LOG_LEVELS) {
    if (line.includes(` - ${level} - `) || line.includes(` ${level} `)) {
      return level;
    }
  }
  return 'INFO';
}

function LogLine({ line, highlight }) {
  const theme = useTheme();
  const level = parseLogLevel(line);
  const color = LEVEL_COLORS[level] || theme.palette.text.primary;

  // Highlight search terms
  let content = line;
  if (highlight) {
    const idx = line.toLowerCase().indexOf(highlight.toLowerCase());
    if (idx >= 0) {
      const before = line.slice(0, idx);
      const match = line.slice(idx, idx + highlight.length);
      const after = line.slice(idx + highlight.length);
      content = (
        <>
          {before}
          <Box
            component="span"
            sx={{
              bgcolor: 'warning.main',
              color: '#000',
              borderRadius: '2px',
              px: 0.25,
            }}
          >
            {match}
          </Box>
          {after}
        </>
      );
    }
  }

  return (
    <Box
      sx={{
        py: 0.25,
        px: 1.5,
        borderLeft: `3px solid ${color}`,
        fontSize: '0.8125rem',
        fontFamily: '"JetBrains Mono", monospace',
        lineHeight: 1.6,
        color: theme.palette.mode === 'dark' ? '#e2e8f0' : '#1e293b',
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-all',
        '&:hover': {
          bgcolor:
            theme.palette.mode === 'dark'
              ? 'rgba(255,255,255,0.02)'
              : 'rgba(0,0,0,0.01)',
        },
      }}
    >
      {content}
    </Box>
  );
}

// ---------- Page ----------

export default function LiveLogs() {
  const theme = useTheme();
  const containerRef = useRef(null);
  const eventSourceRef = useRef(null);

  const [lines, setLines] = useState([]);
  const [connected, setConnected] = useState(false);
  const [paused, setPaused] = useState(false);
  const [autoScroll, setAutoScroll] = useState(true);
  const [levelFilter, setLevelFilter] = useState('ALL');
  const [searchTerm, setSearchTerm] = useState('');

  // Pause buffer -- stores lines while paused
  const pauseBufferRef = useRef([]);

  // Connect to SSE
  const connect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const url = getStreamUrl();
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.addEventListener('log', (event) => {
      try {
        const data = JSON.parse(event.data);
        const logLine = data.log || data;
        if (typeof logLine === 'string' && logLine.trim()) {
          if (paused) {
            pauseBufferRef.current.push(logLine);
          } else {
            setLines((prev) => {
              const next = [...prev, logLine];
              return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next;
            });
          }
        }
      } catch {
        // ignore parse errors
      }
    });

    es.addEventListener('ping', () => {
      // keepalive -- ignore
    });

    es.onopen = () => setConnected(true);
    es.onerror = () => {
      setConnected(false);
      // Auto-reconnect after 3s
      setTimeout(() => {
        if (eventSourceRef.current === es) {
          connect();
        }
      }, 3000);
    };
  }, [paused]);

  useEffect(() => {
    connect();
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // When unpausing, flush the buffer
  useEffect(() => {
    if (!paused && pauseBufferRef.current.length > 0) {
      setLines((prev) => {
        const merged = [...prev, ...pauseBufferRef.current];
        pauseBufferRef.current = [];
        return merged.length > MAX_LINES ? merged.slice(-MAX_LINES) : merged;
      });
    }
  }, [paused]);

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [lines, autoScroll]);

  // Filter lines
  const filteredLines = lines.filter((line) => {
    if (levelFilter !== 'ALL') {
      const level = parseLogLevel(line);
      const levelIdx = LOG_LEVELS.indexOf(level);
      const filterIdx = LOG_LEVELS.indexOf(levelFilter);
      if (levelIdx < filterIdx) return false;
    }
    if (searchTerm) {
      return line.toLowerCase().includes(searchTerm.toLowerCase());
    }
    return true;
  });

  const handleClear = () => {
    setLines([]);
    pauseBufferRef.current = [];
  };

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 140px)' }}>
      {/* Toolbar */}
      <Card sx={{ mb: 2, flexShrink: 0 }}>
        <CardContent sx={{ p: 1.5, '&:last-child': { pb: 1.5 } }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, flexWrap: 'wrap' }}>
            {/* Connection status */}
            <Chip
              icon={<DotIcon sx={{ fontSize: '10px !important' }} />}
              label={connected ? 'Connected' : 'Disconnected'}
              size="small"
              color={connected ? 'success' : 'error'}
              variant="outlined"
              sx={{ '& .MuiChip-icon': { color: 'inherit' } }}
            />

            {/* Pause / Resume */}
            <Tooltip title={paused ? 'Resume' : 'Pause'}>
              <IconButton
                size="small"
                onClick={() => setPaused(!paused)}
                color={paused ? 'warning' : 'default'}
              >
                {paused ? <PlayIcon /> : <PauseIcon />}
              </IconButton>
            </Tooltip>

            {/* Auto-scroll toggle */}
            <Tooltip title={autoScroll ? 'Disable auto-scroll' : 'Enable auto-scroll'}>
              <IconButton
                size="small"
                onClick={() => setAutoScroll(!autoScroll)}
                color={autoScroll ? 'primary' : 'default'}
              >
                {autoScroll ? <AutoScrollIcon /> : <NoScrollIcon />}
              </IconButton>
            </Tooltip>

            {/* Clear */}
            <Tooltip title="Clear logs">
              <IconButton size="small" onClick={handleClear}>
                <ClearIcon fontSize="small" />
              </IconButton>
            </Tooltip>

            {/* Level filter */}
            <FormControl size="small" sx={{ minWidth: 110 }}>
              <InputLabel>Level</InputLabel>
              <Select
                value={levelFilter}
                label="Level"
                onChange={(e) => setLevelFilter(e.target.value)}
              >
                <MenuItem value="ALL">All Levels</MenuItem>
                {LOG_LEVELS.map((l) => (
                  <MenuItem key={l} value={l}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
                      <Box
                        sx={{
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          bgcolor: LEVEL_COLORS[l],
                        }}
                      />
                      {l}
                    </Box>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            {/* Search */}
            <TextField
              size="small"
              placeholder="Filter logs..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              InputProps={{
                startAdornment: <SearchIcon fontSize="small" sx={{ mr: 0.5, color: 'text.secondary' }} />,
              }}
              sx={{ minWidth: 200 }}
            />

            <Box sx={{ flex: 1 }} />

            {/* Line count */}
            <Typography variant="caption" color="text.secondary" sx={{ mb: 0 }}>
              {filteredLines.length} lines
              {paused && ` (${pauseBufferRef.current.length} buffered)`}
            </Typography>
          </Box>
        </CardContent>
      </Card>

      {/* Log output */}
      <Card
        sx={{
          flex: 1,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          bgcolor: theme.palette.mode === 'dark' ? '#0c0c10' : '#fafbfc',
        }}
      >
        <Box
          ref={containerRef}
          sx={{
            flex: 1,
            overflow: 'auto',
            py: 1,
            '&::-webkit-scrollbar': { width: '6px' },
            '&::-webkit-scrollbar-thumb': {
              bgcolor: theme.palette.mode === 'dark' ? '#334155' : '#cbd5e1',
              borderRadius: '3px',
            },
          }}
        >
          {filteredLines.length === 0 ? (
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                flexDirection: 'column',
                gap: 1,
              }}
            >
              <Typography variant="body2" color="text.secondary">
                {lines.length === 0
                  ? 'Waiting for log messages...'
                  : 'No logs match current filters'}
              </Typography>
              {lines.length === 0 && connected && (
                <Typography variant="caption" color="text.secondary">
                  Logs will appear here in real time as the backend processes requests.
                </Typography>
              )}
            </Box>
          ) : (
            filteredLines.map((line, i) => (
              <LogLine key={i} line={line} highlight={searchTerm} />
            ))
          )}
        </Box>
      </Card>
    </Box>
  );
}
