#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Kill any stale Next.js dev servers on common ports
for port in 3000 3001 3002; do
  lsof -ti:"$port" | xargs kill -9 2>/dev/null || true
done

# Clear corrupted webpack / Next caches (fixes missing chunk 404s)
rm -rf .next node_modules/.cache

echo "Starting Timelly Studio frontend on http://localhost:3000"
exec npx next dev -p 3000
