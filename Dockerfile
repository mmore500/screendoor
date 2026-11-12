# Built on the clusters' distribution family so bound host Slurm binaries
# find a compatible glibc (see "Installation" in the README).
FROM rockylinux:9

ENV PYTHONUNBUFFERED=1

# Rocky 9's own python3 is 3.9, older than screendoor supports: python3 on
# PATH is 3.12, while dnf keeps /usr/bin/python3
RUN dnf install -y python3.12 python3.12-pip && dnf clean all \
    && ln -s /usr/bin/python3.12 /usr/local/bin/python3

COPY . /opt/screendoor-src
RUN python3 -m pip install --no-cache-dir /opt/screendoor-src \
    && mkdir -p /opt/screendoor \
    && cp /opt/screendoor-src/scripts/slurm-binds.sh /opt/screendoor/ \
    && rm -rf /opt/screendoor-src

ENTRYPOINT ["python3", "-m", "screendoor"]
