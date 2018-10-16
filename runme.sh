#!/bin/bash

# step 1
git branch -D master
git checkout -b master master-empty
git push --set-upstream origin master -f
git checkout sources

# step 2
cd blog
bundle exec jekyll serve
cd ..
git checkout master

# step 3
cd blog
git --work-tree=_site add --all
git --work-tree=_site commit -m 'autogen: update'
git --work-tree=_site push -f
git checkout sources

