#!/bin/bash
set -e

# WeasyPrint system dependencies
apt-get update && apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf2.0-0 libffi-dev libcairo2

# Python dependencies and database migration (running inside backend Root Directory)
pip install -r requirements.txt
alembic upgrade head

# Chromium runtime for JavaScript-rendered pricing pages
export PLAYWRIGHT_BROWSERS_PATH=/opt/render/project/src/.playwright
playwright install-deps chromium
playwright install chromium
