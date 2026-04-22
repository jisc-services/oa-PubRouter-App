/*
* Functionality for disabling and enabling cookies related to user tracking.
* - Display cookie banner at top of screen while a user has not explicitly indicated whether they do/don't want tracking
* - Functionality specific to /about/cookies page - display / functionality of the toggle-button
*/

// Wrap in an anonymous function to not set any of these variables in global scope.
// Note that this function executes when the script is loaded.
(function() {
    const jiscGaCode = 'UA-73663652-1';
    // Regex for capturing tracking cookie details
    const reTracking = /\btracking_enabled=(true|false)\b/;
    // If tracking cookie is set, then trackingEnabledArr will be an array, with element [0] being entire cookie string,
    // & element [1] set to "true" or "false";  otherwise trackingEnabledArr will be null
    const trackingEnabledArr = document.cookie.match(reTracking);

    // Global variable indicates if cookie exists (and so if cookie tracking has been set)
    const trackingSet = trackingEnabledArr !== null;
    // Global variable indicates if cookie tracking is on
    var trackingOn = trackingSet && trackingEnabledArr[1] == "true";

    function setGoogleTracking (setCookies) {
        if(setCookies) {
            (function(i,s,o,g,r,a,m){i['GoogleAnalyticsObject']=r;i[r]=i[r]||function(){
            (i[r].q=i[r].q||[]).push(arguments)},i[r].l=1*new Date();a=s.createElement(o),
            m=s.getElementsByTagName(o)[0];a.async=1;a.src=g;m.parentNode.insertBefore(a,m)
            })(window,document,'script','https://www.google-analytics.com/analytics.js','ga');

            ga('create', jiscGaCode, 'auto');
            ga('send', 'pageview');
        }
        else {
            // Regex for capturing Google cookie names (all begin with "_g")
            // NB. As regex pattern ends with '/g' the whole string is searched and ONLY the capture group values are returned
            const reGoogle = /\b(_g[^=]*)\b/g;
            let googleCookieNameArr = document.cookie.match(reGoogle) || [];    // If no match, set to an empty array
            for(const cookieName of googleCookieNameArr){
                // DELETE each Google cookie by setting expiry date in the past
                document.cookie = `${cookieName}=; expires=Thu, 01 Jan 1970 00:00:01 UTC; path=/; domain=.jisc.ac.uk;`;
            }
        }
    }

    function setTrackingCookie(isEnabled) {
        // Cookie set to expire in 180 days from today
        const days = 180;
        let expireDate = new Date();
        expireDate.setTime(expireDate.getTime() + 3600000 * 24 * days);
        document.cookie = "tracking_enabled=" + isEnabled + ";expires=" + expireDate.toUTCString() + ";path=/";
        setGoogleTracking(isEnabled);
        trackingOn = isEnabled;
    }

    // Set google tracking
    setGoogleTracking(trackingOn);

    $(document).ready(function(){
        // Set cookieButton (NOTE: only found on the about/cookies page)
        const $cookieToggleBtn = $('#cookie-toggle-button');

        function setCookieToggleBtnAttribs() {
            if(trackingOn){
                $cookieToggleBtn.removeClass().addClass('cookie-on').attr('aria-pressed', 'true').attr('aria-label', 'Press to disable cookies');
            }
            else {
                $cookieToggleBtn.removeClass().addClass('cookie-off').attr('aria-pressed', 'false').attr('aria-label', 'Press to enable cookies');
            }
        };

        function setCookieToggleBtn() {
            // Only execute function if $cookieToggleBtn NOT empty, indicating that we are on cookie page
            if($cookieToggleBtn.length){
                setCookieToggleBtnAttribs();   // Set class for toggle button
                $cookieToggleBtn.on("click", function(){
                    setTrackingCookie(! trackingOn);
                    setCookieToggleBtnAttribs();   // Redisplay toggle button
                });
            }
        }

        // If Cookie tracking has been set
        if(trackingSet){
            setCookieToggleBtn();       // Set the toggle button to reflect current status (if on Cookie page)
        }
        else {
            // No enable_tracking cookie is set, show banner where cookie enable/disable is requested.

            const $cookieBlock = $('#cookie-container');
            
            // Fade the container in so it looks nice
            $cookieBlock.slideDown("linear");

            // Set click handler on the 2 buttons, with values "no" (no tracking) and "yes" (yes tracking)
            $cookieBlock.on("click", "button", function(e){
                // set the tracking cookie to true/false depending on button value (yes/no)
                setTrackingCookie(e.currentTarget.value === "yes");
                $cookieBlock.slideUp("linear");   // hide the cookie setting banner
                setCookieToggleBtn();       // Set the toggle button to reflect current status (if on Cookie page)
            });
        }

    })
})();
