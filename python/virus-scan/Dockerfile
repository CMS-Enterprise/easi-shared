# Simple Dockerfile using pre-built ClamAV packages
# Much faster and more reliable than building from source

FROM public.ecr.aws/lambda/python:3.14

# Install ClamAV and dependencies from Amazon Linux repos
RUN dnf install -y \
    clamav \
    clamav-update \
    zip \
    && dnf clean all

# Update virus definitions
RUN freshclam || echo "Freshclam completed with warnings"

# Create layer structure with all dependencies
WORKDIR /output
RUN mkdir -p bin lib share

# Copy binaries
RUN cp /usr/bin/clamscan /output/bin/ && \
    cp /usr/bin/freshclam /output/bin/

# Copy ClamAV libraries
RUN cp -r /usr/lib64/libclamav.so* /output/lib/ && \
    cp -r /usr/lib64/libfreshclam.so* /output/lib/

# Copy ONLY non-system dependencies (exclude libc, libm, etc. which Lambda provides)
RUN cp -P /usr/lib64/libjson-c.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libxml2.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libpcre2-8.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libssl.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libcrypto.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libz.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libbz2.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libcurl.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/liblzma.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libnghttp2.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libunistring.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libpsl.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libclammspack.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libgssapi_krb5.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libk5crypto.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libkrb5support.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libcom_err.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libltdl.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libkeyutils.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libkrb5.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libidn2.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libselinux.so* /output/lib/ 2>/dev/null || true && \
    cp -P /usr/lib64/libpcre2-8.so* /output/lib/ 2>/dev/null || true

# DO NOT copy system libraries (libc, libm, libpthread, libdl, librt, libgcc_s, libstdc++)
# Lambda runtime provides these and they must match the runtime's GLIBC version

# Copy virus definitions
RUN cp -r /var/lib/clamav /output/share/clamav 2>/dev/null || true

# Strip binaries and libraries
RUN strip /output/bin/* 2>/dev/null || true && \
    strip /output/lib/*.so* 2>/dev/null || true

# Check size
RUN du -sh /output && \
    ls -lh /output/bin/ && \
    /output/bin/clamscan --version

# Package the layer
WORKDIR /
RUN mkdir -p /layer && \
    cd /output && \
    zip -r /layer/clamav-layer.zip .

CMD ["echo", "ClamAV layer built successfully"]
