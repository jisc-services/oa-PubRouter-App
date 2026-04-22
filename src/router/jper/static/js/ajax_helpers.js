/*
 ajax_helpers.js - Code implememting a standard approach for Ajax interactions & other GUI features:
    * doAjaxGet
    * doAjaxPost
    * flashMsg
    * selectChangeHandler

 Author: Jisc

*/

function _handle_error(jqXHR, errFn) {
/*
    :param jqXHR: jQuery ajax object
    :param errFn: OPTIONAL Function with a single 'error-msg' parameter that will handle the error msg as required.  If
                  no function is provided then the error is displayed in standard Windows dialog box.

    :return: NOTHING
*/
//console.log(jqXHR);
    let msg = jqXHR.responseJSON?.error;
    if (! msg) {
        msg = jqXHR.statusText;
    }
    if (jqXHR.status != 400) {
        msg += ` (${jqXHR.status})`;
    }
    if (errFn) {
        errFn(msg);
    }
    else {
        alert(msg);
    }
}

function doAjaxGet(urlStr, dataO, successFn, errFn){
/*
    AJAX GET.
    :param urlStr: URL endpoint for AJAX request
    :param dataO: Data object that is sent to server
    :param successFn: Function with a single 'responseObject' parameter that will handle the (successful)  response
                      from server
    :param errFn: OPTIONAL Function with a single 'error-msg' parameter that will handle the error msg as required.  If
                  no function is provided then the error is displayed in standard Windows dialog box.

    :return: jqXHR object
*/
    return $.getJSON(urlStr, dataO, successFn)
        .fail(function(jqXHR, textStatus, errorThrown) {
                _handle_error(jqXHR, errFn);
            });
}

function doAjaxPost(urlStr, dataO, successFn, errFn){
/*
    AJAX POST.
    :param urlStr: URL endpoint for AJAX request
    :param dataO: Data object that is sent to server
    :param successFn: Function with a single 'responseObject' parameter that will handle the (successful)  response
                      from server
    :param errFn: OPTIONAL Function with a single 'error-msg' parameter that will handle the error msg as required.  If
                  no function is provided then the error is displayed in standard Windows dialog box.

    :return: jqXHR object
*/
     return $.ajax({
        type: "POST",
        dataType: "json",
        contentType: "application/json; charset=utf-8",
        url: urlStr,
        data: JSON.stringify(dataO),
        success: successFn,
        error: function(jqXHR, textStatus, errorThrown){
            _handle_error(jqXHR, errFn);
            }
        });
}

function doAjaxPatch(urlStr, dataO, successFn, errFn){
/*
    AJAX PATCH.
    :param urlStr: URL endpoint for AJAX request
    :param dataO: Data object that is sent to server
    :param successFn: Function with a single 'responseObject' parameter that will handle the (successful)  response
                      from server
    :param errFn: OPTIONAL Function with a single 'error-msg' parameter that will handle the error msg as required.  If
                  no function is provided then the error is displayed in standard Windows dialog box.

    :return: jqXHR object
*/
     return $.ajax({
        type: "PATCH",
        dataType: "json",
        contentType: "application/json; charset=utf-8",
        url: urlStr,
        data: JSON.stringify(dataO),
        success: successFn,
        error: function(jqXHR, textStatus, errorThrown){
            _handle_error(jqXHR, errFn);
            }
        });
}

class FlashMsg{
/*  Class for displaying messages.
*       Usage:  flasher = new FlashMsg($jQuery-flash-els, default-display-duration-secs)
*               flasher.msg($divEl, ind, msg, override-show-ecs) - where always want to use same $flashEl (set when class initialised)
*               flasher.dispMsg($flashEl, $divEl, ind, msg, override-show-secs) - where using different $flashEl values
*
*   :param $flashEl: OPTIONAL jQuery element(s) - where msg will be displayed if using .msg() method
*   :param showSecs: OPTIONAL Number - Default number of seconds to display msgs for (can be decimal number).
*                                      IMPORTANT: Value 0 - means displayed msgs are NOT automatically hidden.
*/
    constructor($flashEl=null, showSecs=0) {
        this.$flashEl = $flashEl;
        this.sleepMs = showSecs * 1000;
        this.timer = null;
        this.$lastFlashEl = null;
        this.$lastDivEl = null;
    }

    dispMsg($flashEl, $divEl, ind, msg, showSecs=null) {
        /*
        DISPLAY MESSAGE
        :param $flashEl: Jquery message element
        :param $divEl: OPTIONAL Jquery div (e.g. panel/form) element which requires green/red shading depending on message.
        :param ind: String - indicator: "s" success, "i" info, "e" error
        :param msg: String - message text to display
        :param showSecs: OPTIONAL Number of seconds to wait before message is automatically hidden (via "hide" class)
        */
        // Clear existing timer if it exists to prevent early removal of new message
        if (this.timer !== null){
            clearTimeout(this.timer);
            this.timer = null;
        }
        if (this.$lastFlashEl !== $flashEl){
            this.$lastFlashEl?.addClass("hide");
        }
        this.$lastDivEl?.removeClass("flash-success flash-danger flash-info");
        this.$lastFlashEl = $flashEl;
        this.$lastDivEl = $divEl;

        $flashEl.html(msg).removeClass("hide box--success box--danger box--info").addClass({s: "box--success", e: "box--danger", i:"box--info"}[ind]);
        $divEl?.addClass({s: "flash-success", e: "flash-danger", i:"flash-info"}[ind]);
        const sleepMillisecs = showSecs === null ? this.sleepMs : showSecs * 1000;
        if (sleepMillisecs > 0) {
            this.timer = setTimeout(function(){
                    $flashEl.addClass("hide");
                    $divEl?.removeClass("flash-success flash-danger flash-info");
                }, sleepMillisecs);
        }
    }

    msg($divEl, ind, msg, showSecs=null) {
    /*
    *   :param $divEl: jQuery div element (can be null) for background color
    *   :param ind: Char indicator: "s" success, "i" info, "e" error
    *   :param showSecs: OPTIONAL Number of seconds to display msg for (will override class default). 0 = permanent display.
    */
        this.dispMsg(this.$flashEl, $divEl, ind, msg, showSecs);
    }
}

function selectChangeHandler($select, selectFunc){
/*
    CHANGE HANDLER for SELECT input
    :param $select: jQuery select element
    :param selectFunc: Function to run when select occurs - takes 2 parameters (selected_value, selected_description)
*/
    // Set Select Change handler -
    $select.on("change", function(e){
        e.stopPropagation();
        // We expect 1 item to be selected - the children () func will return an array - so we use [0] element.
        selected = $select.children(":selected")[0];
        selectFunc(selected.value, selected.text);
    });
}
