#!/bin/bash

# cd to script directory
# adapted from https://stackoverflow.com/a/6393573
cd "${0%/*}"

echo "generating requirements-all.txt"
python3 -m uv pip compile --python-version=3.11 ../../pyproject.toml --extra docs --extra release --extra testing -o requirements-all.txt --upgrade

echo "generating requirements-docs.txt"
python3 -m uv pip compile --python-version=3.11 ../../pyproject.toml --extra docs -o requirements-docs.txt --upgrade

echo "generating requirements-release.txt"
python3 -m uv pip compile --python-version=3.11 ../../pyproject.toml --extra release -o requirements-release.txt --upgrade

echo "generating requirements-testing.txt"
python3 -m uv pip compile --python-version=3.11 ../../pyproject.toml --extra testing -o requirements-testing.txt --upgrade
