
# OmniOS

AI-native desktop OS based on Pop!_OS 24.04 with COSMIC desktop.

## Dev setup

```bash


git clone https://github.com/realmikolajpiech/OmniOS.git

cd OmniOS

./setup-dev.sh

omni
```

**Note:** The setup script will sync your COSMIC shortcuts. The `Super` key is bound to start Omni.
**More Important Note:** Setting the above-mentioned shortcut via script DOESN'T WORK currently. You need to set it manually in the settings (remove `Super` shortcut from the Launcher and add custom shortcut for command `omni`).

```