#!/usr/bin/env sh
cd "$(dirname "$0")"
export LULSRNG_API_BASE="https://render-47ff.onrender.com"
export LULSRNG_API_TOKEN="04ea193ec0537156f012b0f3a82f86a8"
python3 lulsrng1.1.py
