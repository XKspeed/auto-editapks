#!/bin/bash
cd ~/apk
git add .
echo -n "输入 commit 信息: "
read msg
git commit -m "$msg"
git push
