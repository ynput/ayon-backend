"""Example of using OAuth client_credentials grant type.

This example demonstrates how to authenticate using client credentials
for service-to-service authentication without user interaction.
"""

import requests
from typing import Dict, Any


class AyonServiceClient:
    """OAuth client for service-to-service authentication."""

    def __init__(self, client_id: str, client_secret: str, base_url: str):
        """Initialize the service client.
        
        Args:
            client_id: OAuth client ID
            client_secret: OAuth client secret
            base_url: Base URL of the AYON server (e.g., "http://localhost:5000")
        """
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = base_url
        self.access_token = None
        self.token_expiry = None

    def get_access_token(self, scope: str = "read") -> Dict[str, Any]:
        """Get access token using client credentials grant.
        
        Args:
            scope: Requested scope (default: "read")
            
        Returns:
            Token response containing access_token, token_type, expires_in, etc.
            
        Example response:
            {
                "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
                "token_type": "Bearer",
                "expires_in": 3600,
                "scope": "read"
            }
        """
        token_url = f"{self.base_url}/oauth/token"

        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": scope
        }

        response = requests.post(token_url, data=data)
        response.raise_for_status()

        token_data = response.json()
        self.access_token = token_data["access_token"]

        # Calculate token expiry
        import time
        if "expires_in" in token_data:
            self.token_expiry = time.time() + token_data["expires_in"]

        return token_data

    def make_authenticated_request(
        self, 
        endpoint: str, 
        method: str = "GET",
        **kwargs
    ) -> requests.Response:
        """Make an authenticated request to the API.
        
        Args:
            endpoint: API endpoint (e.g., "/api/projects")
            method: HTTP method (GET, POST, etc.)
            **kwargs: Additional arguments to pass to requests
            
        Returns:
            Response object
        """
        # Ensure we have a valid token
        if not self.access_token:
            self.get_access_token()

        # Check if token is expired
        import time
        if self.token_expiry and time.time() >= self.token_expiry:
            self.get_access_token()

        # Add authorization header
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.access_token}"

        url = f"{self.base_url}{endpoint}"
        response = requests.request(method, url, headers=headers, **kwargs)

        return response


def example_usage():
    """Example usage of the service client."""
    
    # Initialize the client
    client = AyonServiceClient(
        client_id="your_service_client_id",
        client_secret="your_service_client_secret",
        base_url="http://localhost:5000"
    )

    # Get access token
    print("Getting access token...")
    token_data = client.get_access_token(scope="read")
    print(f"✓ Access token obtained: {token_data['access_token'][:20]}...")
    print(f"  Token type: {token_data['token_type']}")
    print(f"  Expires in: {token_data['expires_in']} seconds")
    print(f"  Scope: {token_data['scope']}")

    # Use the token to make API requests
    print("\nMaking authenticated API request...")
    response = client.make_authenticated_request("/api/projects")
    
    if response.status_code == 200:
        print(f"✓ API request successful!")
        projects = response.json()
        print(f"  Found {len(projects)} projects")
    else:
        print(f"✗ API request failed: {response.status_code}")
        print(f"  Error: {response.text}")


def example_token_introspection():
    """Example of token introspection."""
    
    client = AyonServiceClient(
        client_id="your_service_client_id",
        client_secret="your_service_client_secret",
        base_url="http://localhost:5000"
    )

    # Get token
    token_data = client.get_access_token()
    access_token = token_data["access_token"]

    # Introspect the token
    introspect_url = f"{client.base_url}/oauth/introspect"
    response = requests.post(
        introspect_url,
        data={"token": access_token}
    )

    if response.status_code == 200:
        introspection = response.json()
        print("Token introspection:")
        print(f"  Active: {introspection['active']}")
        print(f"  Client ID: {introspection['client_id']}")
        print(f"  Scope: {introspection['scope']}")
        print(f"  Token type: {introspection['token_type']}")
        
        # Note: username/sub are not present for client_credentials tokens
        if 'username' in introspection:
            print(f"  Username: {introspection['username']}")
        else:
            print("  Username: (none - client credentials)")


if __name__ == "__main__":
    print("=" * 60)
    print("AYON OAuth Client Credentials Example")
    print("=" * 60)
    print()
    
    # Note: You need to create an OAuth client first with:
    # - grant_types including "client_credentials"
    # - client_type set to "confidential"
    
    print("Before running this example:")
    print("1. Create an OAuth client via the admin API")
    print("2. Ensure grant_types includes 'client_credentials'")
    print("3. Replace 'your_service_client_id' and 'your_service_client_secret'")
    print()
    
    # Uncomment to run:
    # example_usage()
    # example_token_introspection()
