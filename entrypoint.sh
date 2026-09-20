#!/bin/sh
set -e

# Create .streamlit directory if it doesn't exist
mkdir -p .streamlit

# Write environment variables to .streamlit/secrets.toml at runtime
cat <<EOF > .streamlit/secrets.toml
[auth]
redirect_uri = "${STREAMLIT_AUTH__REDIRECT_URI}"
cookie_secret = "${STREAMLIT_AUTH__COOKIE_SECRET}"

[auth.google]
client_id = "${STREAMLIT_AUTH__GOOGLE__CLIENT_ID}"
client_secret = "${STREAMLIT_AUTH__GOOGLE__CLIENT_SECRET}"
server_metadata_url = "${STREAMLIT_AUTH__GOOGLE__SERVER_METADATA_URL:-https://accounts.google.com/.well-known/openid-configuration}"
EOF

# Execute the main CMD passed from Dockerfile / Cloud Run
exec "$@"
