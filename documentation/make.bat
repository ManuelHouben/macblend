@ECHO OFF

pushd %~dp0

if "%SPHINXBUILD%" == "" (
    set SPHINXBUILD=sphinx-build
)
set SOURCEDIR=pages
set BUILDDIR=build
set CONFDIR=config

%SPHINXBUILD% >NUL 2>NUL
if errorlevel 9009 (
    echo.
    echo.The 'sphinx-build' command was not found. Install documentation/requirements.txt.
    exit /b 1
)

if "%1" == "" goto help
%SPHINXBUILD% -M %1 %SOURCEDIR% %BUILDDIR% -c %CONFDIR% %SPHINXOPTS% %O%
goto end

:help
%SPHINXBUILD% -M help %SOURCEDIR% %BUILDDIR% -c %CONFDIR% %SPHINXOPTS% %O%

:end
popd
