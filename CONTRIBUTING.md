# Contributing to MacBlend

## Report an issue

Search existing issues before opening a report. Bug reports should include:

- Blender, MacBlend, and operating-system versions
- Exact reproduction steps
- Source and target image color-space settings
- Relevant console output
- Screenshots or small sample files when their licenses permit redistribution

## Development setup

MacBlend requires Blender 4.2 or newer. The repository is configured for the VS Code extension `JacquesLucke.blender-development`.

1. Clone the repository and open its root folder in VS Code.
2. Install the workspace-recommended extensions.
3. Create and activate a Python virtual environment.
4. Install the host-side dependencies:

   ```console
   python -m pip install numpy
   python -m pip install -r documentation/requirements.txt
   ```

5. Run **Blender: Start** and select a Blender executable.
6. Use **Blender: Reload Addons** after changing extension code.

The workspace sets `BLENDER_USER_RESOURCES` to `blender_vscode_development/`. The Blender Development extension creates this isolated profile, its extension junction, and debugger dependencies automatically. It is local generated state and must not be committed.

## Tests

Run host-side unit tests from the repository root:

```console
python -m unittest discover -s tests -p "test_*.py"
```

Run the integration smoke test with Blender:

```console
blender --background --factory-startup --python tests/blender_smoke.py
```

Use the full path to the Blender executable when `blender` is not available on `PATH`.

## Extension package

The distributable extension lives entirely in `source/`. Validate and build it from that directory:

```console
cd source
blender --command extension validate
blender --command extension build --output-dir ../dist
```

Validate the resulting ZIP before installing it from disk:

```console
blender --command extension validate ../dist/macblend-*.zip
```

Generated ZIP files and `dist/` are not committed.

## Documentation

Install the documentation dependencies and build the site with warnings treated as errors:

```console
python -m pip install -r documentation/requirements.txt
sphinx-build -W --keep-going -c documentation/config -b html documentation/pages documentation/build/html
```

On Windows, `documentation\make.bat html` provides a shorter local command. On Linux and macOS, use `make -C documentation html`.

Documentation changes are built for every pull request. Pushes to `main` deploy the site to GitHub Pages.

## Pull requests

Keep changes focused, update tests and documentation for changed behavior, and verify the relevant commands above. Do not commit local Blender profiles, virtual environments, generated documentation, or extension archives.
