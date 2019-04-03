#!/bin/bash

bundle exec jekyll clean
bundle exec jekyll build
echo ".sass-cache" > _site/.gitignore
echo ".jekyll-metadata" >> _site/.gitignore
echo ".DS_Store" >> _site/.gitignore

