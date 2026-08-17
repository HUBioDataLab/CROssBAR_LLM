import React, { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Card,
  CardContent,
  Chip,
  Grid,
  Skeleton,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
  useTheme,
} from '@mui/material';
import {
  QueryStats as QueriesIcon,
  CheckCircleOutline as SuccessIcon,
  Speed as LatencyIcon,
  Token as TokenIcon,
  ErrorOutline as ErrorIcon,
} from '@mui/icons-material';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as ReTooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { getStats, getTimeline } from '../services/api';
import { format, parseISO } from 'date-fns';
import { tz } from '@date-fns/tz';

const DASHBOARD_TZ = tz('Europe/Istanbul');

// ---------- Stat Card ----------

function StatCard({ icon, label, value, subtitle, color, loading }) {
  return (
    <Card sx={{ height: '100%' }}>
      <CardContent sx={{ p: 2.5, '&:last-child': { pb: 2.5 } }}>
        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 2 }}>
          <Box
            sx={{
              width: 44,
              height: 44,
              borderRadius: '10px',
              bgcolor: `${color}18`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            {React.cloneElement(icon, { sx: { color, fontSize: 22 } })}
          </Box>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="caption" color="text.secondary" sx={{ mb: 0, display: 'block' }}>
              {label}
            </Typography>
            {loading ? (
              <Skeleton width={80} height={32} />
            ) : (
              <Typography variant="h3" sx={{ mb: 0, lineHeight: 1.2 }}>
                {value}
              </Typography>
            )}
            {subtitle && (
              <Typography variant="caption" color="text.secondary" sx={{ mb: 0 }}>
                {subtitle}
              </Typography>
            )}
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

// ---------- Chart Tooltip ----------

function CustomTooltip({ active, payload, label, formatter }) {
  const theme = useTheme();
  if (!active || !payload?.length) return null;
  return (
    <Box
      sx={{
        bgcolor: 'background.paper',
        border: `1px solid ${theme.palette.divider}`,
        borderRadius: '8px',
        p: 1.5,
        boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
      }}
    >
      <Typography variant="caption" color="text.secondary" sx={{ mb: 0.5, display: 'block' }}>
        {label}
      </Typography>
      {payload.map((p, i) => (
        <Typography key={i} variant="body2" sx={{ color: p.color, mb: 0 }}>
          {p.name}: {formatter ? formatter(p.value) : p.value}
        </Typography>
      ))}
    </Box>
  );
}

// ---------- Page ----------

export default function Overview() {
  const theme = useTheme();
  const navigate = useNavigate();
  const [stats, setStats] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [timeRange, setTimeRange] = useState('7');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchData();
  }, [timeRange]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const days = parseInt(timeRange);
      const granularity = days <= 7 ? 'hour' : 'day';
      const [s, t] = await Promise.all([
        getStats(days),
        getTimeline(days, granularity),
      ]);
      setStats(s);
      setTimeline(t);
    } catch (err) {
      console.error('Failed to fetch overview data:', err);
    } finally {
      setLoading(false);
    }
  };

  const formatDuration = (ms) => {
    if (ms < 1000) return `${Math.round(ms)}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  const formatTokens = (n) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return String(n);
  };

  const timelineFormatted = timeline.map((t) => {
    let label;
    try {
      const d = parseISO(t.time);
      label = timeRange === '7' ? format(d, 'MMM d HH:mm', { in: DASHBOARD_TZ }) : format(d, 'MMM d', { in: DASHBOARD_TZ });
    } catch {
      label = t.time;
    }
    return { ...t, label };
  });

  const PIE_COLORS = [theme.palette.success.main, theme.palette.error.main, theme.palette.warning.main];

  const statusData = stats
    ? [
        { name: 'Completed', value: stats.completed },
        { name: 'Failed', value: stats.failed },
        { name: 'Other', value: Math.max(0, stats.total_queries - stats.completed - stats.failed) },
      ].filter((d) => d.value > 0)
    : [];

  return (
    <Box>
      {/* Time range toggle */}
      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
        <ToggleButtonGroup
          value={timeRange}
          exclusive
          onChange={(_, v) => v && setTimeRange(v)}
          size="small"
        >
          <ToggleButton value="7" sx={{ px: 2 }}>7d</ToggleButton>
          <ToggleButton value="30" sx={{ px: 2 }}>30d</ToggleButton>
          <ToggleButton value="90" sx={{ px: 2 }}>90d</ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {/* Stat cards */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} lg={3}>
          <StatCard
            icon={<QueriesIcon />}
            label="Total Queries"
            value={stats?.total_queries ?? '-'}
            subtitle={`Last ${timeRange} days`}
            color={theme.palette.primary.main}
            loading={loading}
          />
        </Grid>
        <Grid item xs={12} sm={6} lg={3}>
          <StatCard
            icon={<SuccessIcon />}
            label="Success Rate"
            value={stats ? `${stats.success_rate}%` : '-'}
            subtitle={`${stats?.completed ?? 0} completed / ${stats?.failed ?? 0} failed`}
            color={theme.palette.success.main}
            loading={loading}
          />
        </Grid>
        <Grid item xs={12} sm={6} lg={3}>
          <StatCard
            icon={<LatencyIcon />}
            label="Avg Latency"
            value={stats ? formatDuration(stats.avg_duration_ms) : '-'}
            subtitle="Per query"
            color={theme.palette.warning.main}
            loading={loading}
          />
        </Grid>
        <Grid item xs={12} sm={6} lg={3}>
          <StatCard
            icon={<TokenIcon />}
            label="Total Tokens"
            value={stats ? formatTokens(stats.total_tokens) : '-'}
            subtitle={`Last ${timeRange} days`}
            color={theme.palette.info.main}
            loading={loading}
          />
        </Grid>
      </Grid>

      {/* Charts row */}
      <Grid container spacing={2} sx={{ mb: 3 }}>
        {/* Query timeline */}
        <Grid item xs={12} lg={8}>
          <Card>
            <CardContent sx={{ p: 2.5, '&:last-child': { pb: 2.5 } }}>
              <Typography variant="h5" sx={{ mb: 2 }}>
                Queries Over Time
              </Typography>
              {loading ? (
                <Skeleton variant="rectangular" height={260} sx={{ borderRadius: '8px' }} />
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <AreaChart data={timelineFormatted}>
                    <defs>
                      <linearGradient id="colorTotal" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={theme.palette.primary.main} stopOpacity={0.3} />
                        <stop offset="100%" stopColor={theme.palette.primary.main} stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke={theme.palette.divider}
                      vertical={false}
                    />
                    <XAxis
                      dataKey="label"
                      tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
                      axisLine={false}
                      tickLine={false}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
                      axisLine={false}
                      tickLine={false}
                      allowDecimals={false}
                    />
                    <ReTooltip content={<CustomTooltip />} />
                    <Area
                      type="monotone"
                      dataKey="total"
                      name="Queries"
                      stroke={theme.palette.primary.main}
                      fill="url(#colorTotal)"
                      strokeWidth={2}
                    />
                    <Area
                      type="monotone"
                      dataKey="failed"
                      name="Failed"
                      stroke={theme.palette.error.main}
                      fill="transparent"
                      strokeWidth={1.5}
                      strokeDasharray="4 4"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Status donut */}
        <Grid item xs={12} lg={4}>
          <Card sx={{ height: '100%' }}>
            <CardContent sx={{ p: 2.5, '&:last-child': { pb: 2.5 } }}>
              <Typography variant="h5" sx={{ mb: 2 }}>
                Status Breakdown
              </Typography>
              {loading ? (
                <Skeleton variant="circular" width={180} height={180} sx={{ mx: 'auto' }} />
              ) : statusData.length > 0 ? (
                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart>
                      <Pie
                        data={statusData}
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={80}
                        paddingAngle={3}
                        dataKey="value"
                      >
                        {statusData.map((_, i) => (
                          <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                        ))}
                      </Pie>
                      <ReTooltip />
                    </PieChart>
                  </ResponsiveContainer>
                  <Box sx={{ display: 'flex', gap: 2, mt: 1 }}>
                    {statusData.map((d, i) => (
                      <Box key={d.name} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                        <Box
                          sx={{
                            width: 8,
                            height: 8,
                            borderRadius: '50%',
                            bgcolor: PIE_COLORS[i % PIE_COLORS.length],
                          }}
                        />
                        <Typography variant="caption">
                          {d.name} ({d.value})
                        </Typography>
                      </Box>
                    ))}
                  </Box>
                </Box>
              ) : (
                <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 4 }}>
                  No data available
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Bottom row: Model distribution + Recent errors */}
      <Grid container spacing={2}>
        {/* Model distribution */}
        <Grid item xs={12} lg={6}>
          <Card>
            <CardContent sx={{ p: 2.5, '&:last-child': { pb: 2.5 } }}>
              <Typography variant="h5" sx={{ mb: 2 }}>
                Model Usage
              </Typography>
              {loading ? (
                <Skeleton variant="rectangular" height={200} sx={{ borderRadius: '8px' }} />
              ) : stats?.model_distribution?.length > 0 ? (
                <ResponsiveContainer width="100%" height={200}>
                  <BarChart
                    data={stats.model_distribution}
                    layout="vertical"
                    margin={{ left: 0, right: 20 }}
                  >
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke={theme.palette.divider}
                      horizontal={false}
                    />
                    <XAxis
                      type="number"
                      tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
                      axisLine={false}
                      tickLine={false}
                      allowDecimals={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="model"
                      tick={{ fontSize: 11, fill: theme.palette.text.secondary }}
                      axisLine={false}
                      tickLine={false}
                      width={120}
                    />
                    <ReTooltip content={<CustomTooltip />} />
                    <Bar
                      dataKey="count"
                      name="Queries"
                      fill={theme.palette.primary.main}
                      radius={[0, 4, 4, 0]}
                      maxBarSize={28}
                    />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center', mt: 4 }}>
                  No data available
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>

        {/* Recent errors */}
        <Grid item xs={12} lg={6}>
          <Card>
            <CardContent sx={{ p: 2.5, '&:last-child': { pb: 2.5 } }}>
              <Typography variant="h5" sx={{ mb: 2 }}>
                Recent Errors
              </Typography>
              {loading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <Skeleton key={i} height={48} sx={{ mb: 1, borderRadius: '6px' }} />
                ))
              ) : stats?.recent_errors?.length > 0 ? (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                  {stats.recent_errors.map((err) => (
                    <Box
                      key={err.request_id}
                      onClick={() => navigate(`/dashboard/logs/${err.request_id}`)}
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 1.5,
                        p: 1.5,
                        borderRadius: '8px',
                        bgcolor: 'background.subtle',
                        cursor: 'pointer',
                        transition: 'background 0.15s',
                        '&:hover': { bgcolor: 'action.hover' },
                      }}
                    >
                      <ErrorIcon sx={{ color: 'error.main', fontSize: 18, flexShrink: 0 }} />
                      <Box sx={{ minWidth: 0, flex: 1 }}>
                        <Typography variant="body2" noWrap sx={{ mb: 0 }}>
                          {err.question || err.error || 'Unknown error'}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ mb: 0 }}>
                          {err.model_name} &middot;{' '}
                          {err.timestamp
                            ? format(parseISO(err.timestamp), 'MMM d, HH:mm', { in: DASHBOARD_TZ })
                            : ''}
                        </Typography>
                      </Box>
                      <Chip
                        label={err.error_type || 'Error'}
                        size="small"
                        color="error"
                        variant="outlined"
                      />
                    </Box>
                  ))}
                </Box>
              ) : (
                <Box sx={{ textAlign: 'center', py: 4 }}>
                  <SuccessIcon sx={{ fontSize: 40, color: 'success.main', mb: 1 }} />
                  <Typography variant="body2" color="text.secondary">
                    No recent errors
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
