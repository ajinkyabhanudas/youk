FROM python:3.13-slim

COPY servers/code/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY servers/shared/ /shared/

# Source is NOT baked in — read live from /youk volume mount.
# Code changes take effect on next Claude Code restart without rebuild.
# Only rebuild when requirements.txt or servers/shared/ changes.
WORKDIR /youk/servers/code/src

CMD ["python", "server.py"]
