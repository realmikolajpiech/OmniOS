{
  description = "AI-Native OS Distro";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    nixos-generators = {
      url = "github:nix-community/nixos-generators";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, nixos-generators, ... }: {
    packages.x86_64-linux = {
      # To polecenie zbuduje Twoje ISO
      install-iso = nixos-generators.nixosGenerate {
        system = "x86_64-linux";
        format = "install-iso"; # Format wyjściowy: bootowalne ISO
        modules = [
          ./configuration.nix # Twój konfig systemu
        ];
      };
    };
  };
}
