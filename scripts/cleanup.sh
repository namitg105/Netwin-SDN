#!/bin/bash
# Remove leftover virtual switches and links after a crashed or interrupted run.
set -euo pipefail
sudo mn -c
