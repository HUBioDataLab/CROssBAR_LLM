import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
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
import { getLogs, getFilters } from '../services/api';
import { format, parseISO } from 'date-fns';

// ---------- Status chip ----------

function StatusChip({ status }) {
  const colorMap = {
    completed: 'success',
    failed: 'error',
    in_progress: 'warning',
    pending: 'default',
  };
  return (
    <Chip
      label={status || 'unknown'}
      size="small"
      color={colorMap[status] || 'default'}
      variant="outlined"
      sx={{ fontWeight: 500 }}
    />
  );
}

// ---------- Helpers ----------

function formatDuration(ms) {
  if (ms == null) return '-';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function truncate(str, len = 60) {
  if (!str) return '-';
  return str.length > len ? str.slice(0, len) + '...' : str;
}

// ---------- Page ----------

export default function LogsExplorer() {
  const theme = useTheme();
  const navigate = useNavigate();

  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState(null);

  // Pagination & filters state
  const [page, setPage] = useState(0); // MUI DataGrid uses 0-based
  const [pageSize, setPageSize] = useState(25);
  const [search, setSearch] = useState('');
  const [searchInput, setSearchInput] = useState('');
  const [status, setStatus] = useState('');
  const [model, setModel] = useState('');
  const [provider, setProvider] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sortModel, setSortModel] = useState([{ field: 'timestamp', sort: 'desc' }]);

  // Fetch filter options once
  useEffect(() => {
    getFilters().then(setFilters).catch(console.error);
  }, []);

  // Fetch data on param changes
  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const sort = sortModel[0] || { field: 'timestamp', sort: 'desc' };
      const data = await getLogs({
        page: page + 1, // API is 1-based
        limit: pageSize,
        search: search || undefined,
        status: status || undefined,
        model: model || undefined,
        provider: provider || undefined,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
        sort_by: sort.field,
        sort_order: sort.sort,
      });
      setRows(data.items.map((item) => ({ ...item, id: item.request_id })));
      setTotal(data.total);
    } catch (err) {
      console.error('Failed to load logs:', err);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, status, model, provider, dateFrom, dateTo, sortModel]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Debounced search
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
    setStatus('');
    setModel('');
    setProvider('');
    setDateFrom('');
    setDateTo('');
    setPage(0);
  };

  const hasActiveFilters = search || status || model || provider || dateFrom || dateTo;

  // CSV export
  const handleExport = () => {
    const headers = [
      'Timestamp',
      'Request ID',
      'Question',
      'Model',
      'Provider',
      'Status',
      'Duration (ms)',
      'Search Type',
    ];
    const csvRows = rows.map((r) =>
      [
        r.timestamp,
        r.request_id,
        `"${(r.question || '').replace(/"/g, '""')}"`,
        r.model_name,
        r.provider,
        r.status,
        r.total_duration_ms,
        r.search_type,
      ].join(',')
    );
    const csv = [headers.join(','), ...csvRows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `logs_export_${format(new Date(), 'yyyy-MM-dd_HH-mm')}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Columns
  const columns = [
    {
      field: 'timestamp',
      headerName: 'Time',
      width: 160,
      renderCell: ({ value }) => {
        try {
          return (
            <Typography variant="body2" sx={{ mb: 0 }}>
              {format(parseISO(value), 'MMM d, HH:mm:ss')}
            </Typography>
          );
        } catch {
          return value;
        }
      },
    },
    {
      field: 'question',
      headerName: 'Question',
      flex: 1,
      minWidth: 250,
      renderCell: ({ value }) => (
        <Tooltip title={value || ''} placement="top-start">
          <Typography variant="body2" noWrap sx={{ mb: 0 }}>
            {truncate(value, 80)}
          </Typography>
        </Tooltip>
      ),
    },
    {
      field: 'model_name',
      headerName: 'Model',
      width: 140,
      renderCell: ({ value }) => (
        <Chip label={value || '-'} size="small" variant="outlined" />
      ),
    },
    {
      field: 'provider',
      headerName: 'Provider',
      width: 110,
    },
    {
      field: 'status',
      headerName: 'Status',
      width: 120,
      renderCell: ({ value }) => <StatusChip status={value} />,
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
      field: 'search_type',
      headerName: 'Type',
      width: 120,
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
            navigate(`/logs/${row.request_id}`);
          }}
        >
          <OpenIcon fontSize="small" />
        </IconButton>
      ),
    },
  ];

  return (
    <Box>
      {/* Filter bar */}
      <Card sx={{ mb: 2 }}>
        <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
          <Box
            sx={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 1.5,
              alignItems: 'center',
            }}
          >
            {/* Search */}
            <TextField
              size="small"
              placeholder="Search questions, IDs, queries..."
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

            {/* Status */}
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Status</InputLabel>
              <Select
                value={status}
                label="Status"
                onChange={(e) => { setStatus(e.target.value); setPage(0); }}
              >
                <MenuItem value="">All</MenuItem>
                {(filters?.statuses || []).map((s) => (
                  <MenuItem key={s} value={s}>{s}</MenuItem>
                ))}
              </Select>
            </FormControl>

            {/* Model */}
            <FormControl size="small" sx={{ minWidth: 140 }}>
              <InputLabel>Model</InputLabel>
              <Select
                value={model}
                label="Model"
                onChange={(e) => { setModel(e.target.value); setPage(0); }}
              >
                <MenuItem value="">All</MenuItem>
                {(filters?.models || []).map((m) => (
                  <MenuItem key={m} value={m}>{m}</MenuItem>
                ))}
              </Select>
            </FormControl>

            {/* Provider */}
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Provider</InputLabel>
              <Select
                value={provider}
                label="Provider"
                onChange={(e) => { setProvider(e.target.value); setPage(0); }}
              >
                <MenuItem value="">All</MenuItem>
                {(filters?.providers || []).map((p) => (
                  <MenuItem key={p} value={p}>{p}</MenuItem>
                ))}
              </Select>
            </FormControl>

            {/* Date from */}
            <TextField
              size="small"
              type="date"
              label="From"
              value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); setPage(0); }}
              InputLabelProps={{ shrink: true }}
              sx={{ width: 150 }}
            />

            {/* Date to */}
            <TextField
              size="small"
              type="date"
              label="To"
              value={dateTo}
              onChange={(e) => { setDateTo(e.target.value); setPage(0); }}
              InputLabelProps={{ shrink: true }}
              sx={{ width: 150 }}
            />

            {/* Actions */}
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

      {/* Results count */}
      <Typography variant="caption" color="text.secondary" sx={{ mb: 1, display: 'block' }}>
        {total} results
      </Typography>

      {/* Data grid */}
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
          onRowClick={(params) => navigate(`/logs/${params.row.request_id}`)}
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
