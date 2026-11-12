# Built on the clusters' distribution family so bound host Slurm binaries
# find a compatible glibc (see "Deployment" in the README).
FROM rockylinux:9

ENV PYTHONUNBUFFERED=1

RUN dnf install -y python3 && dnf clean all

COPY . /opt/screendoor-src
RUN python3 -m pip install --no-cache-dir /opt/screendoor-src \
    && mkdir -p /opt/screendoor \
    && cp /opt/screendoor-src/scripts/slurm-binds.sh /opt/screendoor/ \
    && rm -rf /opt/screendoor-src

ENTRYPOINT ["python3", "-m", "screendoor"]
