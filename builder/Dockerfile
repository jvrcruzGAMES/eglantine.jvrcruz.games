FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive PIP_BREAK_SYSTEM_PACKAGES=1
RUN apt-get update && apt-get install -y --no-install-recommends \
 autoconf automake autopoint bash bison build-essential ca-certificates ccache curl \
 g++ git jq libasound2-dev libavcodec-dev libavfilter-dev \
 libboost-context-dev libboost-dev libboost-fiber-dev libdrm-dev libegl1-mesa-dev \
 libglu1-mesa-dev libltdl-dev libopus-dev libpulse-dev libssl-dev libtool libtool-bin \
 libudev-dev libusb-1.0-0-dev libva-dev libvdpau-dev libvulkan-dev libx11-dev \
 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxkbcommon-x11-0 \
 make mesa-common-dev nasm ninja-build patch \
 perl pkg-config python3 python3-pip python3-venv sed spirv-headers \
 spirv-tools texinfo unzip wget xz-utils zlib1g-dev zsync glslang-tools \
 && pip install --no-cache-dir 'cmake==3.31.6' 'aqtinstall==3.3.0' \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /work
