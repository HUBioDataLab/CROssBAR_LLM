import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import RemoveCircleOutlineIcon from '@mui/icons-material/RemoveCircleOutline';
import HourglassEmptyIcon from '@mui/icons-material/HourglassEmpty';
import RateReviewIcon from '@mui/icons-material/RateReview';

/** Label, icon and palette key for each agent status, shared by progress and trace. */
export const STATUS_META = {
  pending: { label: 'Waiting', Icon: HourglassEmptyIcon, palette: 'text' },
  queued: { label: 'Queued', Icon: HourglassEmptyIcon, palette: 'text' },
  running: { label: 'Working', Icon: null, palette: 'info' },
  completed: { label: 'Answered', Icon: CheckCircleIcon, palette: 'success' },
  failed: { label: 'Failed', Icon: ErrorOutlineIcon, palette: 'warning' },
  skipped: { label: 'Skipped', Icon: RemoveCircleOutlineIcon, palette: 'text' },
  awaiting_review: { label: 'Needs review', Icon: RateReviewIcon, palette: 'info' },
};

export const statusMeta = (status) => STATUS_META[status] || STATUS_META.pending;

/** The theme colour for a status; neutral statuses use secondary text. */
export const statusColor = (theme, status) => {
  const { palette } = statusMeta(status);
  return palette === 'text' ? theme.palette.text.secondary : theme.palette[palette].main;
};

export const formatSeconds = (seconds) => {
  if (seconds === null || seconds === undefined) return '';
  if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
};
