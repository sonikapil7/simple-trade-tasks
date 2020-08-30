#!/bin/bash
source ../.venv/bin/activate
source ../auth_data/export_zerodha_credentials.sh

python sentinal.py
