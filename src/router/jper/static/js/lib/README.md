#Library contents

This directory contains third-party JS library code that PublicationsRouter requires.

Certain files need more explanation.  The following list mentions the main source file, but in all cases there is a corresponding *minified* version (which has a `.min` before the `.js` suffix).

* **ux.jisc-1.1.0.script-head.js** - A Jisc UX library originally hosted on a Jisc CDN site.  It is loaded in the `<head>` section of the HTML page
* **oa.ux.jisc-1.1.0.script-foot.js** - A much cut down version of the Jisc UX library named *ux.jisc-1.1.0.script-foot.js* which was originally hosted on a Jisc CDN site. This contains only the functionality needed by PubRouter. It is loaded at the bottom of the `<body>` section of the HTML page
* **oa.query-ui.js** - a cut-down version of jquery-ui library that includes ONLY the functions required by Jisc UX library code.  
* **unused.jquery-ui.js** - A now unused version of the popular *jquery.ui.js (v1.12.1)* library, which was originally included for use by Jisc UX code. However, a much cut-down version named *oa.query-ui.js* which only includes the essential functions has replaced its use.

