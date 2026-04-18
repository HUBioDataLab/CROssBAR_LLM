import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Card,
  CardContent,
  Chip,
  FormControl,
  IconButton,
  InputAdornment,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';
import {
  Search as SearchIcon,
  Download as DownloadIcon,
  Refresh as RefreshIcon,
  OpenInNew as OpenIcon,
  Clear as ClearIcon,
} from '@mui/icons-material';
import { getSessions, getSessionFilters } from '../services/api';
import { format, parseISO } from 'date-fns';
import { tz } from '@date-fns/tz';

const DASHBOARD_TZ = tz('Europe/Istanbul');

function formatDuration(ms) {
  if (ms == null) return '-';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function truncate(str, len = 60) {
  if (!str) return '-';
  return str.length > len ? str.slice(0, len) + '...' : str;
}

function StatusSummaryChips({ summary }) {
  if (!summary) return '-';
  return (
    <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
      {Object.entries(summary).map(([status, count]) => (
        <Chip
          key={status}
          label={`${count} ${status}`}
          size="small"
          color={status === 'completed' ? 'success' : status === 'failed' ? 'error' : 'default'}
          variant="outlined"
          sx={{ fontSize: '0.65rem', height: 20 }}
        />
      ))}
    </Box>
  );
}

function ModelsChips({ models }) {
  if (!models?.length) return '-';
  return (
    <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
      {models.slice(0, 2).map((m) => (
        <Chip key={m} label={m} size="small" variant="outlined" sx={{ fontSize: '0.65rem', height: 20 }} />
      ))}
      {models.length > 2 && (
        <Chip label={`+${models.length - 2}`} size="small" sx={{ fontSize: '0.65rem', height: 20 }} />
      )}
    </Box>
  );
}

export default function SessionsExplorer() {
  const theme = useTheme();
  const navigate = useNavigate();

  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState(null);

  const [page, setPage] = useState(0);
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [clientId, setClientId] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sortModel, setSortModel] = useState([{ field: 'last_activity', sort: 'desc' }]);

  useEffect(() => {
    getSessionFilters().then(setFilters).catch(console.error);
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const sort = sortModel[0] || { field: 'last_activity', sort: 'desc' };
      const data = await getSessions({
        page: page + 1,
        limit: pageSize,
        search: search || undefined,
        client_id: clientId || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        sort_by: sort.field,
        sort_order: sort.sort,
      });
      setRows(data.items.map((item) => ({ ...item, id: item.session_id })));
      setTotal(data.total);
    } catch (err) {
      console.error('Failed to load sessions:', err);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, clientId, dateFrom, dateTo, sortModel]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setPage(0);
    }, 400);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const handleClearFilters = () => {
    setSearchInput('');
    setSearch('');
    setClientId('');
    setDateFrom('');
    setDateTo('');
    setPage(0);
  };

  const hasActiveFilters = search || clientId || dateFrom || dateTo;

  const handleExport = () => {
    const headers = ['Session ID', 'Client ID', 'First Activity', 'Last Activity', 'Turns', 'Models', 'Duration (ms)'];
    const csvRows = rows.map((r) =>
      [r.session_id, r.client_id, r.first_activity, r.last_activity, r.turn_count, `"${(r.models_used || []).join(', ')}"`, r.total_duration_ms].join(',')
    );
    const csv = [headers.join(','), ...csvRows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `sessions_export_${format(new Date(), 'yyyy-MM-dd_HH-mm', { in: DASHBOARD_TZ })}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const columns = [
    {
      field: 'last_activity',
      headerName: 'Last Activity',
      width: 170,
      renderCell: ({ value }) => {
        try {
          return (
            <Typography variant="body2" sx={{ mb: 0 }}>
              {format(parseISO(value), 'MMM d, HH:mm:ss', { in: DASHBOARD_TZ })}
            </Typography>
          );
        } catch {
          return value;
        }
      },
    },
    {
      field: 'session_id',
      headerName: 'Session ID',
      width: 150,
      renderCell: ({ value }) => (
        <Tooltip title={value}>
          <Typography variant="body2" sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.75rem', mb: 0 }}>
            {value ? `${value.slice(0, 8)}...` : '-'}
          </Typography>
        </Tooltip>
      ),
    },
    {
      field: 'first_question',
      headerName: 'First Question',
      flex: 1,
      minWidth: 200,
      renderCell: ({ value }) => (
        <Tooltip title={value || ''} placement="top-start">
          <Typography variant="body2" noWrap sx={{ mb: 0 }}>
            {truncate(value, 80)}
          </Typography>
        </Tooltip>
      ),
    },
    {
      field: 'turn_count',
      headerName: 'Turns',
      width: 80,
      renderCell: ({ value }) => (
        <Chip label={value || 0} size="small" color="primary" variant="outlined" sx={{ fontWeight: 600 }} />
      ),
    },
    {
      field: 'models_used',
      headerName: 'Models',
      width: 180,
      renderCell: ({ value }) => <ModelsChips models={value} />,
    },
    {
      field: 'status_summary',
      headerName: 'Status',
      width: 160,
      renderCell: ({ value }) => <StatusSummaryChips summary={value} />,
    },
    {
      field: 'total_duration_ms',
      headerName: 'Duration',
      width: 100,
      renderCell: ({ value }) => (
        <Typography variant="body2" sx={{ fontFamily: '"JetBrains Mono", monospace', mb: 0 }}>
          {formatDuration(value)}
        </Typography>
      ),
    },
    {
      field: 'actions',
      headerName: '',
      width: 50,
      sortable: false,
      renderCell: ({ row }) => (
        <IconButton
          size="small"
          onClick={(e) => {
            e.stopPropagation();
            navigate(`/dashboard/sessions/${row.session_id}`);
          }}
        >
          <OpenIcon fontSize="small" />
        </IconButton>
      ),
    },
  ];

  return (
    <Box>
      <Card sx={{ mb: 2 }}>
        <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
            <TextField
              size="small"
              placeholder="Search session IDs, questions..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              InputProps={{
                startAdornment: (
                  <InputAdornment position="start">
                    <SearchIcon fontSize="small" color="action" />
                  </InputAdornment>
                ),
              }}
              sx={{ minWidth: 260, flex: 1 }}
            />

            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel>Client</InputLabel>
              <Select
                value={clientId}
                label="Client"
                onChange={(e) => { setClientId(e.target.value); setPage(0); }}
              >
                <MenuItem value="">All</MenuItem>
                {(filters?.client_ids || []).map((c) => (
                  <MenuItem key={c} value={c}>
                    <Typography variant="body2" sx={{ fontFamily: '"JetBrains Mono", monospace', fontSize: '0.8rem' }}>
                      {c}
                    </Typography>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <TextField
              size="small"
              type="date"
              label="From"
              value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); setPage(0); }}
              InputLabelProps={{ shrink: true }}
              sx={{ width: 150 }}
            />

            <TextField
              size="small"
              type="date"
              label="To"
              value={dateTo}
              onChange={(e) => { setDateTo(e.target.value); setPage(0); }}
              InputLabelProps={{ shrink: true }}
              sx={{ width: 150 }}
            />

            {hasActiveFilters && (
              <Tooltip title="Clear filters">
                <IconButton size="small" onClick={handleClearFilters}>
                  <ClearIcon fontSize="small" />
                </IconButton>
              </Tooltip>
            )}
            <Tooltip title="Refresh">
              <IconButton size="small" onClick={fetchData}>
                <RefreshIcon fontSize="small" />
              </IconButton>
            </Tooltip>
            <Tooltip title="Export CSV">
              <IconButton size="small" onClick={handleExport} disabled={rows.length === 0}>
                <DownloadIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          </Box>
        </CardContent>
      </Card>

      <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
        {total} sessions
      </Typography>

      <Card>
        <DataGrid
          rows={rows}
          columns={columns}
          loading={loading}
          rowCount={total}
          paginationMode="server"
          paginationModel={{ page, pageSize }}
          onPaginationModelChange={({ page: p, pageSize: ps }) => {
            setPage(p);
            setPageSize(ps);
          }}
          pageSizeOptions={[10, 25, 50, 100]}
          sortingMode="server"
          sortModel={sortModel}
          onSortModelChange={(m) => {
            setSortModel(m);
            setPage(0);
          }}
          onRowClick={(params) => navigate(`/dashboard/sessions/${params.row.session_id}`)}
          disableRowSelectionOnClick
          autoHeight
          sx={{
            border: 'none',
            '& .MuiDataGrid-row': {
              cursor: 'pointer',
              '&:hover': { bgcolor: 'action.hover' },
            },
            '& .MuiDataGrid-cell': {
              borderBottom: (t) => `1px solid ${t.palette.divider}`,
              py: 1,
            },
            '& .MuiDataGrid-columnHeaders': {
              borderBottom: (t) => `1px solid ${t.palette.divider}`,
              bgcolor: 'background.subtle',
            },
            '& .MuiDataGrid-footerContainer': {
              borderTop: (t) => `1px solid ${t.palette.divider}`,
            },
          }}
        />
      </Card>
    </Box>
  );
}
