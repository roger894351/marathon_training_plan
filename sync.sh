#!/bin/bash
cd "$(dirname "$0")"
python3 -m watch_sync sync && python3 -m watch_sync dashboard --open
