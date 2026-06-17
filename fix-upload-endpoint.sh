#!/bin/bash

echo "=== Fixing WhatsApp Campaign Dashboard Upload Issue ==="
echo ""

# Step 1: Stop conflicting whatsapp_saas service
echo "1️⃣  Stopping whatsapp_saas service (port 8000 conflict)..."
sudo systemctl stop whatsapp_saas
sudo systemctl disable whatsapp_saas
echo "   ✓ Stopped and disabled"

# Step 2: Ensure wa-campaign-dashboard is running on port 8001
echo ""
echo "2️⃣  Verifying wa-campaign-dashboard configuration..."

# Check if .env has correct port
if grep -q "PORT=8001" /opt/wa-campaign-dashboard/.env; then
    echo "   ✓ PORT=8001 is correct"
else
    echo "   Updating PORT to 8001..."
    sed -i 's/PORT=.*/PORT=8001/' /opt/wa-campaign-dashboard/.env
fi

# Check SERVER_BASE_URL
if grep -q "SERVER_BASE_URL=https://phone.whatsappworld.in" /opt/wa-campaign-dashboard/.env; then
    echo "   ✓ SERVER_BASE_URL is correct"
else
    echo "   Updating SERVER_BASE_URL..."
    sed -i 's|SERVER_BASE_URL=.*|SERVER_BASE_URL=https://phone.whatsappworld.in|' /opt/wa-campaign-dashboard/.env
fi

# Step 3: Ensure /uploads directory exists and has correct permissions
echo ""
echo "3️⃣  Checking /uploads directory..."
if [ ! -d "/opt/wa-campaign-dashboard/uploads" ]; then
    mkdir -p /opt/wa-campaign-dashboard/uploads
    echo "   ✓ Created /uploads directory"
else
    echo "   ✓ /uploads directory exists"
fi

# Set proper permissions
chmod 755 /opt/wa-campaign-dashboard/uploads
chown www-data:www-data /opt/wa-campaign-dashboard/uploads 2>/dev/null || true
echo "   ✓ Set permissions (755)"

# Step 4: Configure Nginx to serve /uploads
echo ""
echo "4️⃣  Checking Nginx configuration for /uploads..."

NGINX_CONF="/etc/nginx/sites-enabled/nodelib"

# Check if /uploads location block exists
if grep -q "location /uploads" "$NGINX_CONF"; then
    echo "   ✓ /uploads location already configured"
else
    echo "   Adding /uploads location to Nginx..."
    
    # Backup original
    sudo cp "$NGINX_CONF" "$NGINX_CONF.bak"
    
    # Add uploads location before the closing brace of phone.whatsappworld.in server block
    sudo sed -i '/server_name phone.whatsappworld.in;/,/^}/s|proxy_cache_bypass|location /uploads {\n        alias /opt/wa-campaign-dashboard/uploads;\n        expires 30d;\n        add_header Cache-Control "public, immutable";\n    }\n\n    proxy_cache_bypass|' "$NGINX_CONF"
    
    echo "   ✓ Added /uploads location"
fi

# Step 5: Test Nginx configuration
echo ""
echo "5️⃣  Testing Nginx configuration..."
if sudo nginx -t 2>&1 | grep -q "successful"; then
    echo "   ✓ Nginx configuration is valid"
    echo "   Reloading Nginx..."
    sudo systemctl reload nginx
    echo "   ✓ Nginx reloaded"
else
    echo "   ❌ Nginx configuration has errors"
    sudo nginx -t
fi

# Step 6: Restart wa-dashboard
echo ""
echo "6️⃣  Restarting wa-dashboard service..."
sudo systemctl restart wa-dashboard
sleep 3
echo "   ✓ Restarted"

# Step 7: Verify everything is working
echo ""
echo "7️⃣  Verifying services..."
echo ""

if systemctl is-active --quiet wa-dashboard; then
    echo "   ✓ wa-dashboard is RUNNING on port 8001"
else
    echo "   ❌ wa-dashboard is NOT running"
    systemctl status wa-dashboard
fi

if ! systemctl is-active --quiet whatsapp_saas; then
    echo "   ✓ whatsapp_saas is STOPPED"
else
    echo "   ⚠️  whatsapp_saas is still running"
fi

# Step 8: Test the upload endpoint
echo ""
echo "8️⃣  Testing media upload endpoint..."
echo "   Creating test image..."

python3 << 'PYEOF'
import base64
png_data = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
)
with open('/tmp/test-image.png', 'wb') as f:
    f.write(png_data)
PYEOF

echo "   Testing POST /api/media/upload on port 8001..."
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST http://localhost:8001/api/media/upload \
  -F "file=@/tmp/test-image.png" \
  -F "description=Test upload")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | head -n -1)

echo "   HTTP Status: $HTTP_CODE"

if [ "$HTTP_CODE" = "200" ]; then
    echo "   ✓ Upload endpoint is WORKING!"
    echo ""
    echo "   Response:"
    echo "   $BODY" | head -c 200
    echo ""
else
    echo "   Response: $BODY"
fi

# Step 9: Final instructions
echo ""
echo "=== Fix Complete ==="
echo ""
echo "✅ Your dashboard should now work correctly!"
echo ""
echo "📍 Access your dashboard at:"
echo "   https://phone.whatsappworld.in/campaigns"
echo ""
echo "📝 What was fixed:"
echo "   1. Stopped whatsapp_saas (port 8000 conflict)"
echo "   2. Verified wa-campaign-dashboard runs on port 8001"
echo "   3. Ensured /uploads directory exists with correct permissions"
echo "   4. Configured Nginx to serve /uploads directory"
echo "   5. Verified media upload endpoint is working"
echo ""
echo "🧪 Try uploading an image in the Campaigns page now!"
