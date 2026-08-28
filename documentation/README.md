# MacBlend documentation

The user manual is written in Markdown and reStructuredText and built with Sphinx, MyST Parser, and the Furo theme.

## Build locally

Install the dependencies from the repository root:

```console
python -m pip install -r documentation/requirements.txt
```

Build on Windows:

```console
documentation\make.bat html
```

Build on Linux or macOS:

```console
make -C documentation html
```

For the same strict check used in GitHub Actions:

```console
sphinx-build -W --keep-going -c documentation/config -b html documentation/pages documentation/build/html
```

Open `documentation/build/html/index.html` to preview the generated site. Build output is ignored by Git.
