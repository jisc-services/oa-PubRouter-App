/*
 content_mgt.js - Code for Content Management page to:
     - Retrieve content-type data for populating select box of content-types (ultimately from cms_ctl db table)
     - Retrieve content-type control record (ultimately from cms_ctl db table) for defining Content Mgt
       data-entry form which is dynamically constructed once the required content-type has been selected
     - Retrieve existing content records of selected content-type (ultimately from cms_html db table) for
       display/selection
     - Dynamically constructing page elements, such as:
        - Existing record table
        - Content entry form
     - Handle various GUI functions such as Preview, Insert (save) new content record, Update existing content record,
       Delete content record
     * All these features are achieved using AJAX interactions with the /admin/content_ajax endpoint (see
       jper\views\admin.py, jper\models\admin.py, jper\forms\admin.py)

 ** THIS code DEPENDS on functions in `ajax_helpers.js` file.

 *** WARNING *** - This functionality currently allows the input of potentially dangerous HTML or Javascript [JS] code.
                   This has been regarded as acceptable because the functions are only used by GUI screens available
                   to a limited number of trustworthy YOUR-ORG administrators.  This defect could be addressed within this
                   library by the introduction of an HTML/JS checking/filtering function (which still allows some HTML).
                   Alternatively the validation/filtering could be performed at a higher level before storing entered
                   data in the database.

Author: Jisc
*/

