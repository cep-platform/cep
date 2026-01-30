FROM mvance/unbound:latest

WORKDIR /app

# Install Python + pip
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        iproute2 \
        python3 \
        python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Install FastAPI + ASGI server
RUN pip3 install --no-cache-dir --break-system-packages fastapi uvicorn rich python-dotenv

# Copy API code
COPY service/api.py api.py
COPY config/a-records.conf /opt/unbound/etc/unbound/a-records.conf
COPY config/unbound_template.conf /opt/unbound/etc/unbound/unbound_template.conf

# Expose API port (informational with host networking)
EXPOSE 8000

# Default command
CMD sh -c '\
    unbound -d & \
    exec uvicorn api:app --host 0.0.0.0 --port 8053 \
'

