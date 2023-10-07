#!/usr/bin/env bash

# python version must match lowest supported (3.8)
major=3
minor=8
if ! python -c "import sys; assert sys.version_info.major == $major and sys.version_info.minor == $minor"; then
  echo "python version not equal to expected $major.$minor: $(python --version)"
  exit 1
fi

pushd ./requirements
make ./*.txt
popd

cp requirements/build.txt docs/requirements.txt
