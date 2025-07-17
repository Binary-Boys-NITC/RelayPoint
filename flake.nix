{
  description = "RelayPoint Flake";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python3
            python3Packages.pip
            postgresql
          ];
          
          shellHook = ''
            echo "Setting up Python virtual environment..."
            
            # Create venv if it doesn't exist
            if [ ! -d ".venv" ]; then
              python -m venv .venv
            fi
            
            # Activate virtual environment
            source .venv/bin/activate
            
            # Install requirements if requirements.txt exists
            if [ -f "requirements.txt" ]; then
              pip install -r requirements.txt
            fi
            
            echo "Python development environment ready!"
          '';
        };
      });
}