#!/bin/bash

# cd to script directory
# adapted from https://stackoverflow.com/a/6393573
cd "${0%/*}"

./py310/regenerate.sh &

./py311/regenerate.sh &

./py312/regenerate.sh &

./py313/regenerate.sh &

./py314/regenerate.sh &

# the top-level files pin for the oldest supported python
echo "generating requirements-docs.txt"
python3 -m uv pip compile --python-version=3.10 ../pyproject.toml --extra docs -o requirements-docs.txt --upgrade &

echo "generating requirements-release.txt"
python3 -m uv pip compile --python-version=3.10 ../pyproject.toml --extra release -o requirements-release.txt --upgrade &

echo "generating requirements-testing.txt"
python3 -m uv pip compile --python-version=3.10 ../pyproject.toml --extra testing -o requirements-testing.txt --upgrade &

wait
