import React from 'react';
import {
  Box,
  Typography,
  Paper,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  InputAdornment,
  Switch,
  FormControlLabel,
  Checkbox,
  Divider,
  Collapse,
  alpha,
  useTheme,
} from '@mui/material';
import TuneIcon from '@mui/icons-material/Tune';
import KeyIcon from '@mui/icons-material/Key';
import InfoOutlinedIcon from '@mui/icons-material/InfoOutlined';
import SectionHeader from './SectionHeader';
import { supportedModels, isModelSupported } from '../../constants';

/**
 * Model settings section for the right panel.
 */
function ModelSettings({
  expanded,
  onToggle,
  provider,
  setProvider,
  llmType,
  setLlmType,
  apiKey,
  setApiKey,
  apiKeysStatus,
  apiKeysLoaded,
  modelChoices,
  topK,
  setTopK,
  verbose,
  setVerbose,
  isSettingsValid,
}) {
  const theme = useTheme();

  const handleProviderChange = (e) => {
    const selectedProvider = e.target.value;
    setProvider(selectedProvider);
    // Auto-select first model
    if (selectedProvider && modelChoices[selectedProvider]) {
      const firstModel = modelChoices[selectedProvider].find(m => typeof m === 'string');
      if (firstModel) setLlmType(firstModel);
      else setLlmType('');
    } else {
      setLlmType('');
    }
  };

  return (
    <Paper 
      elevation={0} 
      sx={{ 
        mb: 2, 
        borderRadius: '16px', 
        border: `1px solid ${theme.palette.divider}`, 
        overflow: 'hidden' 
      }}
    >
      <SectionHeader 
        title="Model Settings" 
        icon={<TuneIcon fontSize="small" color="primary" />} 
        expanded={expanded}
        onToggle={onToggle}
        badge={!isSettingsValid ? "Required" : null}
      />
      <Collapse in={expanded}>
        <Box sx={{ p: 2, pt: 0 }}>
          <FormControl fullWidth size="small" sx={{ mb: 2 }}>
            <InputLabel>Provider</InputLabel>
            <Select 
              value={provider} 
              onChange={handleProviderChange} 
              label="Provider"
            >
              <MenuItem value=""><em>Select a provider</em></MenuItem>
              {Object.keys(modelChoices).map((p) => (
                <MenuItem key={p} value={p}>{p}</MenuItem>
              ))}
            </Select>
          </FormControl>
          
          <FormControl fullWidth size="small" sx={{ mb: 2 }}>
            <InputLabel>Model</InputLabel>
            <Select 
              value={llmType} 
              onChange={(e) => setLlmType(e.target.value)} 
              label="Model" 
              disabled={!provider}
            >
              <MenuItem value=""><em>Select a model</em></MenuItem>
              {provider && modelChoices[provider]?.map((m, idx) => {
                if (typeof m === 'object' && m.value === 'separator') {
                  return <Divider key={`sep-${idx}`} sx={{ my: 1 }} />;
                }
                if (typeof m === 'object' && m.value === 'label') {
                  return (
                    <MenuItem 
                      key={`label-${idx}`} 
                      disabled 
                      sx={{ opacity: 0.7, fontWeight: 'bold', fontSize: '0.85rem' }}
                    >
                      {m.label}
                    </MenuItem>
                  );
                }
                const isSupported = isModelSupported(m);
                return (
                  <MenuItem 
                    key={m} 
                    value={m}
                    sx={isSupported ? {
                      backgroundColor: alpha(theme.palette.success.main, 0.08),
                      fontWeight: 600,
                      '&:hover': {
                        backgroundColor: alpha(theme.palette.success.main, 0.15),
                      },
                      '&.Mui-selected': {
                        backgroundColor: alpha(theme.palette.success.main, 0.2),
                        '&:hover': {
                          backgroundColor: alpha(theme.palette.success.main, 0.25),
                        },
                      },
                    } : {}}
                  >
                    {isSupported && (
                      <Box component="span" sx={{ 
                        color: theme.palette.success.main, 
                        mr: 1, 
                        fontSize: '0.75rem',
                        fontWeight: 700,
                      }}>★</Box>
                    )}
                    {m}
                  </MenuItem>
                );
              })}
            </Select>
          </FormControl>
          
          {/* API Key Section */}
          {apiKeysLoaded && apiKeysStatus[provider] ? (
            <Paper
              variant="outlined"
              sx={{
                p: 1.5,
                mb: 2,
                backgroundColor: alpha('#4caf50', 0.05),
                border: '1px solid rgba(76, 175, 80, 0.3)'
              }}
            >
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography variant="body2" sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box sx={{ color: '#4caf50' }}>✓</Box>
                  Using API key from server
                </Typography>
                <FormControlLabel
                  control={
                    <Checkbox
                      size="small"
                      checked={apiKey !== 'env'}
                      onChange={(e) => setApiKey(e.target.checked ? '' : 'env')}
                      sx={{ p: 0.5 }}
                    />
                  }
                  label={<Typography variant="caption">Use custom</Typography>}
                  sx={{ m: 0 }}
                />
              </Box>
              {apiKey !== 'env' && (
                <TextField
                  fullWidth
                  size="small"
                  type="password"
                  value={apiKey}
                  onChange={(e) => setApiKey(e.target.value)}
                  placeholder="Enter your API key"
                  sx={{ mt: 1.5 }}
                  InputProps={{
                    startAdornment: <InputAdornment position="start"><KeyIcon fontSize="small" /></InputAdornment>,
                  }}
                />
              )}
            </Paper>
          ) : (
            <TextField
              fullWidth
              size="small"
              label="API Key"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              sx={{ mb: 2 }}
              InputProps={{
                startAdornment: <InputAdornment position="start"><KeyIcon fontSize="small" /></InputAdornment>,
              }}
            />
          )}
          
          <TextField
            fullWidth
            size="small"
            label="Top K Results"
            type="number"
            value={topK}
            onChange={(e) => setTopK(Math.max(1, Math.min(100, parseInt(e.target.value) || 10)))}
            inputProps={{ min: 1, max: 100 }}
            helperText="Number of results to return (1-100)"
            sx={{ mb: 2 }}
          />
          
          {/* Debug Mode */}
          <Box
            onClick={() => setVerbose(!verbose)}
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              p: 1.5,
              borderRadius: '8px',
              border: `1px solid ${theme.palette.divider}`,
              cursor: 'pointer',
              backgroundColor: verbose ? alpha(theme.palette.info.main, 0.08) : 'transparent',
              '&:hover': { backgroundColor: alpha(theme.palette.info.main, 0.05) },
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <InfoOutlinedIcon fontSize="small" sx={{ color: verbose ? 'info.main' : 'text.secondary' }} />
              <Typography variant="body2" sx={{ fontWeight: 500 }}>Debug Mode</Typography>
            </Box>
            <Switch
              checked={verbose}
              onChange={(e) => { e.stopPropagation(); setVerbose(e.target.checked); }}
              color="info"
              size="small"
            />
          </Box>
        </Box>
      </Collapse>
    </Paper>
  );
}

export default ModelSettings;
