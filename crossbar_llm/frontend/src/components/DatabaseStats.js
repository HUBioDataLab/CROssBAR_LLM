import React, { useEffect, useState } from 'react';
import axios from '../services/api';
import {
  Typography,
  CircularProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';

import {
  Chart as ChartJS,
  ArcElement,
  CategoryScale,
  LinearScale,
  BarElement,
  Tooltip,
  Legend,
} from 'chart.js';

import { Pie, Bar } from 'react-chartjs-2';

ChartJS.register(ArcElement, CategoryScale, LinearScale, BarElement, Tooltip, Legend);

function DatabaseStats() {
  const [stats, setStats] = useState(() => {
    const savedStats = sessionStorage.getItem('databaseStats');
    return savedStats ? JSON.parse(savedStats) : null;
  });

  useEffect(() => {
    // If CSRF token is not set in cookies, wait for it to be set (a little wait) and then fetch the data
    const waitForCsrfToken = async () => {
      while (!axios.defaults.headers['X-CSRF-Token']) {
        console.log('Waiting for CSRF token to be set in cookies...');
      await new Promise((resolve) => setTimeout(resolve, 100));
      }
    };

    waitForCsrfToken().then(() => {
      axios
      .get('/database_stats/')
      .then((response) => {
        setStats(response.data);
        sessionStorage.setItem('databaseStats', JSON.stringify(response.data));
      })
      .catch((error) => {
        console.error('Error fetching database statistics:', error);
      });
    });
  }, []);

  if (!stats) {
    return (
      <Typography align="center" sx={{ mt: 4 }}>
        <CircularProgress />
      </Typography>
    );
  }

  const { top_5_labels, node_counts, relationship_counts } = stats;

  const nodeLabelsChart = {
    labels: Object.keys(top_5_labels),
    datasets: [
      {
        label: 'Node Counts',
        data: Object.values(top_5_labels),
        backgroundColor: ['#FF6384', '#36A2EB', '#FFCE56', '#81C784', '#BA68C8'],
      },
    ],
  };

  const relationshipChart = {
    labels: Object.keys(relationship_counts),
    datasets: [
      {
        label: 'Relationship Counts',
        data: Object.values(relationship_counts),
        backgroundColor: ['#7986CB', '#E57373', '#4DB6AC', '#F06292', '#4FC3F7'],
      },
    ],
  };


  return (
    <Accordion defaultExpanded={true} sx={{ mt: 2 }}>
      <AccordionSummary expandIcon={<ExpandMoreIcon />}>
        <Typography variant="h6">Database Statistics</Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Typography variant="subtitle1">Top 5 Node Labels</Typography>
        <Pie data={nodeLabelsChart} />

        <Typography variant="subtitle1" sx={{ mt: 4 }}>
          Top 5 Relationship Types
        </Typography>
        <Bar data={relationshipChart} options={{ indexAxis: 'y' }} />
      </AccordionDetails>
    </Accordion>
  );
}

export default DatabaseStats;