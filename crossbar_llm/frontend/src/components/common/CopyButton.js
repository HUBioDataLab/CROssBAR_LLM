import React from 'react';
import {
  IconButton,
  Tooltip,
} from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';

/**
 * Reusable copy to clipboard button.
 */
function CopyButton({
  text,
  onCopy,
  isCopied,
  size = 'small',
  tooltipPlacement = 'top',
  sx = {},
}) {
  const handleClick = async (e) => {
    e?.stopPropagation?.();
    if (onCopy) {
      onCopy(text);
    } else {
      try {
        await navigator.clipboard.writeText(text);
      } catch (err) {
        console.error('Failed to copy:', err);
      }
    }
  };

  return (
    <Tooltip title={isCopied ? "Copied!" : "Copy"} placement={tooltipPlacement}>
      <IconButton 
        size={size} 
        onClick={handleClick}
        sx={{ opacity: 0.6, ...sx }}
      >
        <ContentCopyIcon sx={{ fontSize: size === 'small' ? 14 : 18 }} />
      </IconButton>
    </Tooltip>
  );
}

export default CopyButton;
