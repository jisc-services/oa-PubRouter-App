/********************************************
* Javascript for use by Repository User page
*
* IMPORTANT: The following 3 variables must be set in the HTML file (before this script is loaded):
*   - packaging_formats
*   - search_identifiers_url
*   - org_acc_api_key
*********************************************/

function getSelectedVal($jquerySelect) {
    /*
     * @param $jquerySelect: HTML DOM select object as jQuery
     *
     * @return: Selected value or undefined
     */
    // Simple helper function to get a selected value
    return $jquerySelect.find(":selected").val();
}

function setSelectOptions($jquerySelect, optionVals, selectedLabel) {
    /* Helper function to change the options of a select element
     * @param $jquerySelect: HTML DOM select object as jQuery
     * @param optionVals: array of new option values (each being a 2 element array: [<option-value>, <option-description>])
     * @param selectedLabel: The label of the new selected option
     */
    $jquerySelect.empty();
    for (const optVal of optionVals) {
        const optionValue = optVal[0];
        const optionLabel = optVal[1];
        let option = document.createElement("option");
        option.innerHTML = optionLabel;
        option.setAttribute("value", optionValue);
        if(optionLabel == selectedLabel) {
            option.setAttribute("selected", "");
        };
        $jquerySelect.append(option);
    };
}

function showHideParentAndDisableSelf(shouldHide, $self, $parent) {
    /* Show hide the container of an object and disable it if shouldHide true. Otherwise, make it visible.
     *
     * @param shouldHide: Should we hide these DOM objects? (bool)
     *
     * @param $self: DOM object to be disabled (generally an input)
     *
     * @param $parent: Container of the object (should hide anything to do with $self
     */
    shouldHide ? $parent.hide() : $parent.show();
    $self.prop("disabled", shouldHide);
}

function changePackagingDependingOnXmlFormat(xmlFormat, $packagingFormat) {
    /* Changes the packaging value options dependent on the xml format
     *
     * @param $xmlFormat: xml format object as jquery
     * @param $packagingFormat: packaging format object as jquery
     */

    const newPackaging = packaging_formats[xmlFormat];
    // get the human readable selected packaging format (the [1] value)
    const newSelectedPackaging = newPackaging[0][1];
    setSelectOptions($packagingFormat.find("#packaging"), newPackaging, newSelectedPackaging);
    // get the span which is an immediate child of the packaging format object
    $packagingFormat.children("span").first().text(newSelectedPackaging);
}

function showHideReviewQueueDependingOnXmlFormat(xmlFormat, $targetQueue) {
    /* Show hides $targetQueue dependent on xmlFormat's value. Namely, hide unless it's an eprints repository.
     *
     * @param $xmlFormat: HTML DOM xml format select field
     * @param $targetQueue: HTML DOM review queue input field as jQuery
     */
    // If our xml format is not some form of eprints, hide the review queue . Disable also for good measure.
    const isNotEprints = xmlFormat.indexOf("eprints") === -1;
    showHideParentAndDisableSelf(isNotEprints, $targetQueue, $targetQueue.parent().parent());
}

/* Create an autocomplete widget for identifiers
 *
 * @param selector: jQuery/DOM selector (like .autocomplete or #some_id)
 * @param type: Type of identifier to query for ("JISC", "CORE")
 *
 * Check https://jqueryui.com/autocomplete/ for info on the autocomplete API ($(...).autocomplete constructor)
*/
function createAutocomplete(inputSelector, infoSelector, type){
    // Select input with id
    const $info = $(infoSelector);
    $(inputSelector).autocomplete({
        source: function(request, response){
            // Construct URL endpoint
            $.getJSON(
                search_identifiers_url + request.term,
                // api_key retrieved from flask params
                {"api_key": org_acc_api_key, "type": type},
                function(data){
                    /* Make an array for each piece of data to show in the searched list
                     * the 'label' and 'value' properties of the object are used in the jquery autocomplete API.
                     * The label property is what is displayed in the drop down list; the value property is
                     * what the input box is set to after selection.
                     * the 'name' property is used to populate the .extra-info span.
                     * Example data:
                     *	[
                     *		{"id": "123456789", "institution": "University of something", "type": "JISC"}
                     *	]
                     */
                    let newArray = data.map(function(identifier){
                        return {"label": identifier.institution + " (" + identifier.id + ")", "value": identifier.id, "name": identifier.institution};
                    })
                    response(newArray);
                },
            )
        },
        // Executed when something is selected
        select: function( event, ui ){
            // Update the extra info box with the item's name when we make a selection
            $info.val(ui.item.name)
        },
        // Executed on blur event
        change: function( event, ui ){
            // If no item has been selected, just clear the box.
            if(!ui.item) {
                $(this).val("");
                $info.val("");
            }
        },
        // Min length of input text to execute a request
        minLength: 2,
        // 100 ms delay so we don't send too many requests
        delay: 100
    })
}

