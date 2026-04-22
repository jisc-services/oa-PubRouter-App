# xapi - Exclusive API

This deployment configuration is used when Router API is run exclusively on App2 server.  In such cases **xweb** (exclusive Web GUI) should be deployed on the other server (App1).

## Gateway NGINX Configuration
When **xapi** is deployed, the Gateway NGINX must be configured to:
* route API traffic to App2 (where **xapi** is running)
* route Router Web traffic to App1 (where **xweb** should be running).
