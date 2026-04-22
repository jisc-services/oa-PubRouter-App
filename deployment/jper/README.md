# jper - Router Web GUI + API

This deployment configuration is used when Router Web (GUI) and API are run exclusively on App1.  

In such cases NEITHER **xweb** (exclusive Web GUI) nor **xapi** (exclusive API) should be deployed (on either App server).

## Gateway NGINX Configuration
When **jper** is deployed, the Gateway NGINX must be configured to route BOTH Router Web traffic and API traffic to App1.
