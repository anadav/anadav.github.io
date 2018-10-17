#!/bin/bash

# step 1
git branch -D master
git checkout -b master master-empty
git push --set-upstream origin master -f
git checkout sources

# step 2
cd blog
bundle exec jekyll clean
bundle exec jekyll serve
cp -r ../download _site 
cd ..
git checkout master

# step 3
cd blog

echo ".sass-cache" > _site/.gitignore
echo ".jekyll-metadata" >> _site/.gitignore
echo ".DS_Store" >> _site/.gitignore

git --work-tree=_site add .gitignore
git --work-tree=_site add --all
git --work-tree=_site commit -m 'autogen: update'
git --work-tree=_site push -f
#sleep 3
git checkout sources
git reset --hard
