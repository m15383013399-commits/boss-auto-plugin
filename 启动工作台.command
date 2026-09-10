#!/bin/zsh
cd -- "${0:A:h}"
if [[ -x /opt/homebrew/bin/python3 ]]; then
  exec /opt/homebrew/bin/python3 run.py
else
  exec python3 run.py
fi
