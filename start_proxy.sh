#!/bin/bash
export GEMINI_API_KEY=$(grep 'GOOGLE_API_KEY=' ~/.hermes2/profiles/main/.env | cut -d= -f2 | tr -d '"'\'' )
/usr/bin/python3 ./proxy/main.py > ~/.hermes2/profiles/main/cache/scratch/proxy.log 2>&1
