import React from 'react';
import { Typography } from '@mui/material';
import { DataGrid } from '@mui/x-data-grid';

function LatestQueries({ queries, onSelectQuery }) {
  const columns = [
    { field: 'question', headerName: 'Question', flex: 2 },
    { field: 'query', headerName: 'Query', flex: 2 },
    { field: 'type', headerName: 'Type', flex: 1 },
    { field: 'llmType', headerName: 'LLM', flex: 1 },
    { 
      field: 'naturalAnswer', 
      headerName: 'Answer', 
      flex: 2,
      renderCell: (params) => (
        <div style={{ whiteSpace: 'normal', wordWrap: 'break-word' }}>
          {params.value}
        </div>
      )
    } // updated "Answer" column
  ];

  const rows = queries.slice().reverse().map((item, index) => ({
    id: index,
    question: item.question,
    query: item.query,
    type: item.type,
    llmType: item.llmType,
    naturalAnswer: item.naturalAnswer // Include natural language answer
  }));

  const handleRowClick = (params) => {
    onSelectQuery(params.row);
  };

  return (
    <div style={{ height: 300, width: '100%', marginTop: 16 }}>
      <Typography variant="h6" gutterBottom>
        Latest Queries
      </Typography>
      <DataGrid
        rows={rows}
        columns={columns}
        pageSize={5}
        onRowClick={handleRowClick}
        rowsPerPageOptions={[5]}
        disableSelectionOnClick
        getRowHeight={() => 'auto'}
        sx={{ '& .MuiDataGrid-cell': { borderRight: '1px solid rgba(0, 0, 0, 0.12)' } }}
      />
    </div>
  );
}

export default LatestQueries;