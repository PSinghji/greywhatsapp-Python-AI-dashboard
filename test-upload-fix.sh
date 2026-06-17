#!/bin/bash

# WhatsApp Campaign Dashboard - Upload Endpoint Diagnostic Script
# This script tests if the upload endpoint is working correctly

echo "=== WhatsApp Campaign Dashboard - Upload Diagnostic ==="
echo ""

# Check if .env exists
if [ ! -f /opt/wa-campaign-dashboard/.env ]; then
    echo "❌ .env file not found at /opt/wa-campaign-dashboard/.env"
    exit 1
fi

# Source .env
source /opt/wa-campaign-dashboard/.env

echo "📋 Current Configuration:"
echo "   MongoDB: $MONGO_URL"
echo "   Database: $DB_NAME"
echo "   Upload Dir: $UPLOAD_DIR"
echo "   Server Base URL: $SERVER_BASE_URL"
echo "   Port: $PORT"
echo ""

# Check if uploads directory exists
echo "📁 Checking /uploads directory..."
if [ -d "/opt/wa-campaign-dashboard/$UPLOAD_DIR" ]; then
    echo "   ✓ Directory exists"
    ls -lh /opt/wa-campaign-dashboard/$UPLOAD_DIR | head -5
else
    echo "   ❌ Directory does NOT exist. Creating..."
    mkdir -p /opt/wa-campaign-dashboard/$UPLOAD_DIR
    chmod 755 /opt/wa-campaign-dashboard/$UPLOAD_DIR
    echo "   ✓ Created and set permissions"
fi
echo ""

# Check if service is running
echo "🔧 Checking if wa-dashboard service is running..."
if systemctl is-active --quiet wa-dashboard; then
    echo "   ✓ Service is running"
    PORT_CHECK=$(netstat -tlnp 2>/dev/null | grep uvicorn | awk '{print $4}' | grep -oE '[0-9]+$' | tail -1)
    echo "   Running on port: $PORT_CHECK"
else
    echo "   ❌ Service is NOT running"
    echo "   Starting service..."
    systemctl start wa-dashboard
    sleep 2
fi
echo ""

# Test the upload endpoint
echo "🧪 Testing upload endpoint..."
echo "   Creating test image..."

# Create a simple test image (1x1 pixel PNG)
python3 << 'PYEOF'
import base64
import os

# 1x1 transparent PNG
png_data = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
)

test_file = '/tmp/test-image.png'
with open(test_file, 'wb') as f:
    f.write(png_data)
print(f"✓ Test image created: {test_file}")
PYEOF

echo ""
echo "   Testing POST /api/media/upload..."

# Try uploading to localhost:8000 first
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST http://localhost:8000/api/media/upload \
  -F "file=@/tmp/test-image.png" \
  -F "description=Test upload")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

echo "   HTTP Status: $HTTP_CODE"
echo "   Response: $BODY"

if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✓ Upload successful!"
    echo ""
    echo "   Public URL should be accessible at:"
    echo "   $SERVER_BASE_URL/uploads/..."
else
    echo "   ❌ Upload failed with status $HTTP_CODE"
    echo ""
    echo "   Checking if the issue is with the reverse proxy..."
    echo "   Testing direct access to FastAPI..."
    
    # Try to find the actual port
    ACTUAL_PORT=$(netstat -tlnp 2>/dev/null | grep uvicorn | awk '{print $4}' | grep -oE '[0-9]+$' | tail -1)
    if [ ! -z "$ACTUAL_PORT" ]; then
        echo "   Found uvicorn running on port: $ACTUAL_PORT"
        echo "   Retrying on port $ACTUAL_PORT..."
        
        RESPONSE2=$(curl -s -w "\n%{http_code}" -X POST http://localhost:$ACTUAL_PORT/api/media/upload \
          -F "file=@/tmp/test-image.png" \
          -F "description=Test upload")
        
        HTTP_CODE2=$(echo "$RESPONSE2" | tail -1)
        BODY2=$(echo "$RESPONSE2" | head -n -1)
        
        echo "   HTTP Status: $HTTP_CODE2"
        echo "   Response: $BODY2"
        
        if [ "$HTTP_CODE2" = "200" ]; then
            echo "   ✓ Upload works on port $ACTUAL_PORT!"
            echo ""
            echo "   Issue: Your .env PORT is $PORT but service runs on $ACTUAL_PORT"
            echo "   Fix: Update PORT in .env to $ACTUAL_PORT and restart"
        fi
    fi
fi

echo ""
echo "=== Diagnostic Complete ==="
