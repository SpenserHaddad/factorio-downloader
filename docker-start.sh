#!/bin/sh

if [ -z "${FDL_CRON_SCHEDULE}" ]; then
  CRON_SCHEDULE="0 18 * * 1"
else
  CRON_SCHEDULE="${FDL_CRON_SCHEDULE}"
fi

echo "${CRON_SCHEDULE} uv run --directory /factorio-downloader python -m factorio_downloader --version=latest --build=expansion --outdir /downloaded --quiet --logfile /downloaded/factorio-dl.log" >> /etc/cron.d/factorio-dl 
chmod 0644 /etc/cron.d/factorio-dl && crontab /etc/cron.d/factorio-dl
mkdir -p /downloaded

crond -f
