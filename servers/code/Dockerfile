FROM python:3.13-slim@sha256:bffeb7bd6a85767587059c6ba23e1e9122078e3aa3fa836099171b9bb5a9bb00

COPY servers/code/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY servers/shared/ /shared/

# Source is NOT baked in — read live from /youk volume mount.
# Code changes take effect on next Claude Code restart without rebuild.
# Only rebuild when requirements.txt or servers/shared/ changes.
WORKDIR /youk/servers/code/src

CMD ["python", "server.py"]
