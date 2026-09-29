{
  description = "make-audiobook: locked Python environment (uv2nix) plus ffmpeg";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, uv2nix, pyproject-nix, pyproject-build-systems, ... }:
    let
      inherit (nixpkgs) lib;
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAll = f: lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});

      # The uv.lock is the single source of truth for Python dependencies.
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
      lockOverlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };

      pythonSetFor = pkgs:
        (pkgs.callPackage pyproject-nix.build.packages { python = pkgs.python3; }).overrideScope
          (lib.composeManyExtensions [ pyproject-build-systems.overlays.default lockOverlay ]);

      commands = [ "stats" "synth" "build" "serve" "clean" "cache" ];
    in {
      packages = forAll (pkgs:
        let
          pythonSet = pythonSetFor pkgs;
          venv = pythonSet.mkVirtualEnv "make-audiobook-env" workspace.deps.default;
          # Wrap each console script so ffmpeg is on PATH when it runs.
          wrap = cmd: pkgs.writeShellApplication {
            name = "audiobook-${cmd}";
            runtimeInputs = [ pkgs.ffmpeg ];
            text = ''exec "${venv}/bin/audiobook-${cmd}" "$@"'';
          };
          wrapped = lib.genAttrs commands wrap;
        in wrapped // {
          default = pkgs.symlinkJoin {
            name = "make-audiobook";
            paths = lib.attrValues wrapped;
          };
        });

      apps = forAll (pkgs:
        lib.genAttrs commands (cmd: {
          type = "app";
          program = "${self.packages.${pkgs.stdenv.hostPlatform.system}.${cmd}}/bin/audiobook-${cmd}";
        }));

      devShells = forAll (pkgs:
        let
          python = pkgs.python3;
          # Editable install of this package so edits under src/ are live in the
          # shell. The root is resolved at shell entry (see shellHook).
          editableOverlay = workspace.mkEditablePyprojectOverlay { root = "$REPO_ROOT"; };
          devSet = (pythonSetFor pkgs).overrideScope (lib.composeManyExtensions [
            editableOverlay
            (final: prev: {
              make-audiobook = prev.make-audiobook.overrideAttrs (old: {
                nativeBuildInputs = old.nativeBuildInputs
                  ++ final.resolveBuildSystem { editables = [ ]; };
              });
            })
          ]);
          venv = devSet.mkVirtualEnv "make-audiobook-dev-env" workspace.deps.all;
        in {
          default = pkgs.mkShell {
            packages = [ venv pkgs.ffmpeg pkgs.uv ];
            env = {
              UV_NO_SYNC = "1";                 # the venv comes from Nix, not from uv
              UV_PYTHON = python.interpreter;
              UV_PYTHON_DOWNLOADS = "never";
            };
            shellHook = ''
              unset PYTHONPATH
              # Editable root: the skill checkout when the shell is entered from
              # inside it (or REPO_ROOT is preset), else the flake's own source.
              if [ -z "''${REPO_ROOT:-}" ] || [ ! -f "$REPO_ROOT/pyproject.toml" ]; then
                if [ -f "$PWD/pyproject.toml" ] && grep -q '^name = "make-audiobook"' "$PWD/pyproject.toml"; then
                  export REPO_ROOT="$PWD"
                else
                  export REPO_ROOT="${self}"
                fi
              fi
            '';
          };
        });
    };
}
