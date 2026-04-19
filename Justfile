set dotenv-load

version := `uv version --short`
image_name := "factorio-downloader:"+version
packages := `uv export --no-dev --format requirements.txt --no-hashes --no-annotate --no-header | tr '\n' ' '`

v:
    @echo {{version}}

i:
    @echo {{image_name}}

download:
    uv run fdl --version latest --outdir downloads

build:
    docker build -t {{image_name}} .

run_docker:
    docker run \
        -v $(realpath fdl/):/downloaded \
        -e FACTORIO_USERNAME=$FACTORIO_USERNAME \
        -e FACTORIO_TOKEN=$FACTORIO_TOKEN \
        -e FDL_CRON_SCHEDULE="*/5 * * * *" \
        {{image_name}}

export_image:
    mkdir -p build/
    docker save -o build/{{image_name}}.tar.gz {{image_name}}

shiv:
    uv run shiv --entry-point factorio_downloader.__main__:main_sync --output-file fdl.pyz {{packages}}
