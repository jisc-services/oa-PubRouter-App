# xweb - Exclusive Web

This deployment configuration is used when Router Web (GUI) is run exclusively on App1.  In such cases **xapi** (exclusive Router API) should be deployed on the other server (App2).

## Gateway NGINX Configuration
When **xweb** is deployed, the Gateway NGINX must be configured to:
* route Router Web traffic to App1 (where **xweb** is running)
* route Router API traffic to App2 (where **xapi** should be running).
