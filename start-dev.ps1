#!/usr/bin/env pwsh
# Quick start script for development with Tailwind CSS

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "POS Cafe - Development Setup" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Node.js is installed
try {
    $nodeVersion = node --version
    $npmVersion = npm --version
    Write-Host "✅ Node.js found" -ForegroundColor Green
    Write-Host "Node: $nodeVersion"
    Write-Host "NPM: $npmVersion"
} catch {
    Write-Host "❌ Node.js is not installed!" -ForegroundColor Red
    Write-Host "Please install Node.js from https://nodejs.org/" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""

# Check if node_modules exists
if (-not (Test-Path "node_modules")) {
    Write-Host "Installing dependencies..." -ForegroundColor Yellow
    npm install
    Write-Host ""
}

# Start the Tailwind watch process
Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Starting Tailwind CSS watch mode..." -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Watching for changes in templates/" -ForegroundColor Green
Write-Host "CSS will rebuild to static/output.css" -ForegroundColor Green
Write-Host ""
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

npm run watch
