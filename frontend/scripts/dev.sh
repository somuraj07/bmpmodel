#!/usr/bin/env bash
set -euo pipefail

# Kill any stale Next.js dev servers on common ports
for port in 3000 3001 3002; do
  lsof -ti:"$port" | xargs kill -9 2>/dev/null || true
done

# Remove corrupted webpack chunks (fixes missing ./833.js)
rm -rf .next node_modules/.cache

echo "Starting BMP Mode frontend on http://localhost:3000"
exec npx next dev -p 3000
