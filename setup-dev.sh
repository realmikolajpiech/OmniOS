#!/bin/bash
echo "Setup OmniOS dev environment..."

# Virtual env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# COSMIC config (wyłączenie ramki aktywnego okna)
mkdir -p ~/.config/cosmic/com.system76.CosmicComp
cp config/cosmic/com.system76.CosmicComp/config.ron ~/.config/cosmic/com.system76.CosmicComp/

echo "Gotowe! Uruchom: source .venv/bin/activate && python src/main.py"
