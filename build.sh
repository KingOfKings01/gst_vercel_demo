#!/usr/bin/env bash
set -o errexit

pip install -r requirements.txt

# Install Chromium AND its system dependencies (critical for Linux servers)
playwright install --with-deps chromium
