{ config, pkgs, lib, ... }:

{
  # Baza graficzna
  services.xserver.enable = true; 

  # Display Manager (Logowanie)
  services.displayManager.sddm = {
    enable = true;
    wayland.enable = true;
  };

  # Auto-login graficzny
  services.displayManager.autoLogin = {
    enable = true;
    user = "omnios";
  };

  # Włączenie Hyprland
  programs.hyprland.enable = true;

  # --- KONFIGURACJA HYPRLAND ---
  # Tworzymy systemowy plik konfiguracyjny w /etc/hypr/hyprland.conf
  environment.etc."hypr/hyprland.conf".text = ''
    # 1. Ustawienia monitora (ważne dla QEMU)
    monitor=,preferred,auto,1

    # 2. Autostart tapety
    exec-once = ${pkgs.hyprpaper}/bin/hyprpaper

    # 3. Wygląd (Styl OmniOS)
    general {
        gaps_in = 5
        gaps_out = 10
        border_size = 2
        col.active_border = rgba(33ccffee) rgba(00ff99ee) 45deg
        col.inactive_border = rgba(595959aa)
        layout = dwindle
    }

    decoration {
        rounding = 10
        blur {
            enabled = true
            size = 3
            passes = 1
        }
    }

    # 4. SKRÓTY KLAWISZOWE (Kluczowe!)
    $mainMod = SUPER
    
    bind = $mainMod, Q, exec, kitty
    bind = $mainMod, M, exit, 
  '';
  
  # Zmienne środowiskowe dla Waylanda
  environment.sessionVariables = {
    NIXOS_OZONE_WL = "1"; 
    WLR_NO_HARDWARE_CURSORS = "1"; 
    WLR_RENDERER_ALLOW_SOFTWARE = "1";
  };

  # Konfiguracja hyprpaper (wskazuje na tapetę z theme.nix)
  environment.etc."hypr/hyprpaper.conf".text = ''
    preload = /etc/backgrounds/omnios-bg.png
    wallpaper = ,/etc/backgrounds/omnios-bg.png
  '';
}