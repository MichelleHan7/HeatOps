from fortyguard_client import FortyGuardClient

client = FortyGuardClient()

print("HeatOps FortyGuard client initialized successfully.")
print("API key loaded:", bool(client.api_key))