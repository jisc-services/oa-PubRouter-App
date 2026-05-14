# sword-in - SWORD2 server for publishers to send deposits to Router

This deployment configuration is used when SWORD-IN is run exclusively on App2 server.

## Gateway NGINX Configuration
When **SWORD-IN (sword2 endpoint)** is deployed, the Gateway NGINX must be configured to:
* route sword2 traffic to App2 (where **sword-in app** is running)
