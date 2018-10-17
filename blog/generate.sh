#!/bin/bash
#git checkout master
git --work-tree=_site add --all
git --work-tree=_site commit -m 'autogen: update'
git --work-tree=_site push
