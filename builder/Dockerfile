FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive PIP_BREAK_SYSTEM_PACKAGES=1
RUN apt-get update && apt-get install -y --no-install-recommends \
 autoconf automake autopoint bash bison build-essential ca-certificates ccache curl \
 clang flex g++ g++-multilib gettext git gperf intltool jq libasound2-dev libavcodec-dev libavfilter-dev \
 libboost-context-dev libboost-dev libboost-fiber-dev libdrm-dev libegl1-mesa-dev \
 libglu1-mesa-dev libgdk-pixbuf-2.0-dev libc6-dev-i386 libclang-dev llvm-dev libltdl-dev libopus-dev libpulse-dev libssl-dev libtool libtool-bin \
 libudev-dev libusb-1.0-0-dev libva-dev libvdpau-dev libvulkan-dev libx11-dev \
 libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 libxkbcommon-x11-0 \
 libxml-parser-perl lzip make mesa-common-dev nasm ninja-build p7zip-full patch \
 perl pkg-config python-is-python3 python3 python3-mako python3-yaml python3-packaging python3-setuptools python3-pip python3-venv ruby scons sed spirv-headers \
 spirv-tools texinfo unzip wget xz-utils zip zlib1g-dev zsync glslang-tools \
 && pip install --no-cache-dir 'cmake==3.31.6' 'aqtinstall==3.3.0' \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /work
