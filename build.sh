#!/bin/bash

# Upgrade core Python build tools
pip install --upgrade pip setuptools wheel

# Install dependencies from requirements.txt
pip install -r requirements.txt
