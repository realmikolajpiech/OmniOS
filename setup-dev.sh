#!/bin/bash
set -e

echo "Setup OmniOS dev environment..."

# 1. System Dependencies (Pop!_OS / Ubuntu)
# 1. System Dependencies (Pop!_OS / Ubuntu)
echo "Installing system dependencies..."
sudo apt update
sudo apt install -y python3-venv python3-pip fd-find dex cmake \
    build-essential libcudart12 libcublas12 \
    libxcb-cursor0

# 2. Virtual Env & Python Deps
echo "Setting up Python environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate

echo "Installing generic requirements..."
# Install CPU-only torch to avoid CUDA version conflicts (Embeddings are fast on CPU)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

# 3. Llama.cpp with CUDA (Pre-built Wheel)
echo "Installing llama-cpp-python with CUDA support (Pre-built)..."
# Using CUDA 12.x compatible wheel
pip install llama-cpp-python \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu124

# 4. Model Download
MODEL_DIR="$HOME/.local/share/ai-models"
MODEL_NAME="gemma-3-1b-it-Q8_0.gguf"
MODEL_URL="https://huggingface.co/unsloth/gemma-3-1b-it-GGUF/resolve/main/gemma-3-1b-it-Q8_0.gguf"

mkdir -p "$MODEL_DIR"
if [ ! -f "$MODEL_DIR/$MODEL_NAME" ]; then
    echo "Downloading AI Model ($MODEL_NAME)... This may take a while."
    wget -O "$MODEL_DIR/$MODEL_NAME" "$MODEL_URL"
else
    echo "Model already exists at $MODEL_DIR/$MODEL_NAME"
fi


# 5. System Integration & Configuration
echo "Configuring System Integration..."

# CLI Alias
mkdir -p ~/.local/bin
ln -sf /home/miki/OmniOS/start.sh ~/.local/bin/omni
echo "Added 'omni' command to ~/.local/bin"

# Desktop Entry
cp /home/miki/OmniOS/omni.desktop ~/.local/share/applications/
chmod +x ~/.local/share/applications/omni.desktop
update-desktop-database ~/.local/share/applications/ || true

# COSMIC Keybindings & Config Sync
echo "Syncing COSMIC Configuration..."
COSMIC_CONFIG_DIR="$HOME/.config/cosmic/com.system76.CosmicComp/v1"
REPO_CONFIG_FILE="/home/miki/OmniOS/config/cosmic/com.system76.CosmicComp/v1/config.ron"

if [ -f "$REPO_CONFIG_FILE" ]; then
    mkdir -p "$COSMIC_CONFIG_DIR"
    
    # Check if it's already a symlink to our repo
    if [ -L "$COSMIC_CONFIG_DIR/config.ron" ]; then
        TARGET=$(readlink -f "$COSMIC_CONFIG_DIR/config.ron")
        if [ "$TARGET" == "$REPO_CONFIG_FILE" ]; then
            echo "COSMIC config is already linked correctly."
        else
            echo "Updating existing symlink..."
            ln -sf "$REPO_CONFIG_FILE" "$COSMIC_CONFIG_DIR/config.ron"
        fi
    else
        # It's a real file or doesn't exist. Backup if exists.
        if [ -f "$COSMIC_CONFIG_DIR/config.ron" ]; then
            echo "Backing up existing COSMIC config to config.ron.bak"
            mv "$COSMIC_CONFIG_DIR/config.ron" "$COSMIC_CONFIG_DIR/config.ron.bak"
        fi
        
        echo "Linking repository config to system config..."
        ln -sf "$REPO_CONFIG_FILE" "$COSMIC_CONFIG_DIR/config.ron"
    fi
else
    echo "Warning: Repository config file not found at $REPO_CONFIG_FILE"
fi

echo "--------------------------------------------------------"
echo "Setup Complete!"
echo "To start Omni, run: omni (or press Super key)"
echo "--------------------------------------------------------"
