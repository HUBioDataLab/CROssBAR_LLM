import React from 'react';
import {
  Box,
  Typography,
  IconButton,
  Tooltip,
  Chip,
  alpha,
  useTheme,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';

/**
 * Chat header component with title, message count, and controls.
 */
function ChatHeader({
  messageCount,
  rightPanelOpen,
  onToggleRightPanel,
  onNewConversation,
}) {
  const theme = useTheme();

  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        px: 3,
        py: 2,
        borderBottom: `1px solid ${theme.palette.divider}`,
        backgroundColor: alpha(theme.palette.background.paper, 0.8),
        backdropFilter: 'blur(10px)',
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
        <Typography variant="h6" sx={{ fontWeight: 600 }}>
          CROssBAR Chat
        </Typography>
        {messageCount > 0 && (
          <Chip
            label={`${messageCount} message${messageCount !== 1 ? 's' : ''}`}
            size="small"
            sx={{ fontSize: '0.75rem' }}
          />
        )}
      </Box>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        {messageCount > 0 && (
          <Tooltip title="New conversation">
            <IconButton onClick={onNewConversation} size="small">
              <AddIcon />
            </IconButton>
          </Tooltip>
        )}
        <Tooltip title={rightPanelOpen ? "Hide panel" : "Show panel"}>
          <IconButton onClick={onToggleRightPanel} size="small">
            {rightPanelOpen ? <ChevronRightIcon /> : <ChevronLeftIcon />}
          </IconButton>
        </Tooltip>
      </Box>
    </Box>
  );
}

export default ChatHeader;
