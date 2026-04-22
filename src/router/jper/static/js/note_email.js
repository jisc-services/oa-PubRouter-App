/*
 note_email.js - Code for Contact panels (email/note/todo) on Organisation Account web-pages pages (user.html) and
 Recent error (recent_errors.html) pages:
     - display a table of notes/emails associated with an account;
     - click handlers for note/email form
     - click handlers for email User email address selection Overlay
     - handle AJAX interactions with server to receive/send data

 ** THIS code DEPENDS on functions in `ajax_helpers.js` file.

Author: Jisc
*/

function initAndSetEmailNoteEventHandlers(ajaxQueryUrl, pubOrRepoInd, accId) {
/*
*   Function that provides all functionality related to Notes & Emails contact panel.
*
*   GENERAL RULE: The constants & variables declared below are accessed directly by functions -
*   i.e. they are NOT passed to functions as parameters.
*/
    const acDivIdStr = "#a" + accId;
    const $root = $(acDivIdStr);
    // let accId = acDivIdStr.slice(2); // acDivIdStr is like "#a1234"
    const apiKey = $root.data("apikey") || "";
    
    // Note/Email/ToDo FORM variables
    const $form = $(acDivIdStr + '-form');
    const $formFlashEl = $(acDivIdStr + '-form .flash');    // Elements for displaying flash messages
    const $errTable = $(acDivIdStr + '-err_tbl');
    
    // History Table variables
    const $histTblDiv = $(acDivIdStr + '-hist_tbl');
    const $histFilters = $(acDivIdStr + '-hist_filters');
    const $histFlashEl = $(acDivIdStr + '-hist .flash');
    // filtersObj: controls what info is retrieved/displayed in history table
    const filtersObj = {hist_num: 5, hist_type: "", hist_status: ""};
    // Map status character code to a CSS class
    const statusCssClassMap = {H: "hili", D: "deleted", N: "normal", R:"resolved"};

    // User Email selection variables
    const splitRegex = /[;, \r\n]+/;       // Regex to split string of emails separated by semicolon, comma, space(s)
    const $userEmailOverlay = $(acDivIdStr + '-user_emails');
    const $userEmailOlayTextArea = $userEmailOverlay.find("textarea").first();
    const userEmailObj = {};
    // Initialise userEmailObj
    for(const attrib of ["to_addr", "cc_addr"]){
        userEmailObj[attrib] = {
            $formAddr: $form.find(`textarea.input[name="${attrib}"]`),
            $olayAddr: $userEmailOverlay.find(`textarea[name="${attrib}"]`)
        }
    }
    let userSelectionModal = null;

    const flash = new FlashMsg(null, 6);
    let submitEnabled = true;   // Submit buttons are enabled


    function makeExpandingBody(title, body){
        return `<div class="small-gap-after transparent xt-accordion pale x-show"><span class="x-title">${title}</span><div class="title-accordion narrow small-gap-vert">${body}</div></div>`;
    }

    function formatHistTblRow(recO){
    /**
    *   Format a table row entry for a particular item, i.e. one of: Email, Bulk email, Note, ToDo entry.
    **/
        const emailDesc = {E: "Email", B: "Bulk email"};
        const groupBCC = {E: "", B: " (Bcc)"};
        let snippetA = "</td><td>";
        let errsSnippet = "";
        // If type is E:Email or B:Bulk-Email
        if ("EB".includes(recO.type)) {
            snippetA += `${emailDesc[recO.type]}</td><td class="small-disp"><div class="small-gap-after"><span class="bold-italic">To${groupBCC[recO.type]}:</span>&nbsp; ${recO.to_addr}</div>`;
            if (recO.cc_addr) {
                snippetA += `<div class="small-gap-after"><span class="bold-italic">Cc${groupBCC[recO.type]}:</span>&nbsp; ${recO.cc_addr}</div>`;
            }
            // Normal email
            if (recO.type === "E") {
                let numErrs = recO.err_ids.length;
                if (numErrs > 0) {
                    let s = numErrs > 1 ? "s" : "";
                    errsSnippet = `<br><br><i>${numErrs} error${s} attached (ID${s}: <span class="hili">${recO.err_ids.join(", ")}</span>).</i>`;
                }
            }
        }
        else{
            snippetA += (recO.type === "N" ? "Note": "ToDo") + '</td><td class="small-disp">';
        }

        let btnGroup = '</td><td>';
        // Bulk emails don't have buttons
        if (recO.type === "B"){
            btnGroup += '<div class="italic smaller wide-8rem">Administer from Bulk email screen.</div>';
        }
        else {
            // Construct Pin, Resolve, Clear & Delete buttons
            const btnSnippetA = `<button type="button" class="btn btn--3d value-btn `;
            const btnSnippetB = `" data-action="hist_func" data-id="${recO.id}"`;
            btnGroup += `${btnSnippetA}b_hili${btnSnippetB} title="Pin (highlight)" data-status="H">Pin</button>
                ${btnSnippetA}b_res${btnSnippetB} title="Mark item as resolved" data-status="R">Resolve</button>
                ${btnSnippetA}b_clear${btnSnippetB} title="Clear highlight or deletion" data-status="N">Clear</button>
                ${btnSnippetA}b_del${btnSnippetB} title="Delete item" data-status="D">Delete</button>`;
        }

        const trClass = statusCssClassMap[recO.status] || (recO.type === "T" ? "hili_todo" : 'normal');
        // line-feeds in the message body are replaced by <br>
        let bodyPart = (recO.body ? recO.body.replaceAll('\n', '<br>') : "") + errsSnippet;
        bodyPart = (recO.type === "B" && bodyPart.length > 350) ? makeExpandingBody('Body', bodyPart) : `<div>${bodyPart}</div>`;
        return `<tr class="${trClass}" data-type="${recO.type}"><td class="no-wrap">` + recO.created.slice(0,10) + snippetA +
            (recO.subject ? `<span class="bold-italic">Subject:</span>&nbsp; ${recO.subject}<br><br>` : "")  + bodyPart + btnGroup + "</td></tr>" ;
    };

    function listNotesEmails() {
    /**
    *   Display table of historic Notes, ToDos & Emails
    **/

        function successCreateHistTbl(responseO) {
            // Create the history table
            let $histTbl = $("<table></table>");
            $histTbl.append(`<thead><th>Date</th><th>Type</th><th>Text</th><th>Action</th></thead>`);
            let $histBody = $(`<tbody data-max_num="${filtersObj.hist_num}"></tbody>`).appendTo($histTbl);
            for (const recO of responseO) {
                $histBody.append(formatHistTblRow(recO));
                };
            $histTblDiv.empty().append($histTbl);
        };
        const dataObj = {
            func: "list_all_types",
            acc_id: accId,
            limit: filtersObj.hist_num,
            rec_type: filtersObj.hist_type,
            rec_status: filtersObj.hist_status
        };
        doAjaxGet(ajaxQueryUrl, dataObj, successCreateHistTbl);
    };

    function successUpdateHistTbl(responseO) {
    /**
    *   Add a new row in the History table (after an Email has been sent or a new Note or ToDo created).
    **/

        flash.dispMsg($formFlashEl, $form, 's', responseO.msg + '.');
        // Append new rec as first in  history table
        let $tbody = $histTblDiv.find("tbody");
        $tbody.prepend(formatHistTblRow(responseO.rec));
        // Now see if max number of allowed notes/emails has been exceeded, if so remove the last one
        let maxNum = $tbody.data("max_num");
        if (maxNum && $tbody.children().length > maxNum) {
            $tbody.children().last().remove();
        }
    };

    function errorFunc(msg) {
        // Errors displayed for 10 secs
        flash.dispMsg($formFlashEl, $form, 'e', msg, 10);
    };

    function enableSubmitBtns(enabled) {
        function _setSubmitBtn(on){
            $form.find("button[data-action='submit']").prop("disabled", !on);
            submitEnabled = on;
        }
        if (enabled !== submitEnabled) {
            _setSubmitBtn(enabled);
            // If disabling Submit btns, set a one-time click handler that Enables them again when any key is pressed
            if (!enabled) {
                $form.one("keyup", ".input", function(){ _setSubmitBtn(true); });
            }
        }
    }


    function processFormSubmit(reqdFunc) {
    /**
    *   Obtain data relating to a new Email, Note or ToDo and, if it validates OK, submit it to the server - then
    *   handle the response to update the History table or display returned error.
    **/

        function _errorFn(msg){
            errorFunc(msg);
            enableSubmitBtns(true);     // Enable the submit buttons (Save Note, Save ToDo, Send Email)
        }
        $form.removeClass("flash-success flash-danger");
        $formFlashEl.addClass("hide");
        let dataObj = {
            pub_repo_ind: pubOrRepoInd,
            func: reqdFunc,
            acc_id: accId
        };

        // If Send Email, then deduplicate email addresses before grabbing the input data
        if(reqdFunc === "send_email"){
            $.each(userEmailObj, function(k,emailObj){
                let $addrField = emailObj.$formAddr;
                $addrField.val(splitDedupJoinEmailString($addrField.val()));
            });
        }

        // Extract all form textual data (that with CLASS of "input") and add to dataObj
        $form.find(".input").each(function(ix, el){
            let $el = $(el);
            dataObj[$el.attr('name')] = $el.val();
            });
        // See if the pin checkbox is checked
        if ($form.find('input[name="pin"]').is(':checked')) {
            dataObj["status"] = "H";   // Set highlight status
        }
        // Validate & handle click
        switch (reqdFunc) {
            case 'save_note':
            case 'save_todo':
                if(dataObj.body === "") {
                    errorFunc("No message text entered.")
                    return;
                }
                enableSubmitBtns(false);    // Disable the submit buttons (Save Note, Save ToDo, Send Email)
                // Send request & when it is completed update the history panel.
                doAjaxPost(ajaxQueryUrl, dataObj, successUpdateHistTbl, _errorFn);
                break;

            case 'send_email':
                let errors = [];
                if(dataObj.to_addr === "") {
                    errors.push("Email address")
                }
                if(dataObj.subject === "") {
                    errors.push("Subject")
                }
                if(dataObj.body === "") {
                    errors.push("Message")
                }
                if (errors.length > 0) {
                    errorFunc(errors.join(" and ") + (errors.length === 1 ? " is" : " are") + " required.")
                    return;
                }
                enableSubmitBtns(false);    // Disable the submit buttons (Save Note, Save ToDo, Send Email)
                // Get list of Error ids where check-boxes ticked
                let errIds = []; // Array of error IDs
                $errTable.find("input:checkbox:checked").each(function(x,el){
                    errIds.push(el.value);
                });
                dataObj["err_ids"] = errIds;
                dataObj["api_key"] = apiKey;
                // Send request & when it is completed update the history panel & the error table.
                doAjaxPost(ajaxQueryUrl, dataObj, successUpdateHistTbl, _errorFn)
                    .done(function(){
                        // Unset any checked errors & set the previous (adjacent) column to "Yes<br><br>Error-ID value"
                        $errTable.find("input:checkbox:checked").each(function(){
                            $this = $(this);
                            $this.prop( "checked", false ).parent().prev().html("Yes<br>" + $this.val()).closest("tr").addClass("hili_grn");
                        });
                    });
                break;
        } // end-switch
    }; // end-processFormSubmit()
    
    function processHistBtn(eventTarget){
    /**
    *   Handle one of the Action buttons (Pin, Resolve, Clear, Delete) available for each entry in the history table.
    **/

        $histFlashEl.addClass("hide");

        const eTargetDataset = eventTarget.dataset;
        const newStatus = eTargetDataset.status;
        const dataObj = {
            func: "update_status",
            status: newStatus,
            rec_id: eTargetDataset.id
        };
        const $tr = $(eventTarget).closest("tr");   // The <tr> element that contains the pressed button
        // Send request & when it is completed update the history panel.
        doAjaxPost(ajaxQueryUrl, dataObj,
            // Success func
            function(responseO){
                // If ToDo & clearing the status (N:None) then set special class
                const newClass = (newStatus === "N" && $tr.data("type") === "T") ? "hili_todo" : statusCssClassMap[newStatus];
                $tr.removeClass().addClass(newClass);
            },
            // Failure func
            function(msg){
                // Errors displayed for 10 secs
                flash.dispMsg($histFlashEl, null, 'e', msg, 10);
            }
        );  // end-doAjaxPost

    }; // end-processHistBtn

    function populateUserEmailTextBox(){
    /**
    *   In the User email selection overlay - poplulate the 'Selected emails' textarea field with those email addresses
    *   that have been selected by checking the adjacent checkbox.
    **/
        // Add each checked Org-email to the array of email addresses
        let orgArr = [];
        $userEmailOverlay.find('input[name="org_email"]:checked').each(function(x,el){
            for(const email of el.value.split('; ')){
                orgArr.push(email);
            }
        });
        // Add each checked User-email to the array of email addresses
        let emailArr = [];
        $userEmailOverlay.find('input[name="user_email"]:checked').each(function(x,el){
            const email = el.value;
            // avoid duplicates
            if (! orgArr.includes(email)){
                emailArr.push(email);
            }
        });
        $userEmailOlayTextArea.val(orgArr.concat(emailArr).join("; "));
    };

    function splitEmailString(aString){
        // Return ARRAY of Strings (email addresses) which have been split
        // Note that if aString is "" (empty) then emailArr will be [''] - hence the need for this function
        // Only return array elements that are not empty
        return aString.split(splitRegex).filter((val) => val.length > 0);
    };

    function splitDedupJoinEmailString(aString){
        // Return String of Email addresses that have been de-duplicated & each separated by "; "
        var emailArr = splitEmailString(aString);
        if(emailArr.length){
            // Deduplicate array, then return joined string
            return [... new Set(emailArr)].join("; ");
        }
        return "";
    };

    function processEmailBtn(eventTarget){
        function _clearSelected(){
            // Clear all Email selection checkboxes and the associated 'Selected emails' textarea field
            $userEmailOverlay.find('input:checkbox:checked').prop("checked", false);
            $userEmailOlayTextArea.val("");
        }
    /**
    *   Execute functions for buttons in the User email selection Overlay.
    **/
        const eTargetDataset = eventTarget.dataset;
        let emails = [];
        switch(eTargetDataset.func) {
            case "show_user_emails":
                // Display User email selection modal overlay panel, and move focus to first input field
                // pass DOM element as parameter
                userSelectionModal = modalFocusTrap($userEmailOverlay[0]);
                // populate the panel To & CC fields from the Form fields
                $.each(userEmailObj, function(k,emailObj){
                    emailObj.$olayAddr.val(splitDedupJoinEmailString(emailObj.$formAddr.val()));
                });
                // DROP THROUGH
            case "clear_selected":
                // Clear all Email selection checkboxes and the associated 'Selected emails' textarea field
                _clearSelected();
                 break;
            case "select_all":
                $userEmailOverlay.find('input:checkbox:not(:checked)').prop("checked", true);
                populateUserEmailTextBox();
                break;
            case "set_checkboxes":
                //  Handle [all] & [none] buttons to change checkbox values
                let setOn = eventTarget.value === "1";    // Button value determines wither checkboxes are to be set ON or not
                $(eventTarget).closest("tbody").find("input:checkbox").prop("checked",setOn);
                populateUserEmailTextBox();
                break;
            case "add_to_addr":
                // Handle button to update the overlay's To or CC address boxes from selected values
                const emailObj = userEmailObj[eventTarget.value];
                const olaySelectedEmails = splitEmailString($userEmailOlayTextArea.val());
                if(olaySelectedEmails.length){
                    // Combine & deduplicate current To or CC emails with content of Selected emails text area
                    emails = [... new Set(olaySelectedEmails.concat(splitEmailString(emailObj.$olayAddr.val())))];
                    emailObj.$olayAddr.val(emails.join("; "));

                    // Clear all Email selection checkboxes and the associated 'Selected emails' textarea field
                    _clearSelected();
                }
                break;
            case "close_n_update_user_emails":
                // Update Form with contents of To & CC panel textareas
                $.each(userEmailObj, function(k, emailObj){
                    emailObj.$formAddr.val(splitDedupJoinEmailString(emailObj.$olayAddr.val()));
                });
                // DROP THROUGH ...
            case "close_cancel":
                userSelectionModal.closePanel();
                break;
        }
    }; // end-processEmailBtn


    /**
    *   Initialisation functionality
    **/

    // Handle all button clicks in the Contact (notes & emails) panel.
    $root.on("click", "button", function(event){
//console.log(event);
        event.stopPropagation();
        const eTargetDataset = event.target.dataset;
//console.log("handling above event. Dataset action: ", event.target.dataset.action);

        switch(eTargetDataset.action) {
            // NOT click or allowed keypress or a form submit button that was clicked
            case undefined:
                return;

            case "showhide":
                const showing = doShowHide($(event.target));
                // Process any auto-trigger that is indicated in the element data (in eTargetDataset)
                triggerClick(showing, eTargetDataset);
                break;
            // Email/Note/ToDo form submit buttons
            case "submit":
                // event.target should be like: <button ... data-func="function_name" type="submit">
                // event.target.dataset.func will return the data-func value e.g. "function_name"
                processFormSubmit(eTargetDataset.func);
                break;
            // History table submit buttons
            case "hist_func":
                processHistBtn(event.target);
                break;
            case "clear":
                // data elements on the button contain the target element to clear
                $(eTargetDataset.target).val("");
                enableSubmitBtns(true);
                break;
            case "clear_near":
                // data elements on the button contain the target element relative to parent to clear
                $(event.target).parent().find(eTargetDataset.target).first().val("");
                enableSubmitBtns(true);
                break;
            case "email_func":
                processEmailBtn(event.target);
                break;
            case "set_html":
                // data elements on the button contain the source & target to set if button pressed
                // Line-feed characters are replaced by <br>
                $(eTargetDataset.target).html($(eTargetDataset.source).val().replaceAll('\n', '<br>'));
                break;
//            case "setvalue":
//                // data elements on the button contain the target & text to set if button pressed
//                $(eTargetDataset.target).val(eTargetDataset.text);
//                break;
        }; // end-switch
    });


    // Set click handlers on history filter radio-buttons & checkboxes (that control what information is
    // displayed in the history table.
    $histFilters.on("click", "input", function(event){
        event.stopPropagation();
        //console.log(event);
        // Input names have form:  "filter_name-123", need to remove the '-123' suffix
        let filterName = event.target.name.split('-')[0];
        switch(filterName) {
            case "hist_num":
                filtersObj.hist_num = event.target.value;
                break;
            case "hist_type":
            case "hist_status":
                let filterString = "";
                // Create concatenated string of all checked checkbox values
                // Checkboxes are enclosed in a <fieldset> - which is the closest fieldset parent of the event.target
                $(event.target).closest("fieldset").find("input:checkbox:checked").each(function(){
                    filterString += this.value;
                });
                filtersObj[filterName] = filterString;
                break;
        }; // end-switch
        // Redisplay history table
        listNotesEmails();
    });  // end-$histFilters.on

    // Initial data load - set filtersObj object values from initially checked checkboxes
    $histFilters.find("input:checkbox:checked").each(function(){
        let filterName = this.name.split('-')[0];
        filtersObj[filterName] += this.value;
    });

    // Click handlers on User Email Overlay Checkboxes
    $userEmailOverlay.on("click", "input:checkbox", function(event){
        populateUserEmailTextBox();
    });

    // List recent notes & emails in History section
    listNotesEmails();

}; // end-initAndSetEmailNoteEventHandlers()