function initAndSetCmsEventHandlers(ajaxQueryUrl, $root, $selectContentPanel, $viewContentPanel, $editContentPanel, $previewPane) {
/*
    :param $root: jQuery obj - Outer container
    :param $selectCtl: jQuery obj - select dropdown for content type
    :param $viewContentPanel: jQuery obj - View Content DIV
    :param $editContentPanel: jQuery obj - Edit Content DIV
    :param $previewPane: jQuery obj - Preview Pane DIV
*/
    let activeContentCtlObj = null;
    let activeContentType = null;
    let currentContentArray = [];
    let activeContentObj = null;
    const $selectCtl = $selectContentPanel.find("select");
    const $viewFilters = $viewContentPanel.find("#filters");
    let filtersObj = {status: ""};
    const $editContentForm = $editContentPanel.children(".form").first();
    const $editContentH3Span = $editContentPanel.find("h2 span");
    const $editContentSaveBtn = $editContentForm.find("#save_btn");
    const $editContentSaveNote = $editContentForm.find("#save_note");
    const $viewContentTbody = $viewContentPanel.find("table tbody");
    const $flashEl = $root.find(".flash");
    const flash = new FlashMsg($flashEl, 4);
    let lastWindowY = 0;
    let editContentModal = null;

    function buildEditPanel(){
        /*
        *   Edit panel using activeContentCtlObj content
        */
        $editContentH3Span.last().html(activeContentCtlObj.title + " record");
        // Build edit form
        // Multi-entry forms always have a `sort-value` field; other forms do not.
        let inputHTML = activeContentCtlObj.multi ? `<li><label class="form__label" for="sort_value">Sort value</label><input class="form__item" id="sort_value" maxlength="40" minlength="1" name="sort_value" placeholder="Value to sort on (plain text, 40 chars max)" title="Value to sort on (plain text, 40 chars max)" type="text" value=""></li>` : "";
        for (const obj of activeContentCtlObj.fields) {
             const field = obj.field;
             inputHTML += `<li><label class="form__label" for="${field}">${obj.label}</label><textarea class="input form__item wide-text" id="${field}" name="${field}" rows="${obj.rows ?? 2}" placeholder="${obj.placeholder}" title="${obj.placeholder}"></textarea></li>`;
        }
        // Add edit fields at beginning of <form><ul>
        $editContentForm.find("ul").first().html(inputHTML);
    };

    function populateEditForm(fieldsObj){
        // Populate variable fields
        $editContentForm.find("input, textarea").each(function(){
            const $el = $(this);
            $el.val(fieldsObj[$el.attr("id")]);
        });
    };

    function fillBlankInputsWithSampleText(){
        for (const obj of activeContentCtlObj.fields) {
            const $input = $editContentForm.find(`#${obj.field}`);
            // If Input value is empty Then set it to sample value (if provided) otherwise ""
            if($input.val() === "") {
                $input.val(obj.sample ?? "");
            }
        }
    };

    function clearEditForm(){
        $editContentForm.find("input, textarea").each(function(){
            $(this).val("");
        });
    };

    function buildPreview(fieldObj){
        let template = activeContentCtlObj.template;
        $.each(fieldObj, (k, v) => template = template.replace(`{${k}}`, v));
        let $wrapper = $(activeContentCtlObj.preview_wrapper);
        $wrapper.find(".preview").append(template);
        return $wrapper.html();
    };

    function displayExistingContent(contentArray){
        /*
        *   Content table
        */
        currentContentArray = contentArray;
        const statusClassMap = {L: "live", N: "", D: "deleted", S: "superseded"};
        const statusMap = {L: "Live", N: "Draft", D: "Deleted", S: "Superseded"};
        function statusClass(status){
            return `class="${statusClassMap[status] ?? ""}"`;
        };
        function dispStatus(status){
            return statusMap[status] ?? "Draft";
        };

        // Build content display table
        let tbodyHTML = "";
        let numberLive = 0;
        contentArray.forEach(
            (obj, ix) => {
                const btnPrefix = '<button type="button" class="btn btn--3d ';
                const btnSuffix = `" data-action="run_func" data-value="${ix}"`;
                const btnActionSnippet = `${btnPrefix}panel-btn${btnSuffix}`;
                const btnValueSnippet = `${btnPrefix}value-btn${btnSuffix}`;
                const draftBtn = `${btnValueSnippet} title="Make draft" data-func="make_new">Draft</button>`;
                const deleteBtn = `${btnValueSnippet} title="Delete entry" data-func="delete">Delete</button>`;
                const status = obj.status;
                let btnGroup;      // Action buttons HTML
                // If status is Live or New, then show <Edit> & (<Live> or <Draft>) & <Delete> buttons
                if("NL".includes(status)){
                    btnGroup = `${btnActionSnippet} title="Edit entry" data-func="edit">Edit</button>${btnActionSnippet} title="Edit a copy" data-func="edit_copy">Copy</button>`;
                    // If new, then show <live> button
                    if(status === "N") {
                        btnGroup += `${btnValueSnippet} title="Make live" data-func="make_live">Live</button>`;
                    } else {    // Live - show <Draft> button
                        btnGroup += draftBtn;
                        numberLive += 1;
                    }
                    btnGroup += deleteBtn;
                } else if(status === "S") {     // Superseded status - show <Draft> and <Delete> buttons
                    btnGroup = draftBtn + deleteBtn;
                }
                else {  // Deleted status - show <Draft> button
                    btnGroup = draftBtn;
                }
                tbodyHTML += `<tr data-id="${obj.id}" ${statusClass(status)}><td>${obj.fields.sort_value}</td><td>${buildPreview(obj.fields)}</td><td class="no-decoration">${dispStatus(status)}</td><td class="no-decoration">${btnGroup}</td></tr>`;
            }
        );
        $viewContentTbody.empty().append(tbodyHTML);
        // Non-multi entry CMS type, but more than one record is Live - then show warning (that doesn't automatically disappear)
        if (! activeContentCtlObj.multi && numberLive > 1){
            flash.msg($viewContentPanel, 'i', `Only a single entry should be Live, but currently ${numberLive} entries are Live.`, 0);
        }
    };

    function getExistingContentAndDisplay(){
        doAjaxGet(ajaxQueryUrl,
                 {func: "list_content", cms_type: activeContentType, status: filtersObj.status},
                 displayExistingContent);
    };

    function processContentTypeSelection(contentType, briefDesc) {
        activeContentType = contentType;
        // Initialise filter checkboxes
        filtersObj.status = "NL";   // Initially, we want Draft/New & Live to be set to 'checked'
        $viewFilters.find("input").each(function(){
            let $inp = $(this);
            $inp.prop('checked', filtersObj.status.includes($inp.val()));
        });

        let $descDiv = $root.find(".full_desc");    // For display of long description
        $descDiv.empty();
        let $linkDiv = $root.find(".page_link");    // For display of link to relevant page (in multiple places)
        $linkDiv.empty();
        $viewContentTbody.empty();
        // If "Choose one...." has been selected, then contentType will be empty - so nothing to do
        if(contentType === ""){
            $viewContentPanel.children("h2").first().html("Existing content");
            activeContentCtlObj = null;
            return;
        }
        // Now want to retrieve entire contentCtl record with ID `val` - prepare scaffolding
        doAjaxGet(
            ajaxQueryUrl,
            {func: "get_content_ctl", cms_type: activeContentType},
            function(contentCtlObj){
                activeContentCtlObj = contentCtlObj;
                buildEditPanel();
                // Show description
                $descDiv.html(activeContentCtlObj.full_desc);
                // Set title on current content panel
                $viewContentPanel.children("h2").first().html("Existing " + activeContentCtlObj.title  + " records");
                // Show link to relevant web page (in 2 places)
                $linkDiv.html(`<a target="_blank" href="${activeContentCtlObj.page_link}">Page displaying ${activeContentCtlObj.title} content</a><span class="open-new"></span>.`)
                getExistingContentAndDisplay();
                }
        );
   };

    function populateSelectBox($selectCtl){
        doAjaxGet(ajaxQueryUrl, {"func": "list_cms_types"}, function(responseData){
            // responseData is an array of arrays: [[value, description], ...]
            for (const valDescArr of responseData) {
                $selectCtl.append(`<option value="${valDescArr[0]}">${valDescArr[1]}</option>`);
            }
        });
    };

    function extractFormData(){
        dataObj = {}
        $editContentForm.find("input, textarea").each(function(){
            let $el = $(this);
            dataObj[$el.attr("id")] = $el.val();
        });
        return dataObj;
    }


    function updateStatus(recordObj, newStatus){
        $flashEl.addClass("hide");

        // If no change to status, do nothing
        if (newStatus == recordObj.status) {
            return;
        }
        let dataObj = {
            func: "update_status",
            cms_type: activeContentType,
            id: recordObj.id,
            status: newStatus
        }
        // Send request & when it is completed update the existing content panel.
        doAjaxPost(ajaxQueryUrl, dataObj, function(responseO){
            flash.msg($viewContentPanel, 's', responseO.msg + '.');
            getExistingContentAndDisplay();
            });

    };


    function runButtonFunction(funcName, value){
        switch(funcName) {
            case "add_new":
            case "edit_copy":
                lastWindowY = window.scrollY;
                if(activeContentCtlObj === null){
                    flash.msg(null, 'e', "A content type must be selected before you can add a new one.");
                    return;
                }
                $editContentH3Span.first().html("New");
                $editContentSaveBtn.attr("title", "Save new draft record").html("Save new draft");
                $editContentSaveNote.hide();
                activeContentObj = null;
                if(funcName === "add_new") {
                    clearEditForm();
                }
                else {
                    populateEditForm(currentContentArray[value].fields);
                }
                $previewPane.html(buildPreview(extractFormData()));
                document.body.scrollTop = document.documentElement.scrollTop = 0;
                // Display Edit content modal overlay panel, and move focus to first input field
                // pass DOM element as parameter
                editContentModal = modalFocusTrap($editContentPanel[0], 2);
                break;

            case "edit":
                lastWindowY = window.scrollY;
                $editContentH3Span.first().html("Edit");
                $editContentSaveBtn.attr("title", "Update record").html("Update");
                $editContentSaveNote.show();
                activeContentObj = currentContentArray[value];
                populateEditForm(activeContentObj.fields);
                $previewPane.html(buildPreview(extractFormData()));
                document.body.scrollTop = document.documentElement.scrollTop = 0;
                // Display Edit content modal overlay panel, and move focus to first input field
                // pass DOM element as parameter
                editContentModal = modalFocusTrap($editContentPanel[0], 2);
                break;

            case "fillblanks":
                fillBlankInputsWithSampleText();
                // DROP THROUGH to "preview"
            case "preview":
                $previewPane.html(buildPreview(extractFormData()));
                break;

            case "close_edit":
                editContentModal.closePanel();
                document.body.scrollTop = document.documentElement.scrollTop = lastWindowY;
                break;

            case "make_live":
                updateStatus(currentContentArray[value], "L")
                break;
            case "make_new":
                updateStatus(currentContentArray[value], "N")
                break;
            case "delete":
                updateStatus(currentContentArray[value], "D")
                break;
        }
    };


    function processSubmit(reqdFunc) {
        $editContentForm.removeClass("flash-success flash-info flash-danger");
        $flashEl.addClass("hide");
        let dataObj = {cms_type: activeContentType};    // Initialize with cms_type

        // Perform required function
        switch (reqdFunc) {
            case 'save_content':
                let inputData = extractFormData();
                // Make sure that no field is empty
                let emptyField = false;
                $.each(inputData, (k, v) => {if (v.length === 0){ emptyField = true; }});
                if(emptyField){
                    flash.msg($editContentForm, 'e', 'You must enter data into all fields.');
                    return;
                }
                dataObj["fields"] = inputData;
                // If adding new
                if (activeContentObj === null){
                    dataObj["func"] = "insert_content";
                    dataObj["status"] = "N";    // Draft/New
                }
                else{
                    // See what has changed
                    let contentChanged = false;
                    $.each(dataObj.fields, (k, v) => {if (v !== activeContentObj.fields[k]){contentChanged = true}});
                    if (!contentChanged){
                        flash.msg($editContentForm, 'i', 'No changes to save.');
                        return;
                    }
                    dataObj["func"] = "update_content";
                    dataObj["id"] = activeContentObj.id;
                    dataObj["status"] = activeContentObj.status;
                }
                // Non-multi entry CMS type have no sort_value, but one is expected by server
                if (! activeContentCtlObj.multi){
                    dataObj.fields["sort_value"] = "";
                }

                // Send request & when it has completed update the existing content panel.
                doAjaxPost(ajaxQueryUrl, dataObj, function(responseO){
                    // Success msg is shown in several places for 4 secs
                    flash.msg($editContentForm, 's', responseO.msg + '.');
                    // Edit panel is hidden after 1.5 seconds
                    sleep(1500).then(() => editContentModal.closePanel());
                    getExistingContentAndDisplay();
                    document.body.scrollTop = document.documentElement.scrollTop = lastWindowY;
                    });
                break;

            case 'clear_cache':
                // Send request
                doAjaxPost(ajaxQueryUrl, {func: "clear_cache"}, function(responseO){
                    flash.msg($editContentForm, 's', responseO.msg + '.');
                    });
                break;
        } // end-switch
    }; // end-processSubmit()

    function setRootBtnClickHandlers(){
        $root.on("click", "button", function(event){
    //console.log(event);
            event.stopPropagation();
            const targetData = event.target.dataset;
    //console.log("handling above event. Dataset action: ", event.target.dataset.action);
            switch(targetData.action) {
                // NOT click or allowed keypress or a form submit button that was clicked
                case undefined:
                    return;

                // Form submit buttons
                case "submit":
                    // event.target should be like: <button ... data-func="function_name" type="submit">
                    // event.target.dataset.func will return the data-func value e.g. "function_name"
                    processSubmit(targetData.func);
                    break;
                // Run function
                case "run_func":
                    runButtonFunction(targetData.func, targetData.value);
                    break;
                case "showhide":
                    doShowHide($(event.target));
                    break;
                case "setvalue":
                    // data elements on the button contain the target & text to set if button pressed
                    $(targetData.target).val(targetData.text);
                    break;
            }; // end-switch
        });
    };

    function setFilterSelectHandlers(){
        // Set click handlers on filter radio-buttons & checkboxes
        $viewFilters.on("click", "input", function(event){
            event.stopPropagation();

            if(activeContentCtlObj === null) return;

            switch(event.target.name) {
                case "status":
                    filtersObj.status = "";
                    // Create concatenated string of all checked checkbox values
                    // Checkboxes are enclosed in a <fieldset> - which is the parent of the event.target
                    $(event.target).parent().find("input:checkbox:checked").each(function(){
                        filtersObj.status += this.value;
                    });
                    break;
            }; // end-switch
            // Redisplay content table
            getExistingContentAndDisplay();
        });  // end-$histFilters.on
    };


    // Initialise select box - get the options to display
    populateSelectBox($selectCtl);
    // Set Select Change handler to process a new Content when a new selection is made
    selectChangeHandler($selectCtl, processContentTypeSelection);
    // Set click handlers on buttons 
    setRootBtnClickHandlers();
    // Handlers on filter checkboxes / radio buttons
    setFilterSelectHandlers();
}; // end-setEventHandlers()

