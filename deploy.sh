#!/bin/bash
set -e

# Deploy steps for the blurb double-render fix.
# Run as a user with write access to /srv/ (not opencode).

VHOSTDIR=${VHOSTDIR:-/srv/www/vhosts/zoidtechnologies.com}
HOST=${HOST:-merlin}

echo "1. Engine (router.php)..."
cd /home/opencode/data/work/bbsengine6 && make engine

echo "2. Bbsengine6 templates (blurb, page-markdown, page-markdown-sections)..."
cd /home/opencode/data/work/bbsengine6 && make skin-prod

echo "3. Shared templates (page.tmpl)..."
cd /home/opencode/data/work/zoid6 && make shared

echo "4. bbsengine6 PHP (blurb.php, engine.php) -> merlin..."
cd /home/opencode/data/work/bbsengine6 && make php-deploy-prod

echo "4b. bbsengine6 Smarty plugins (function.teos.php) -> merlin..."
mkdir -p /srv/www/bbsengine6/smarty/
rsync --chmod=Dg=rwxs,Fgu=rw,Fo=r --archive --times --no-group --update --backup --recursive --checksum --rsh=ssh --mkpath /home/opencode/data/work/bbsengine6/smarty/*.php ${HOST}:/srv/www/bbsengine6/smarty/

echo "5. zoid6 PHP (bootstrap.php) -> merlin..."
cd /home/opencode/data/work/zoid6 && make php-deploy
echo "5b. zoid6 Smarty plugins -> merlin..."
rsync --chmod=Dg=rwxs,Fgu=rw,Fo=r --archive --times --no-group --update --backup --recursive --checksum --rsh=ssh --mkpath /home/opencode/data/work/zoid6/smarty/*.php ${HOST}:/srv/www/zoid6/smarty/

echo "6. teos (PHP + skin + blurbs) -> merlin..."
cd /home/opencode/data/work/teos && make www

echo "7. Verify (reads dev tree, no /srv write needed)..."
cd /home/opencode/data/work/bbsengine6/php && php test_blurb_render.php

echo "8. article2 www -> merlin..."
cd /home/opencode/data/work/yummyjam/article2 && make deploy-www

echo "9. article2 tui (pip install -e . into active venv)..."
cd /home/opencode/data/work/yummyjam/article2 && make deploy-tui

echo "DONE. Check https://zoidtechnologies.com/teos/comp/lang/python/intro in browser."


