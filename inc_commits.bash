#!/bin/bash
for i in {1..5}
do
   echo $(($RANDOM%(100000-1)+1)) > README.md && git add -A && git commit -m "new" && git push
done
