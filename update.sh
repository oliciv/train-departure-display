#!/bin/bash

OLD_HEAD=$(git rev-parse HEAD)
git pull
NEW_HEAD=$(git rev-parse HEAD)
[ $OLD_HEAD = $NEW_HEAD ] && exit 0 # no change to repo = no change to any files


echo "Changed"

sudo service departure restart

