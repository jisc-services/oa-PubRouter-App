/*
*   service_accounts.js - functions used on the Users and User screens to process Account status changes.
*/

function setButtonSpanValues($iconEl, txt, pressed, label, tab) {
/*  Function to set Aria and Text values for the <span> elements associated with displayed buttons (RepoStatus and On-Off).
*
*   @param $iconEl: Jquery object corresponding to clickable (icon) element
*   @param: txt - Text to display on screen (in the HTML element preceding the passed $iconEl)
*   @param: pressed - value to assign to the aria-pressed attribute
*   @param: label - value to assign tot the aria-label attribute
*   @param: tab - if not null, then boolean value determines whether tabindex value is to be set or removed
*/
    // Set aria on current element (the icon), and text on previous element (displayed text value)
    $iconEl.attr('aria-pressed', pressed).attr('aria-label', label).prev().text(txt);
    if(tab !== null){
        if(tab){
            $iconEl.attr('tabindex', '0')
        }
        else {
            $iconEl.removeAttr('tabindex')
        }
    }
}

function setTextAndAriaForRepoStatus($iconEl, status) {
/*  Function to set Aria and Text values for Repository status button.
*
*   @param $iconEl: Jquery object corresponding to clickable (icon) element
*   @param: status - Repository status value, one of 'off', 'failing', 'okay', 'problem'
*/
    if(status == 'off'){
        setButtonSpanValues($iconEl, status, 'undefined', 'Button is disabled', false);
    }
    else if(status == 'failing') {
        setButtonSpanValues($iconEl, status, 'false', 'Toggle repository to okay', true);
    } else {
        setButtonSpanValues($iconEl, status, 'true', 'Toggle repository to failing', true);
    }
}

function setTextAndAriaForOnOff($row, $iconEl, status) {
/*  Function to set Aria and Text values for On-Off button, and possibly also the Repository status button.
*
*   @param $iconEl: Jquery object corresponding to clickable (icon) element
*   @param: status - Status value, one of 'off', 'failing', 'okay', 'problem'
*/
    if(status == 'off'){
        setButtonSpanValues($iconEl, 'Off', 'false', 'Turn account On', null);
    }
    else {
        setButtonSpanValues($iconEl, 'On', 'true', 'Turn account Off', null);
    }
    // If a repository status element exists, then update it 
    const $statusEl = $row.find(".toggle-repo");
    if($statusEl.length){
        setTextAndAriaForRepoStatus($statusEl, status);
    }
}

function clickHandler(el, endpoint, is_on_off){
    /*  Function to do requests with repository status then update the repository status column
     *  @param el: javascript object (icon) that was clicked
     *  @param endpoint: The API call endpoint to append to base URL
     *  @param is_on_off: Boolean - True=on/off element; False=Status element
     * */
    const $iconEl = $(el);
    const $row = $iconEl.closest("tr");

    // If waiting for ajax request to complete
    if($row.hasClass("waiting") ){
        return; // Do nothing
    }

    // Set waiting class while AJAX request in progress
    $row.addClass("waiting");

    // Do AJAX request to server
    $.ajax({
            type: "POST",
            url: $row.data("ajax_url"),
            dataType: "json",
            data: JSON.stringify({func: endpoint}),
            contentType: "application/json; charset=utf-8"
            }).done(function(retData){
                // retData: {"status": "okay|failing|problem|off"}
                // Reset row class value
                $row.attr("class", "acc-" + retData.status);
                // If on/off button is toggled, need to also update the status
                if(is_on_off){
                    setTextAndAriaForOnOff($row, $iconEl, retData.status);
                } else {
                    setTextAndAriaForRepoStatus($iconEl, retData.status)
                }
            }).fail(function(xhr, status, error){
                // Remove waiting class if we fail
                $row.removeClass("waiting");
                alert(xhr.responseJSON.error);
            });
}

function setButtonEventHandler(selector, endpoint, is_on_off) {
    $(selector).on("click keydown", function(event){
		if(isClickOrAllowedKeypress(event)) {
			clickHandler(this, endpoint, is_on_off);
		}
    })
}


$(document).ready(function(){

    // Set text and aria values for status and on/off buttons showing in the table users table
    // displayed in both users.html and user.html templates
    $('tbody.user_tbody tr').each(function(){
        const $row = $(this);
        const cl = $row.attr('class');
        if(cl){
            // Set text and aria values for BOTH on-off and, possibly, repo-status buttons based on status class value
            // set in parent row (<tr> element).  Need to strip the 'acc-' substring from the class value. 
            setTextAndAriaForOnOff($row, $row.find(".toggle-on-off"), cl.substring(4));
        }
    });
    // Click/keypress event for the repository on/off button
    setButtonEventHandler('.toggle-on-off', 'toggle_account', true);

    // Click/keypress event for the repository status button
    setButtonEventHandler('.toggle-repo', 'toggle_repo_status', false);

});
