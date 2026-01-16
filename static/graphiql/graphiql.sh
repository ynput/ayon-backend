#!/bin/bash
urls=(
  "https://unpkg.com/graphiql-with-extensions@0.14.3/graphiqlWithExtensions.css"
  "https://unpkg.com/whatwg-fetch@2.0.3/fetch.js"
  "https://unpkg.com/react@16.8.6/umd/react.production.min.js"
  "https://unpkg.com/react-dom@16.8.6/umd/react-dom.production.min.js"
  "https://unpkg.com/graphiql-with-extensions@0.14.3/graphiqlWithExtensions.min.js"
  "https://unpkg.com/js-cookie@3.0.0-rc.2/dist/js.cookie.umd.min.js"
  "https://unpkg.com/subscriptions-transport-ws@0.8.3/browser/client.js"
  "https://unpkg.com/graphiql-subscriptions-fetcher@0.0.2/browser/client.js"
)


# Download each file, stripping the unpkg domain from the local path
for url in "${urls[@]}"; do
  # This regex removes 'https://unpkg.com/' from the string
  local_path=$(echo "$url" | sed 's|https://unpkg.com/|lib/|')
  
  echo "Downloading to: ./$local_path"
  curl --create-dirs -Lo "./$local_path" "$url"
done
