#!/usr/bin/env node

// Script to set PUBLIC_URL from REACT_APP_CROSSBAR_LLM_ROOT_PATH before building
const { execSync } = require('child_process');

// Get the root path from environment variable or use default
const rootPath = process.env.REACT_APP_CROSSBAR_LLM_ROOT_PATH || '';
const baseUrl = `https://crossbarv2.hubiodatalab.com${rootPath}`;

// Set PUBLIC_URL environment variable
process.env.PUBLIC_URL = baseUrl;

console.log(`Building with PUBLIC_URL: ${process.env.PUBLIC_URL}`);

// Run the build command
try {
  execSync('react-scripts build', { stdio: 'inherit' });
} catch (error) {
  console.error('Build failed:', error);
  process.exit(1);
} 