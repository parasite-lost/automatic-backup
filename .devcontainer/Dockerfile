FROM fedora:44

ARG USERNAME=dev
ARG USER_UID=1000
ARG USER_GID=1000

RUN groupadd --gid $USER_GID $USERNAME && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME

RUN dnf install -y \
    black \
    git \
    make \
    pylint \
    python3 \
    python3-flake8 \
    python3-varlink \
    rpm-build \
    rpmlint \
    systemd

WORKDIR /app

USER $USERNAME
