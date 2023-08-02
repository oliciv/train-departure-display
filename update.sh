#!/bin/bash

CURRENT_BRANCH=$(git branch --show-current)
OLD_HEAD=$(git rev-parse HEAD)
git fetch --all
git reset --hard origin/$CURRENT_BRANCH
NEW_HEAD=$(git rev-parse HEAD)
[ $OLD_HEAD = $NEW_HEAD ] && exit 0 # no change to repo = no change to any files


echo "Changed"

sudo service departure restart