/*
* copy_name_el -
*	copies contents of one orginal field to a copy of it, and whenever the original changes updates the copy.
*
*	Param origId - string reference to an ID or Class that uniquely identifies original field
*	Param copyId - string reference to an ID or Class that uniquely identifies the copy field
*/
function copy_name_el(origId, copyId){
    $origName = $(origId);
    $copyName = $(copyId);

    // Whenever the original field changes, update the copy field
    $origName.on("change", function(e){
        $copyName.val(e.target.value);
    });
    // Initialise the copy field from current content of original field
    $copyName.val($origName.val());
} // End-copy_name_el

function expandSwordSettingsAccordion($swordPanel, $repoSoftware){
/*
* Expand the SWORD settings accordion if the repo-software is Eprints or Dspace as these will need to have
* SWORD configured.
*	Param $swordPanel - The SWORD accordion
*	Param $repoSoftware - Repository Software element
*/
    // SWORD panel is currently collapsed
    if($swordPanel.hasClass("show_hide--is-collapsed")){
        // If software is changed --> now contains eprints or dspace
        // Then click the <a> element to expand the panel
        const sw = getSelectedVal($repoSoftware);
        if(sw.includes("eprints") || sw.includes("dspace")) {
            $swordPanel.find("a").trigger("click");
        }
       }
}

$(document).ready(function() {
    /**
     *  Setup for Repository SWORD configuration panel
     **/

    // Get the dom objects (id names are the same as they are in forms/account.py)
    const $packagingFormat = $('#uniform-packaging');
    const $xmlFormat = $('#xml_format');
    const $targetQueue = $('#target_queue');
    // Initially run in case eprints-rioxx is already set. Same for review queue.
    showHideReviewQueueDependingOnXmlFormat(getSelectedVal($xmlFormat), $targetQueue);
    // Run on xmlFormat change
    $xmlFormat.on("change", function (e) {
        const xmlFormat = getSelectedVal($xmlFormat);
        changePackagingDependingOnXmlFormat(xmlFormat, $packagingFormat);
        showHideReviewQueueDependingOnXmlFormat(xmlFormat, $targetQueue);
    });

    const $repoSoftware = $('#repository_software');
    const $swordPanel = $('#sword_details');
    // Expand SWORD panel when screen is rendered if repo-software requires it
    expandSwordSettingsAccordion($swordPanel, $repoSoftware);
    // Run on repoSoftware change - If eprints or dspace software is selected, and sword panel not already expanded,
    // then expand it by clicking the <a> element
    $repoSoftware.on("change", function (e) {
        expandSwordSettingsAccordion($swordPanel, $repoSoftware);
     });

    /**
     * Setup for Repository Identifiers Form
     **/
    // Snippet to copy Organization Name from main field on screen to Identifier form field
    copy_name_el("#organisation_name", "#org_name");

    // Snippet to copy Repository Name from main field on screen to Identifier form field
    copy_name_el("#repository_name", "#repo_name");

    // Initialize the automcomplete functions
    createAutocomplete("#jisc_id", "#jisc_id_name", "JISC");
    createAutocomplete("#core_id", "#core_id_name", "CORE");

    /**
     *	Code for handling Excluded Provider Ids checkboxes
     **/
    const $providerTables = $('#harv-note-srcs, #pub-note-srcs');

    // If <all> or <none> button is clicked in either of the notification sources tables
    $providerTables.on("click", "button", function(e){
        let setOn = e.target.value === "on";    // Button value determines wither checkboxes are to be set ON or not
        // Find all the checkboxes in the <tbody> section of the <table> in which the <button> was clicked
        $(this).closest("table").find("tbody").find("input:checkbox".concat(setOn ? ":not(:checked)" : ":checked")).prop("checked",setOn);
    });

    // Pre-process Sources form before submission occurs.
    $('#frm-note-srcs').on("submit", function(e){
        let excludeSrcIdsA = []; // Array of source IDs
        // Look for Unchecked checkboxes in BOTH harvester & publisher sources tables
        $providerTables.find('input:checkbox:not(:checked)').each(function(x,el){
            excludeSrcIdsA.push(el.value);
        });
        // CSV string of Excluded Ids is added to the hidden input field with id "excluded-ids"
        $('#excluded-ids').val(excludeSrcIdsA.join(','));
    });

    /**
    *   Code to display long description of selected duplicate level below the selection box
    **/
    const $sel = $("#dups_level_pub, #dups_level_harv");
    $sel.on('change', function(e){
        // pass `this` as context for choosing the selected option
        const optionSelected = $("option:selected", this)[0];
        // Traverse up to closest <li> then down to the last <span> within the <li>
        $(this).closest("li").children("span:last-child").html(optionSelected.title + '.');
    });

});

