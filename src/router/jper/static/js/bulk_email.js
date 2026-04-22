/*
 bulk_email.js - Code for Bulk email screen (bulk_email.html):
     - display publisher/repository accounts for selection
     - display a table of historic emails;
     - click handlers for email form
     - handle AJAX interactions with server to receive/send data

 ** THIS code DEPENDS on functions in `ajax_helpers.js` file.

 Author: Jisc
*/

function initAndSetEventHandlers(ajaxQueryUrl, accType) {
/*
*   Function that provides all functionality related to Bulk email GUI interface.
*
*   GENERAL RULE: The constants & variables declared below are accessed directly by functions -
*   i.e. they are NOT passed to functions as parameters.
*/
    const divIdStr = "#bulk";
    const $root = $(divIdStr);

    const $accountsFlashEl = $(divIdStr + '-target .flash');
    const $acRadioBtns = $(divIdStr + '-target_ac');
    const $accountsTbl = $(divIdStr + '-accounts_tbl');
    const $accountsToggleBtn = $(divIdStr + '-accounts_showhide');
    const $emailHistToggleBtn = $(divIdStr + '-hist_toggle');

    let $accountsTblBody = null;
    let accObjArr = [];    // Will store array of Account objects
    let allAccUserEmailObj = {};   // Will store All user emails corresponding to accounts

    // Email form variables
    const $form = $(divIdStr + '-form');
    const $formFlashEl = $(divIdStr + '-form .flash');      // Elements for displaying flash messages
    const $toBccAddrLi = $('#to_bcc_addr');
    const $ccBccAddrLi = $('#cc_bcc_addr');
    const $ccAddr = $('#cc_addr');
    // Object related to 2 sets of email address selection checkboxes for To(bcc) & CC(bcc).
    const emailAddrSelectionObj = {
        to_bcc: {stringVals: "", $parentLi: $toBccAddrLi, $adjacentLi: $ccBccAddrLi, mirrorName: 'cc_bcc'},
        cc_bcc: {stringVals: "", $parentLi: $ccBccAddrLi, $adjacentLi: $toBccAddrLi, mirrorName: 'to_bcc'}
    };

    // History Table variables
    const $histTblDiv = $(divIdStr + '-hist_tbl');
    const $histFilters = $(divIdStr + '-hist_filters');
    const $histFlashEl = $(divIdStr + '-hist .flash');
    // If All: get emails with ac_type of A or P or R; Pub: want ac_type of A or P; Repo: ac_type of A or R 
    const mapAcTypeToFilterType = {A: "APR", P: "AP", R: "AR"};
    // Initialise history-filters
    let filtersObj = {hist_num: 0, hist_type: "", hist_status: ""};
    $histFilters.find("input:checkbox:checked").each(function(){
        filtersObj[this.name] += this.value;
    });

    // Misc values
    const flash = new FlashMsg(null, 6);
    let submitEnabled = true;   // Submit btns are enabled
    const statusClassMap = {H: "hili", D: "deleted", N: "normal"};
    const acTypeTitleMap = {A: "Publisher & Repository", P: "Publisher", R: "Repository"};
    const acTypeToRoleMap = {A: "PR", P: "P", R: "R"};    // Map filter ac-type to Org-account-roles (aka acc type)
    const addrTypeMap = {C: "Org contacts", T: "Technical contacts", A: "Admin users", S: "Standard users", R: "Readonly users"};    // Map address type to description
    const splitRegex = /[;, \r\n]+/;       // Regex to split string of emails separated by semicolon, comma, space(s)
    const regexAdminStdReadOnly = /[ASR]/;      // Regex matches string that contains ANY of the User Type codes: A:Admin, S:Standard, R:Read-only

    function makeExpandingAddrBlock(title, itemArr, emailTypes = ""){
    /*
    *   Widget to create expanding accordion panel that lists either Organisations, or To (Bcc) or Cc (Bcc) email addr.
    */
        let block = `<div class="small-gap-after transparent xt-accordion pale x-hide"><span class="x-title">${title} &nbsp;<span class="smaller">x${itemArr.length}</span></span>
        <div class="title-accordion small-gap-vert" style="display:none">`;
        if(emailTypes){
            let typeArr = [];
            for(const c of emailTypes){
                typeArr.push(addrTypeMap[c]);
            }
            block += `<div class="strong small-gap-after">${typeArr.join(', ')}</div>`;
        };
        for(const v of itemArr){
            block += `<div>${v}</div>`;
        }
        block += '</div></div>';
        return block;
    }
    function makeExpandingBody(title, body){
    // Widget to create expanding accordion panel containing Email body text
        return `<div class="small-gap-after transparent xt-accordion pale x-show"><span class="x-title">${title}</span><div class="title-accordion narrow small-gap-vert">${body}</div></div>`;
    }
    function formatEmailHistoryTblRow(recO){
    /*
    *   Create a table Row containing a single bulk email. It has 4 columns: 1- Date, 2- Type of account email sent to,
    *   3- Email details (inc. Organisations it was sent to, To & CC addr, email Body), 4- Action buttons.
    */
        const accDesc = {A: "All", P: "Pub", R: "Repo"};
        let emailBlock = `</td><td>${accDesc[recO.ac_type]}</td><td class="small-disp">`;
        const snippet = '<div class="small-gap-after"><span class="bold-italic">';
        if (recO.orgs) {
            emailBlock += makeExpandingAddrBlock('Organisations', recO.orgs.split(', '));
        }
        emailBlock += makeExpandingAddrBlock('To (Bcc)', recO.bcc_to_addr.split(';'), recO.to_addr_types ?? "");
        if (recO.bcc_cc_addr) {
            emailBlock += makeExpandingAddrBlock('Cc (Bcc)', recO.bcc_cc_addr.split(';'), recO.cc_addr_types ?? "");
        }
        if (recO.cc_addr) {
            emailBlock += `${snippet}Cc:</span>&nbsp; ${recO.cc_addr}</div>`;
        }
        let bodyPart = recO.body.replaceAll('\n', '<br>');
        bodyPart = bodyPart.length > 350 ? makeExpandingBody('Body', bodyPart) : `<div>${bodyPart}</div>`;

        emailBlock += `${snippet}Subject:</span>&nbsp; ${recO.subject}<br><br>${bodyPart}</div`;

        // Construct Delete, Pin, Unpin buttons
        const btnSnippetA = `<button type="button" class="btn btn--3d value-btn `;
        const btnSnippetB = `" data-action="hist_func" data-id="${recO.id}"`;
        const btnGroup = `</td><td>${btnSnippetA}b_hili${btnSnippetB} title="Pin (highlight)" data-status="H">Pin</button>
            ${btnSnippetA}b_clear${btnSnippetB} title="Clear highlight or deletion" data-status="N">Clear</button>
            ${btnSnippetA}b_del${btnSnippetB} title="Delete item" data-status="D">Delete</button>`;
 
        const trClass = statusClassMap[recO.status] || 'normal';
        // line-feeds in the message body are replaced by <br>
        return `<tr class="${trClass}" data-type="${recO.ac_type}"><td class="no-wrap">` + recO.created.slice(0,10) + emailBlock + btnGroup + "</td></tr>" ;
    };

    function dispHistError(msg){
        flash.dispMsg($histFlashEl, null, 'e', msg, 10);
    }

    function getAndShowHistoricEmails() {
    /**
    *   Retrieve history Emails, for particular Org account types (P: Publisher, R: Repository (Institution), A: All (both P & R)
    *   and with particular bulk email status (N: Normal/Standard, H: Highlighted/Pinned, D: Deleted), up to specified
    *   limit (max number of records returned)
    **/

        function successCreateHistTbl(responseO) {
            // Create the history table
            let $histTbl = $("<table></table>");
            $histTbl.append(`<thead><th>Date</th><th>Type</th><th>Text</th>$<th>Action</th></thead>`);
            let $histBody = $(`<tbody data-max_num="${filtersObj.hist_num}"></tbody>`).appendTo($histTbl);

            $.each(responseO, function(i, recO){
                $histBody.append(formatEmailHistoryTblRow(recO));
                });
            $histTblDiv.empty().append($histTbl);
        };
        const dataObj = {
            func: "list_bulk_emails",
            limit: filtersObj.hist_num,
            ac_type: filtersObj.hist_type,
            rec_status: filtersObj.hist_status
        };
        // Returning so that the calling function can use `.done(func...)` to preform subsequent processing
        return doAjaxGet(ajaxQueryUrl, dataObj, successCreateHistTbl, dispHistError);
    };

    function successAddEmailToHistoryTable(responseO) {
    /**
    *   Add email to history table after a new bulk email has been successfully sent.
    **/
        flash.dispMsg($formFlashEl, $form, 's', responseO.msg + '.');
        // Append new rec as first in  history table
        const $tbody = $histTblDiv.find("tbody");
        $tbody.prepend(formatEmailHistoryTblRow(responseO.rec));
        // Now see if max number of allowed emails has been exceeded, if so remove the last one
        const maxNum = $tbody.data("max_num");
        if (maxNum && $tbody.children().length > maxNum) {
            $tbody.children().last().remove();
        }
        // Now we want to make sure the table is displayed.
        doShowHide($emailHistToggleBtn, false);
    };

    function formErrorFunc(msg) {
        // Errors displayed for 10 secs
        flash.dispMsg($formFlashEl, $form, 'e', msg, 10)
    };

    function enableSubmitBtns(enabled) {
        function _setSubmitBtn(on){
            $form.find("button[data-action='submit']").prop("disabled", !on);   // Remove disabled property
            submitEnabled = on;
        }
        if (enabled !== submitEnabled) {
            _setSubmitBtn(enabled);
            // If disabling Submit btns, set a one-time click handler that Enables them again when any key is pressed.
            if (!enabled) {
                $form.one("keyup", ".input", function(){ _setSubmitBtn(true); });
            }
        }
    };

    function splitDedupJoinEmailString(aString){
        // Return String of Email addresses that have been de-duplicated & each separated by "; "
        var emailArr = aString.split(splitRegex).filter((val) => val.length > 0);
        if(emailArr.length){
            // Deduplicate array, then return joined string
            return [... new Set(emailArr)].join("; ");
        }
        return "";
    };

    function processFormSubmit(reqdFunc) {
        function _errorFn(msg){
            formErrorFunc(msg);
            enableSubmitBtns(true);     // Enable the submit buttons (Send Email)
        }
        $form.removeClass("flash-success flash-danger");
        $formFlashEl.addClass("hide");
        let dataObj = {
            ac_type: accType,
            func: reqdFunc
        };
        // Remove duplicates etc. from CC emails & update displayed field
        $ccAddr.val(splitDedupJoinEmailString($ccAddr.val()));

        // Extract all form textual data and add to dataObj
        $form.find(".input").each(function(ix, el){
            dataObj[el.name] = el.value;
        });

        // Validate & handle click
        switch (reqdFunc) {
             case 'send_email':
                let errors = [];
                if(dataObj.to_bcc_addr === "") {
                    errors.push("To email address")
                }
                if(dataObj.subject === "") {
                    errors.push("Subject")
                }
                if(dataObj.body === "") {
                    errors.push("Message")
                }
                if (errors.length > 0) {
                    formErrorFunc(errors.join(" and ") + (errors.length === 1 ? " is" : " are") + " required.");
                    return;
                }
                const toBccStrVals = emailAddrSelectionObj.to_bcc.stringVals;
                const ccBccStrVals = emailAddrSelectionObj.cc_bcc.stringVals;

                dataObj.to_addr_types = toBccStrVals;
                dataObj.cc_addr_types = ccBccStrVals;
                // Array of objects for each selected org, containing Org ID and To(bcc) & CC(bcc) email addresses
                dataObj.ac_data = setSelectedAccDataArray(toBccStrVals, ccBccStrVals);
                delete dataObj.to_bcc_addr;     // We don't send the to_bcc_addr string, because all the addresses are in ac_data array.
                enableSubmitBtns(false);    // Disable the submit buttons (Save Note, Save ToDo, Send Email)
                // Send request & when it is completed update the history panel & the error table.
                doAjaxPost(ajaxQueryUrl, dataObj, successAddEmailToHistoryTable, _errorFn);
                break;
        } // end-switch
    }; // end-processFormSubmit()
    
    function processHistBtn(eventTarget){
    /*
    *   Process button press in Historic emails table action column - which causes change in email record status
    */
        $histFlashEl.addClass("hide");
        const eTargetDataset = eventTarget.dataset;
        const dataObj = {
            func: "update_status",
            status: eTargetDataset.status,
            rec_id: eTargetDataset.id
        };
        const $tr = $(eventTarget).closest("tr");   // The <tr> element that contains the pressed button
        // Send request & when it is completed update the history panel.
        doAjaxPost(ajaxQueryUrl, dataObj,
            // Success func
            function(responseO){
                // Need to sleep 0.3sec to allow database commit to complete before retrieving/redisplaying recs
                // sleep(300).then(getAndShowHistoricEmails());
                $tr.removeClass().addClass(statusClassMap[eTargetDataset.status]||'');
            }, dispHistError
        );  // end-doAjaxPost
    }; // end-processHistBtn

    function renderAcTable(acRecs){
    /*
    *   Display table of organisation accounts - either Publisher, Repository or All (both pub & repo) - from
    *   array of account records.
    */
        function _format_row(ix, recO){
            let snippetA = '';
            // If Publisher
            if (recO.type === "P"){
                snippetA = recO.pubAutotest ? 'Auto-test' : '';
            }
            // Repository Institution ac
            else{
                const flavourOrSw = recO.repoFlavour || recO.repoSw;
                if (flavourOrSw){
                    snippetA = flavourOrSw;
                }
            }
            const acTypeMap = {P: "Pub", R: "Repo"};
            return `<tr${recO.isOff ? ' class="acc-off"' : ''}><td>${acTypeMap[recO.type]}</td><td>${recO.orgName}</td><td>${recO.contact}</td>
                <td>${recO.techContacts.join('; ')}</td><td>${recO.isLive ? 'Live' : 'Test'}${recO.isOff ? '<span class="smaller"> (off)</span>' : ''}</td><td>${snippetA}</td>
                <td>${recO.status}</td><td><input type="checkbox" name="email" value="${ix}" aria-label="Send bulk mail to ${recO.orgName}" checked></td></tr>`;
        };
        // String holding Table HTML
        let tblHtml = `<table data-rwdtable-sortable data-sortable-col-zero class="content-table"><thead>
            <th class="persist essential" data-sort-default >Type</th>
            <th class="persist essential">Organization</th>
            <th class="optional">Contact email</th>
            <th class="optional">Technical contacts</th>
            <th class="persist essential">Live?</th>
            <th class="persist essential">Extra info</th>
            <th class="optional">Status</th>
            <th class="persist essential">Send</th>
        </thead><tbody>`;
        // Add <tr> rows - using $.each() because need Array index & Object value
        $.each(acRecs, (ix, recO) => {tblHtml += _format_row(ix, recO)});
        tblHtml += `</tbody></table>`;

        // sortableRwdtable() is a Jisc widget which is added Jquery by oa.ux.jisc-1.1.0.script-foot.js code.
        $accountsTbl.html(tblHtml).find('table').sortableRwdtable({idprefix: 'co-', persist: 'persist'});
        // Having reformatted the table, need to append ALL & NONE buttons to the last column (checkboxes) header
        $accountsTbl.find('th').last().append(`<br><button type="button" class="btn-small small-gap-before" data-action="set_ac_checkbox" value="1" title="Send bulk email to all organisations listed below (tick all checkboxes in the table)">All</button>
        <button type="button" class="btn-small small-gap-before" data-action="set_ac_checkbox" value="0" title="Deselect all organisations listed below (clear all checkboxes in the table)">None</button>`);
        $accountsTblBody = $accountsTbl.find('tbody');
        // If target table is currently hidden, then show it
        doShowHide($accountsToggleBtn, false);
    };

    function getAndListOrgAccs(){
    /**
    *   Retrieve array of Org Account summary details, for specified OrgAcc role codes ('P' or 'R' or 'PR').
    **/
        let dataObj = {
            func: "list_ac",
            ac_role: acTypeToRoleMap[accType]
        };
        // Returning so that the calling function can use `.done(func...)` to preform subsequent processing
        return doAjaxGet(ajaxQueryUrl, dataObj,
            // Success func
            function(responseA){
                accObjArr = responseA;  // Persist the returned array of ac objects
                renderAcTable(responseA);   // Create table of accounts
                updateFormEmailTextareaFields();    // Update Email form To & Tech CC fields
            },
            // Failure func
            function(msg){
                accObjArr = [];
                flash.dispMsg($accountsFlashEl, null, 'e', msg, 10);
            }
        );  // end-doAjaxGet
    }; // end-getAndListOrgAccs

    function getUserEmailsForOrgAccs(){
    /**
    *   Retrieve Object containing USER email addresses for organisations with specified OrgAcc role codes ('P' or 'R' or 'PR').
    **/
        let dataObj = {
            func: "get_user_email_addrs",
            ac_role: acTypeToRoleMap[accType]
        };
        // Returning so that the calling function can use `.done(func...)` to preform subsequent processing
        return doAjaxGet(ajaxQueryUrl, dataObj,
            // Success func
            function(responseO){
                allAccUserEmailObj = responseO;  // Persist the returned Object of OrgAcc User Email objects
            },
            // Failure func
            function(msg){
                allAccUserEmailObj = {};
                flash.dispMsg($accountsFlashEl, null, 'e', msg, 10);
            }
        );  // end-doAjaxGet
    }; // end-getUserEmailsForOrgAccs


    function changeCheckboxes($checkboxContainer, onOff){
        // selector string for selecting checkboxes to set On/Off
        const setCheckboxSelector = {true: 'input:checkbox:not(:checked)', false: 'input:checkbox:checked'};
        const setOn = onOff === "1";
        $checkboxContainer.find(setCheckboxSelector[setOn]).prop("checked", setOn);
    };

    function setSelectedAccDataArray(toBccStrVals, ccBccStrVals){
        /*
        Return an Array of objects - one for each selected Organisation account - containing:
        [
            {
                id: account-ID,
                to: [array of selected To (bcc) emails],
                cc: [array of selected CC (bcc) emails];
            },
            ...
        ]
        */
        let retArr = [];
        $accountsTblBody.find('input:checkbox:checked').each(function() {
            const ix = Number(this.value);
            const accObj = accObjArr[ix];

            let toAddr = [];
            let ccAddr = [];
            if(toBccStrVals.length){
                addEmailsOfSelectedTypesToAddrArr(accObj, toBccStrVals, toAddr);
                // Remove duplicates
                toAddr = [... new Set(toAddr)];
            }
            if(ccBccStrVals.length){
                addEmailsOfSelectedTypesToAddrArr(accObj, ccBccStrVals, ccAddr);
                // Remove duplicates
                ccAddr = [... new Set(ccAddr)];
            }
            const retObj = {
                id: accObj.id,
                to: toAddr,
                cc: ccAddr
            };
            retArr.push(retObj);
        });
        return retArr;

    };

    function addEmailsOfSelectedTypesToAddrArr(accObj, stringVal, emailArr){
    /**
    *   Add emails of types determined by `stringVal` to `emailArr`
    *   :param accObj: Object containing summary details of a selected Organisation, inclusing Contact & Tech contact email addresses
    *   :param stringVal: String containing any of these chars: C, T, A, S, R indicating the required types of email address
    *   :param emailArr: Array to add email addresses to.
    **/
        let userEmailList = null;
        // Org Contact emails required
        if(stringVal.includes("C")) {
            emailArr.push(accObj.contact);
        }
        // Org Technical Contact emails required
        if(stringVal.includes("T")) {
            emailArr.push(...accObj.techContacts);
        }
        // For User types Admin, Standard & Readonly

        // if stringVal contains any of Admin, Std or Readonly chars
        if(regexAdminStdReadOnly.test(stringVal)){
            const accUserEmailObj = allAccUserEmailObj[accObj.id];
            // In rare cases where an Org account has no users (e.g. all users have been deleted) then allAccUserEmailObj will not have an entry for that accObj.id
            if (accUserEmailObj !== undefined) {
                for(const userRole of ["A", "S", "R"]){
                    // If stringVal contains one of user roles A, S or R; and Acc User Email Object has emails of that role type
                    if(stringVal.includes(userRole) && Object.hasOwn(accUserEmailObj, userRole)){
                        emailArr.push(...accUserEmailObj[userRole]);    // Add emails to emailArr
                    }
                }
            }
        }
        return emailArr;
    }

    function setSelectedAcEmailsObj() {
        /*
        Return an object containing 2 arrays:
            {
                toBcc: [array of email addresses],
                ccBcc: [array of email addresses]
            }
        for the selected (CHECKED) accounts.

        This uses 3 inputs:
            * emailAddrSelectionObj from which the currently selected Selected Email types string is obtained
            * accObjArr - which stores summary details of the currently listed Org Accounts
            * allAccUserEmailObj - which stores user emails for each account
        */

        let toBccArr = [];
        let ccBccArr = [];
        const toBccStrVals = emailAddrSelectionObj.to_bcc.stringVals;
        const ccBccStrVals = emailAddrSelectionObj.cc_bcc.stringVals;
        // Some email types are selected
        if(toBccStrVals.length || ccBccStrVals.length){
            $accountsTblBody.find('input:checkbox:checked').each(function() {
                // The value of the checkbox is the index to the account object array
                const ix = Number(this.value);
                accObj = accObjArr[ix];
                if(toBccStrVals.length){
                    addEmailsOfSelectedTypesToAddrArr(accObj, toBccStrVals, toBccArr);
                }
                if(ccBccStrVals.length){
                    addEmailsOfSelectedTypesToAddrArr(accObj, ccBccStrVals, ccBccArr);
                }
            });
            // Remove duplicates
            if(toBccStrVals.length){
                toBccArr = [... new Set(toBccArr)];
            }
            if(ccBccStrVals.length){
                ccBccArr = [... new Set(ccBccArr)];
            }
        }
        return {toBcc: toBccArr, ccBcc: ccBccArr};
    };

    function setEmailAddrObjStringVals(emailAddrObj){
    /**
    *   Set stringVals attribute on emailAddrObj based on settings of Email selection checkboxes in
    *   To (bcc) / CC (bcc) fields.
    **/
        let checkedString = '';
        emailAddrObj.$parentLi.find("input:checkbox:checked").each(function(){
                    checkedString += this.value;
        });
        emailAddrObj.stringVals = checkedString;
    }

    function processEmailTypeSelection(changedCheckbox){
    /**
    *   When an Email type checkbox value changes, modify the selected emails.
    **/
        const targetEmailAddrObj = emailAddrSelectionObj[changedCheckbox.name];
        setEmailAddrObjStringVals(targetEmailAddrObj);

        // If same checkbox in alternative adjacent email selection group is Checked, then uncheck it
        const $mirroredCheckbox = targetEmailAddrObj.$adjacentLi.find(`input:checkbox:checked[value=${changedCheckbox.value}]`);
        if($mirroredCheckbox.length){
            $mirroredCheckbox.prop("checked", false);
            setEmailAddrObjStringVals(emailAddrSelectionObj[targetEmailAddrObj.mirrorName]);
        }
    };

    function updateFormEmailTextareaFields(){
    /**
    *   Update the Email address TextArea fields
    **/
        selectedEmailsObj = setSelectedAcEmailsObj();
        $toBccAddrLi.find("textarea").val(selectedEmailsObj.toBcc.join('; '));
        $ccBccAddrLi.find("textarea").val(selectedEmailsObj.ccBcc.join('; '));
    };

    // Handle BUTTON clicks
    $root.on("click", "button", function(event){
        event.stopPropagation();
        const eventTarget = event.target;
        const eTargetDataset = eventTarget.dataset;
 
        //console.log("Handling event.",event ,"\nDataset action: ", event.target.dataset.action);

        switch(eTargetDataset.action) {
            // NOT click or allowed keypress or a form submit button that was clicked
            case undefined:
                return;

            case "showhide":
                const showing = doShowHide($(eventTarget));
                // Process any auto-trigger that is indicated in the element data (in eTargetDataset)
                triggerClick(showing, eTargetDataset);
                break;

            // Set all account checkboxes either On or Off
            case "set_ac_checkbox":
                changeCheckboxes($accountsTblBody, eventTarget.value);    // Change the checkbox values
                updateFormEmailTextareaFields();    // Update the displayed email addresses in the Email form
                break;

            case "set_addr_checkboxes":
                let targetEmailAddrObj = emailAddrSelectionObj[eventTarget.name];
                //  Handle [all] & [none] buttons to change checkbox values
                changeCheckboxes(targetEmailAddrObj.$parentLi, eventTarget.value);    // Change the checkbox values
                setEmailAddrObjStringVals(targetEmailAddrObj);

                // If setting all checkboxes ON, then need to clear all the checkboxes in mirrored address box
                if(eventTarget.value === '1'){
                    targetEmailAddrObj = emailAddrSelectionObj[targetEmailAddrObj.mirrorName];
                    changeCheckboxes(targetEmailAddrObj.$parentLi, '0');
                    setEmailAddrObjStringVals(targetEmailAddrObj);
                }
                updateFormEmailTextareaFields();
                break;

            // Email form submit buttons
            case "submit":
                // event.target should be like: <button ... data-func="function_name" type="submit">
                // event.target.dataset.func will return the data-func value e.g. "function_name"
                processFormSubmit(eTargetDataset.func);
                break;

            // History table submit buttons
            case "hist_func":
                processHistBtn(eventTarget);
                break;

            case "clear":
                // data elements on the button contain the target element to clear
                $(eTargetDataset.target).val("");
                enableSubmitBtns(true);
                break;
//            case "clear_near":
//                // data elements on the button contain the target element relative to parent to clear
//                $(event.target).parent().find(eTargetDataset.target).first().val("");
//                enableSubmitBtns(true);
//                break;
           case "set_html":
                // data elements on the button contain the source & target to set if button pressed
                // Line-feed characters are replaced by <br>
                $(eTargetDataset.target).html($(eTargetDataset.source).val().replace(/\n/g, '<br>'));
               break;
//            case "setvalue":
//                // data elements on the button contain the target & text to set if button pressed
//                $(eTargetDataset.target).val(eTargetDataset.text);
//                break;
        }; // end-switch
    });

    // Set click handlers on filter radio-buttons & checkboxes
    $histFilters.on("click", "input", function(event){
        event.stopPropagation();
//console.log(event);
        switch(event.target.name) {
            case "hist_num":
                filtersObj.hist_num = event.target.value;
                break;
            case "hist_type":
                // Create concatenated string of all checked checkbox values
                filtersObj.hist_type = "";
                // Checkboxes are enclosed in a <fieldset> - which is the parent of the event.target
                $(event.target).parent().find("input:checkbox:checked").each(function(){
                    filtersObj.hist_type += this.value;
                });
                break;
            case "hist_status":
                // Create concatenated string of all checked checkbox values
                filtersObj.hist_status = "";
                // Checkboxes are enclosed in a <fieldset> - which is the parent of the event.target
                $(event.target).parent().find("input:checkbox:checked").each(function(){
                   filtersObj.hist_status += this.value;
                });
                break;
        }; // end-switch
        // Redisplay history table
        getAndShowHistoricEmails();
    });  // end-$histFilters.on

    // Handler for Including particular types of emails by clicking checkboxes
    $form.on("change", "input:checkbox", function(event){
        processEmailTypeSelection(event.target);
        updateFormEmailTextareaFields();
    });
    
    // Click handler for Organisation Account table email checkboxes
    $accountsTbl.on("change", 'input[name="email"]', function(e){
        updateFormEmailTextareaFields();
    });

    function handleOrgAccTypeChange(){
    /**
    *   Retrieve & display list of accounts when account selection radio buttons change.
    **/
        // accType: Char with one of these values: 'A' - all, 'P' - publisher, 'R' - repository
        const accTypes = mapAcTypeToFilterType[accType];
        // Turn History Filter account-type checkboxes on or off depending on Organisation Account type being handled
        $histFilters.find("[name='hist_type']").each(function(){
            const chkBoxAllowed = accTypes.includes(this.value);
            this.checked = chkBoxAllowed;
            this.disabled = !chkBoxAllowed;
        });

        // Update title text.
        $("span.bulk_title").text(acTypeTitleMap[accType]);

        filtersObj.hist_type = accTypes;

        // Clear Email address boxes associated with To(bcc) & CC(bcc) textarea inputs
        changeCheckboxes($toBccAddrLi, '0');    // Set checkboxes off
        changeCheckboxes($ccBccAddrLi, '0');    // Set checkboxes off
        emailAddrSelectionObj.to_bcc.stringVals = "";
        emailAddrSelectionObj.cc_bcc.stringVals = "";
        updateFormEmailTextareaFields();

        // Sequentially: Get array of Org Accounts of selected type
        // Called in then(...) to make server requests sequentially to avoid overloading server (otherwise dev server crashes).
        getAndListOrgAccs().then(
            function(){getUserEmailsForOrgAccs().then(
                function(){getAndShowHistoricEmails()}
            )}
        );
    };

    // When change is made to the required account types
    $acRadioBtns.on("click", "input", function(event){
        event.stopPropagation();
// console.log(event);
        accType = event.target.value;    // Set global variable
        handleOrgAccTypeChange();
    });  // end-$acRadioBtns.on

    // Initial data load
    handleOrgAccTypeChange();

}; // end-initAndSetEventHandlers()
