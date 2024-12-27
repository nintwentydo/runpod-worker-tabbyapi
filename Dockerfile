ARG BUILDKIT_SBOM_SCAN_CONTEXT=true
ARG BUILDKIT_SBOM_SCAN_STAGE=true

# Use Runpod's base image with CUDA 12.4.1
FROM runpod/base:0.6.2-cuda12.4.1 as build-000

# Set Github args
ARG GIT_REPO=https://github.com/nintwentydo/tabbyAPI.git
ARG DO_PULL=true
ENV DO_PULL $DO_PULL

# Set the working directory in the container
WORKDIR /app

# Copy model
#COPY src/models/pixtral-12b-exl2-8.0bpw /app/models/pixtral-12b-exl2-8.0bpw

# Install requirements
COPY builder/requirements.txt /app/requirements.txt
RUN pip3.11 install --no-cache-dir -r /app/requirements.txt

# Update repo
RUN if [ ${DO_PULL} ]; then \
    git init && \
    git remote add origin $GIT_REPO && \
    git fetch origin && \
    git pull origin main && \
    echo "Pull finished"; fi

# Install packages specified in pyproject.toml cu121
RUN pip3.11 install --no-cache-dir .[cu121,extras]

# Copy the sample configuration and adjust the host to 0.0.0.0
RUN cp -av src/config.yml /app/models/config.yml

# Copy the handler.py script into the container
COPY src/handler.py /app/handler.py

# Copy the start.sh script and make it executable
COPY src/start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Set the command to run when the container starts
CMD ["/bin/bash", "/app/start.sh"]