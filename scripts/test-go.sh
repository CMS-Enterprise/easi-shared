#!/bin/bash

if [ -d "./go" ]; then
  # Check if there are any .go files to test
  if [ -n "$(find ./go -name "*.go" -type f)" ]; then
    go test ./go/...
  else
    echo "No GO packages found to test - skipping"
    exit 0
  fi
fi
