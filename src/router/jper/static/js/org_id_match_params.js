/*
 org_id_match_params.js - Code for Obtaining potential Org Id match params via ROR API, displaying these for selection
       and using selected IDs to update OrgId match params.
     - Retrieve potential OrgIDs using ROR API
     - Display OrgIDs for selection
     - Create JSON data structure of selected IDs for updating Router's Org ID matching params
     - Submit Org Ids to Router

 ** Designed to work with ROR REST API v2 - https://ror.readme.io/docs/rest-api

 ** THIS code DEPENDS on functions in `ajax_helpers.js` file.

Author: Jisc
*/
const rorAPIurl = "https://api.ror.org/v2/organizations";       // V2 endpoint

function getDetailsObjFromRorResultItem(rorItem, nameType="ror_display", langCode="en"){
/*
    Retrieve the following for an organisation, and return in an object:
        * Org Name - from "names" array within returned ROR result item
        * ROR record status
        * Array of Org types
        * Org Website URL.

    :param rorItem: Object - Individual item returned from ROR API query
    :param nameType: String - Type of name to return - "ror_display" will return the default Org name, "label" returns the first Org name of required language
    :param langCode: String - 2 char language code (defaults to English: "en")
*/
    const getDefault = nameType === "ror_display";
    let itemObj = null;

    // Obtain name
    let orgName = null;
    for (const nameObj of rorItem.names) {
        // If name-object is of required type
        if (nameObj.types.includes(nameType)) {
            // If getting default or, if not, then if is required language
            if (getDefault || nameObj.lang === langCode){
                orgName = nameObj.value;
                break;
             }
        }
    }
    if (orgName) {
        itemObj = {
            name: orgName,
            status: rorItem.status,
            // Capitalize the types
            types: rorItem.types.map(t => {return t.charAt(0).toUpperCase() + t.slice(1)}),
            website: ""
        };
        for (const link of rorItem.links){
            if (link.type === "website"){
                itemObj.website = link.value;
                break;
            }
        }
    }
    return itemObj;
}

function getAndShowOrgName($el, idType, idVal, rorNameType, rorLangCode) {
/*
    Append Organisation Name corresponding to Identifier, retrieved via ROR API or Crossref API depending on idType

    :param $el: Jquery object to which Org Name is to be appended
    :param idType: String - Type of identifier
    :param idVal: String - ID Value (e.g. 'ISNI', 'ROR' etc).
    :param rorNameType: String - Type of name to return from ROR API results - "ror_display" will return the default Org name, "label" returns the first Org name of required language
    :param rorLangCode: String - 2 char language code (defaults to English: "en") - used for ROR API results
*/
    function handleError($el, url, msg){
    // Function uses `url` and `$el` variables defined in outer scope
        if (url){
            console.log(`ERROR getting ${url} - `, msg);
        }
        $el.append(`<div class="italic">${msg}</div`);
    }

    function addOrgNameFromRor($el, idType, idVal) {
    /*
        Append Organisation Name corresponding to Identifier, retrieved via ROR API
    */

        const missingIdMsg = "ID not in ROR database";
        const idTypeToRorTypeMap = {
            // CROSSREF: "FundRef",
            GRID: "grid",
            ISNI: "isni",
            RINGGOLD: null,
            ROR: "ror"
        }
        const searchType = idTypeToRorTypeMap[idType];
        if (! searchType){
            handleError($el, null, missingIdMsg);
            return;
        }
        const gettingROR = searchType === "ror";
        var searchQuery = "";
        if (gettingROR){
            searchQuery = "/" + idVal;
        }
        else{
            if (searchType === "isni") {
                // Use regex to split string every 4th char and insert a space character'%20'
                idVal = idVal.match(/.{1,4}/g).join("%20");
            }
            else {
                // If NOT ROR Id, need to URL encode characters & replace all '.' by '%2E'
                idVal = encodeURIComponent(idVal).replace(/\./g, '%2E')
            }
            // Search by id Type AND id Value (which may contain spaces, so are surround double quotes '%22')
            searchQuery = `?query.advanced=external_ids.type:${searchType}+AND+external_ids.all:%22${idVal}%22`;
        }
        const url = rorAPIurl + searchQuery;

        doAjaxGet(url, {},
            // Success func - Get ROR returns a single item dict, Getting anything else returns array of item dicts
            function(responseO){
                // Status code 200 can actually return an errors array... if so, display error message(s).
                if (responseO?.errors) {
                    handleError($el, url, responseO.errors.join(". "));
                    return;
                }
                let name = "";
                if (gettingROR) {
                    detailObj = getDetailsObjFromRorResultItem(responseO, rorNameType, rorLangCode);
                }
                else if (responseO.items.length) {
                    // Use first item returned, which will be the primary/closest match from API query
                    detailObj = getDetailsObjFromRorResultItem(responseO.items[0], rorNameType, rorLangCode);
                }
                if (detailObj){
                    // Add org name to element
                    $el.append(`<div>${detailObj.name}</div`);
                }
                else {
                    handleError($el, null, missingIdMsg)
                }
            },
            // Failure func
            function(msg){
                handleError($el, url, msg);
            }
        );  // end-doAjaxGet    }

    }


    function addOrgNameFromCrossref($el, idType, idVal) {
    /*
        Append Organisation Name corresponding to Identifier, retrieved via Crossref API
    */
        const url = "https://api.crossref.org/funders/" + idVal;
        doAjaxGet(url, {},
            // Success func - Get ROR returns a single item dict, Getting anything else returns array of item dicts
            function(responseO){
                let name = responseO.message.name;
                // Add org name to element
                $el.append(`<div>${name}</div`);
            },
            // Failure func
            function(msg){
                handleError($el, url, msg);
            }
        );  // end-doAjaxGet    }
    }

    if (idType === "CROSSREF") {
        addOrgNameFromCrossref($el, idType, idVal);
    }
    else {
        addOrgNameFromRor($el, idType, idVal);
    }
}

function embellishOrgIds($orgIdTable, rorNameType="ror_display", rorLangCode="en") {
/*
    Takes text Org-IDs within <td> elements and wraps them with <a> links to the actual ID website.
    :param $orgIdTable: Jquery obj - Org-Id Table
    :param rorNameType: String - Type of name to return - "ror_display" will return the default Org name, "label" returns the first Org name of required language
    :param rorLangCode: String - 2 char language code (defaults to English: "en")
*/
    const idUrlMap = {
        CROSSREF: "https://api.crossref.org/funders/",
        GRID: null,     // There is no longer a public API for organisation lookup via GRID Id URL
        ISNI: "https://isni.org/isni/",
        RINGGOLD: null,     // There is no public API for organisation lookup via RINGGOLD Id URL
        ROR: "https://ror.org/"
    };

    $orgIdTable.addClass("no-underline").find("tbody td").each(function() {
        // Split something like "ISNI: 00001111" into an array ["ISNI", "00001111"]
        const partsA = this.innerText.split(": ");
        const urlBase = idUrlMap[partsA[0]];
        const $td = $(this);
        // If the ID has a base URL, then create an <div><a ...> link to the Identifier and WRAP this around the existing ID
        // text (e.g. ISNI: 00001111 ---> <div><a href="...">ISNI: 0000111</a></div>);
        // otherwise simply wrap <div></div> around it (e.g. GRID: grid.5337.2  ---> <div>GRID: grid.5337.2</div>)
        $td.addClass("org-grid").wrapInner(function(){
            return (urlBase) ?
                `<div><a href="${urlBase}${partsA[1]}" target="_blank" title="opens in new tab"></a></div>` :
                "<div></div>";
        });
        // Get Org name and append
        getAndShowOrgName($td, partsA[0], partsA[1], rorNameType, rorLangCode);
    });
}

function getRORidFromUrl(rorUrl){
    return rorUrl.substring(rorUrl.lastIndexOf("/") + 1).toLowerCase();
}

function initAndSetOrgIdEventHandlers(
    ajaxQueryUrl,
    $root,
    $getIdsPanel,
    $orgName,
    $listOrgIdsPanel,
    $orgIdFilters,
    $viewRelatedPanel,
    existingIdsArr,
    countryCode,
    filterCountryCodesArr,
    rorNameType,
    rorLangCode
    ){
/*
    :param $root: jQuery obj - Outer container
    :param $getIdsPanel: jQuery obj - Form with Org Name used by when Org Ids from ROR
    :param $orgName: jQuery obj - Input holding the organisation name
    :param $listOrgIdsPanel: jQuery obj - List Org Ids DIV
    :param $orgIdFilters: jQuery obj - Org Id Filter radio buttons DIV
    :param $viewRelatedPanel: jQuery obj - Overlay Panel for viewing related (parents/children) orgs  DIV
    :param existingIdsArr: Array of strings - existing org ids
    :param countryCode: String - Required country code (set to "" or null if all countries are wanted)
    :param filterCountryCodesArr: Array of strings - country codes we want to KEEP - can be empty if `countryCode` has a value
    :param rorNameType: String - Type of name to return - "ror_display" will return the default Org name (REGARDLESS OF LANGUAGE CODE), "label" returns the first Org name of required language
    :param rorLangCode: String - 2 char language code (defaults to English: "en")
*/

    const $viewRelatedH3 = $viewRelatedPanel.find("h3");
    const $viewRelatedForm = $viewRelatedPanel.find(".form");
    const $radBtn = $orgIdFilters.find("input:radio");  // We have just one radio button for resetting checkboxes
    const $checkboxes = $orgIdFilters.find("input:checkbox");

    // Set ror API URL - append country code filter if a code is specified
    const rorAPIsearchUrl = rorAPIurl + (countryCode ? `?filter=country.country_code:${countryCode}&`: "?");
    const maxItemsPerPg = 20;  // Maximum items returned in a page of data - Value fixed for ROR API
//console.log("rorAPIurl", rorAPIurl);
    // ID types to capture (ROR are captured automatically) - for now, exclude "FUNDREF", "CROSSREF", "RINGGOLD" types.
    const filterIdTypes = ["GRID", "ISNI"];  // , "RINGGOLD", "FUNDREF", "CROSSREF" ]
    const $foundIdsTbody = $listOrgIdsPanel.find("tbody");
    const $flashEl = $root.find(".flash");
    const flash = new FlashMsg($flashEl, 8);
    let rorResultArr = [];
    let origWindowY = 0;
    let lastWindowY = 0;
    let parsedDataArr = [];    // Array of Org data objects derived from ROR API results
    let rorIdsArr = [];   // Array of ROR ids that have been retrieved from ROR API results
    // If country code is provided or filterCountryCodesArr is empty then we don't need to do any filtering
    if(countryCode && filterCountryCodesArr.length === 0){
        filterCountryCodesArr = [countryCode];
    }
    let masterOrg = ""; // First org returned by org-name search
    let masterOrgLower = ""; // Lowercase name of first organisation returned by org-name search
    let viewRelatedModal = null;

    function exactMatchToMasterOrg(relationArr, name, relation="") {
        if(name.toLowerCase() === masterOrgLower){
            relationArr.push(relation + "exact");
        }
    }

    function filterParseRORData(item){
    /*
        :param item: object returned by request to ROR API

        Filter and Parse organisation object:
            * Discard any that are foreign (country_code is NOT in `filterCountryCodesArr` array, if it is specified)
            * Extract Orgname, ROR, Other IDs (that are in `filterIdTypes` array)

        Potentially append an object (see below) to a parsedDataArr and an Id to rorIdsArr.

        Object:
            {
              id: "ROR-ID",
              name: "org-name",
              country: "country",
              ids: [[ "type", "id-value"], ...]     // 1st element is always ROR
              children: [{name: "org-name", ror: "ROR-ID"}, ]
              parents: [{name: "org-name", ror: "ROR-ID"}, ]
              related: [{name: "org-name", ror: "ROR-ID"}, ]
            },...

        :Return: true - if Object added; false - no object added (filtered out)
    */
        // Replaced: original v1 code... const _countryCode = item?.country?.country_code;
        const _countryCode = item?.locations[0]?.geonames_details?.country_code;

        // Check if required country code
        if (! filterCountryCodesArr.includes(_countryCode)) {
            return false;   // Country code is NOT one we want, so skip to next item
        }
        const detailObj = getDetailsObjFromRorResultItem(item, rorNameType, rorLangCode);
        if (detailObj === null) {
            return false;
        }
        // If this is FIRST record for display, we assume it is CLOSEST match to search term & will be used for comparison purposes
        if (parsedDataArr.length === 0) {
            masterOrg = detailObj.name;
            masterOrgLower = masterOrg.toLowerCase();
        }
        // Establish if this Organisation name exactly or closely matches user's input search string
        let relationToSrchOrgArr = [];
        exactMatchToMasterOrg(relationToSrchOrgArr, detailObj.name);

        // Capture related child / parent organisations - ignore "Related" orgs
        let childrenA = [];
        let parentsA = [];
        let relatedA = [];
        // Loop over relationships array of objects, like [{label: "Org-name", id: "ROR-URL"}, ...]
        for (const obj of item.relationships) {
            const id = getRORidFromUrl(obj.id);
            const relatedOrgName = obj.label;
            switch(obj.type) {
                case "child":
                    // If this item has a child that matches search, then this is a parent of matching item
                    exactMatchToMasterOrg(relationToSrchOrgArr, relatedOrgName, "parent-");
                    childrenA.push([relatedOrgName, id]);
                    break;
                case "parent":
                    // If this item has a parent that matches search, then this is a child of matching item 
                    exactMatchToMasterOrg(relationToSrchOrgArr, relatedOrgName, "child-");
                    parentsA.push([relatedOrgName, id]);
                    break;
                case "related":
                    // This item is related to Searched for organisation
                    exactMatchToMasterOrg(relationToSrchOrgArr, relatedOrgName, "related-");
                    relatedA.push([relatedOrgName, id]);
                    break;
            }
        }
//console.log(detailObj.name, relationToSrchOrgArr);
        // ROR Id is provided as URL, but we only want the last segment, forced to lower case
        let rorId = getRORidFromUrl(item.id);
        // Merge detail Obj to create orgObj
        let orgObj = Object.assign(
            {
                children: childrenA,
                country: _countryCode,
                id: rorId,
                ids: [["ROR", rorId]],
                parents: parentsA,
                related: relatedA,
                relations: relationToSrchOrgArr
            },
            detailObj
        );

        // Iterate over external_ids array - capture any external IDs e.g. GRID, ISNI etc
        for (const idObj of item.external_ids) {
            const idType = idObj.type.toUpperCase();
            if (filterIdTypes.includes(idType)) {
                // FundRef Ids are now known as CROSSREF Ids
                if (idType === "FUNDREF") {
                    idType = "CROSSREF";
                }
                for (const id of idObj.all) {
                    orgObj.ids.push([idType, id.replaceAll(' ', '').toLowerCase()]);
                }
            }
        }
        rorIdsArr.push(rorId);
        parsedDataArr.push(orgObj);
        return true;
    }

    function addRowToIdsTable(ix, orgObj) {
        function setDesc(arr, count, word, suff="") {
            if (count) {
                arr.push(`${count} ${word}${(count > 1) ? suff : ""}`);
            }
        }
       // hashRelated is by combining bits for parents: 001 | children: 010 | related: 100
        let hasRelated = []
        setDesc(hasRelated, orgObj.parents.length, "parent", "s");
        setDesc(hasRelated, orgObj.children.length, "child", "ren");
        setDesc(hasRelated, orgObj.related.length, "related");

        let formattedIdsExists = [];
        let allIdsExist = true;
        // Process all IDs to find out if all of them already exist in Matching Parameters
        for (const idArr of orgObj.ids) {
            const idVal = `${idArr[0]}: ${idArr[1]}`;     // Something like "GRID: 123456..."
            const existing = existingIdsArr.includes(idVal);
            allIdsExist = allIdsExist && existing;     // if existing is False, then allIdsExist will ultimately be False
            formattedIdsExists.push({exists: existing, id:idVal});
        }
        let trs = [];
        const trExists = (allIdsExist ? "exists " : "");
        let firstTrClass = "none";
        let otherTrClass = "none";
        let trTitle = "";
        const relationsArr = orgObj.relations;
        if (relationsArr.length) {
            firstTrClass = relationsArr.join(' ');
            // otherTrClass is similar to firstTrClass, except each relation is prefixed by underscore 'x'
            otherTrClass = relationsArr.map(s => 'x' + s).join(' ');
            if(relationsArr.includes("child-exact")) {
                const numExtraParents = orgObj.parents.length - 1;
                const andParents = numExtraParents >= 1 ? ` & ${numExtraParents} other parent${numExtraParents > 1 ? 's': ''}` : '';
                trTitle = ` title="Child of '${masterOrg}'${andParents}."`;
            }
            else if (relationsArr.includes("parent-exact")) {
                trTitle = ` title="Parent of '${masterOrg}'"`;
            }
            else if (relationsArr.includes("related-exact")) {
                trTitle = ` title="Related to '${masterOrg}'"`;
            }
        }
        let first = true;   // First ID is always ROR id
        for (const obj of formattedIdsExists) {
            // <td> exists class value only needs setting where allIdsExist is False
            const existsClass = ! allIdsExist && obj.exists ? 'class="exists"' : '';
            const checkboxSnippet = `<td ${existsClass}>` + (obj.exists ? 'Exists' : `<input type="checkbox" value="${obj.id}" title="${'Select ' + obj.id}" aria-label="Add identifier">`) + '</td></tr>';
            if(first) {
                const showRelated = hasRelated.length ? `<br><button class="nav-btn btn btn--3d btn-small-gap" data-action="run_func" data-func="show_related" data-value="${ix}">View ${hasRelated.join(' & ')}</button>` : "";
                const status = orgObj.status === "active" ? "" : `<span class="gap-left-5 brown lozenge">${orgObj.status}</span>`;
//                const orgTypes = orgObj.types.reduce(function(t, v){ return t + `<span class="lozenge">${v}</span>`; }, "<br>");
                const orgTypes = `<span class="gap-left circle" title="Org type: ${orgObj.types.join(', ')}.">T</span>`;
                const websiteIcon = orgObj.website ? `<a class="gap-left-5 no-decoration" href="${orgObj.website}" target="_blank" title="Organisation website opens in a new tab">🌐</a>` : "";
                trs.push(`<tr class="${trExists}${firstTrClass}"><td rowspan="${orgObj.ids.length}"${trTitle}>${orgObj.name}${status}${orgTypes}${websiteIcon}${showRelated}</td><td ${existsClass}>${obj.id}</td>` + checkboxSnippet);
                first = false;
            }
            else {
                trs.push(`<tr class="${trExists}${otherTrClass}"><td ${existsClass}>${obj.id}</td>` + checkboxSnippet);
            }
        }
        $foundIdsTbody.append(trs);
    }

    function addAdditionalObj(rorId){
    /*
        Get additional organisation via ROR API - triggered from <Add> Button press on $viewRelatedPanel
    */
        doAjaxGet(rorAPIurl + `/${rorId}`, {},
            // Success func
            function(responseO){
                // Status code 200 can actually return an errors array... if so, display error message(s).
                if (responseO?.errors) {
                    flash.msg($viewRelatedPanel, "e", responseO.errors.join(".<br>"));
                    return;
                }
                // Accumulate retrieved data into `parsedDataArr` (after processing it)
                const objAdded = filterParseRORData(responseO);
                if(objAdded) {
                    // The last item just retrieved & added to parsedDataArr added we want to append to Ids Table
                    const lastIx = parsedDataArr.length - 1;
                    addRowToIdsTable(lastIx, parsedDataArr[lastIx]);
                }
                else {
                    const detailObj = getDetailsObjFromRorResultItem(responseO, rorNameType, rorLangCode);
                    const orgName = detailObj ? detailObj.name : "??";
                    flash.msg($viewRelatedPanel, 'i', `Organisation '${orgName}' is not in an eligible country.`);
                }
            },
            // Failure func
            function(msg){
                flash.msg($viewRelatedPanel, 'e', msg);
            }
        );  // end-doAjaxGet    }
    }

    function recursiveRORquery(rorUrlBase, rorUrl, pageNum){
        doAjaxGet(rorUrl, {},
            // Success func
            function(responseO){
                // Status code 200 can actually return an errors array... if so, display error message(s).
                if (responseO?.errors) {
                    flash.msg($getIdsPanel, "e", responseO.errors.join(".<br>"));
                    return;
                }
                if (responseO.number_of_results === 0) {
                    flash.msg($getIdsPanel, "i", "Found no organisations matching the input value");
                    return;
                }
                let ix = parsedDataArr.length;  // Starting index for new data
                // Accumulate retrieved data into `parsedDataArr` (after processing it)
                // and add ROR id for each item to `rorIdsArr`
                for (const item of responseO.items) {
                   // Note that an item could be filtered out here & NOT added to parsedDataArr
                    filterParseRORData(item);
                }
                // Now add new data to table in 'List Org Ids' panel (ix was initialised above, before adding new data)
                for (let len = parsedDataArr.length; ix < len; ++ix) {
                    addRowToIdsTable(ix, parsedDataArr[ix]);
                }
                // Display table if first page
                if(pageNum === 1){
                    $listOrgIdsPanel.show();
                }
                 // If more pages of data to get, update the ROR URL by appending `page=...` parameter & continue with while loop
                // num-Pages = Math.floor(responseO.number_of_results / maxItemsPerPg);
                if (pageNum <= Math.floor(responseO.number_of_results / maxItemsPerPg)) {
                   pageNum += 1;
                   recursiveRORquery(rorUrlBase, rorUrlBase + `&page=${pageNum}`, pageNum);
                }
            },
            // Failure func
            function(msg){
                flash.msg($getIdsPanel, 'e', msg);
            }
        );  // end-doAjaxGet
    }

    function getRORDataAndDisplayIdsTable(orgNameSrchStr){
        if(! orgNameSrchStr) {
            returns;
        }
        // Replace spaces in searchFor by %20
        const rorUrlBase = rorAPIsearchUrl + "query.advanced=names.value:" + encodeURIComponent(orgNameSrchStr);
        // ROR API returns max 20 records, so need to make repeated calls to retrieve all records
        parsedDataArr = [];
        rorIdsArr = [];
        recursiveRORquery(rorUrlBase, rorUrlBase, 1);
    }

    function submitOrgIds(){
        let orgIdsA = []; // Array of selected Org IDs
        // For each selected checkbox, add the OrgId to the list
        $foundIdsTbody.find("input:checkbox:checked").each(function(x,el){
            orgIdsA.push(el.value);
        });
        // No records to update
        if(orgIdsA.length === 0) {
            flash.msg($getIdsPanel, 'e', "No identifiers selected.");
            return;
        }
        let dataObj = { org_ids: orgIdsA };

        // Send request & when it is completed update the history panel.
        doAjaxPatch(ajaxQueryUrl, dataObj,
            // Success func
            function(responseO){
                flash.msg(null, "s", responseO.msg);
                // sleep 3 secs, then reload page
                sleep(3000).then(function(){
                    document.documentElement.scrollTop = 0;
                    location.reload();
                });
            },
            // Failure func
            function(msg){
                flash.msg(null, "e", msg);
            }
        );  // end-doAjaxPatch
    }

    function createTable(title, related){
        let html = [];
        if(related.length) {
            html.push(`<table><tbody><tr><th>${title} Organisations</th><th>Add</th></tr>`);
            // related is an array of arrays: [[org-name, ror-id], ...]
            for (const arr of related) {
                // Create TR with 2 elements Orgname
                const id = arr[1];
                const addBtnTd = rorIdsArr.includes(id) ? "<td></td>" : `<td id="${id}"><button class="bold-hov btn btn--3d" data-action="run_func" data-func="add_related" data-value="${id}" title="Add related">Add</button></td>`;
                html.push(`<tr><td>${arr[0]}</td>${addBtnTd}</tr>`);
            }
            html.push("</tbody></table>");
        }
        return html.join("");
    }

    function buildShowViewRelatedPanel(itemObj) {
        lastWindowY = window.scrollY;
//console.log(itemObj);
        $viewRelatedH3.html(itemObj.name);
        $viewRelatedForm.empty()
            .append(createTable("Parent", itemObj.parents))
            .append(createTable("Child", itemObj.children))
            .append(createTable("Related", itemObj.related));
        const viewRelatedEl = $viewRelatedPanel[0];
        viewRelatedEl.scrollIntoView(true);
        // Display 'View related' modal overlay panel, and move focus to first input field
        // pass DOM element as parameter
        viewRelatedModal = modalFocusTrap(viewRelatedEl);
    }

    function runButtonFunction(funcName, value){
        switch(funcName) {
            case "get_ror":
                origWindowY = window.scrollY;
                $foundIdsTbody.empty();
                $radBtn.trigger( "click" );     // Reset show-all radio btn
                masterOrg = masterOrgLower = "";
                getRORDataAndDisplayIdsTable($orgName.val());
                break;

            case "add_org_ids":
                submitOrgIds();
                break;

            case "hide_org_ids":
                $foundIdsTbody.empty();
                $listOrgIdsPanel.hide();
                // Close panel if open
                if (viewRelatedModal !== null) viewRelatedModal = viewRelatedModal.closePanel();
                document.documentElement.scrollTop = origWindowY;
                break;

            case "show_related":
                buildShowViewRelatedPanel(parsedDataArr[value]);
                break;

            case "add_related":
                // Remove <Add> button
                $viewRelatedForm.find(`#${value}`).empty();
                addAdditionalObj(value);
                break;

            case "close_related":
                viewRelatedModal = viewRelatedModal.closePanel();
                document.documentElement.scrollTop = lastWindowY;
                break;

        }
    }


    function setRootBtnClickHandlers(){
        $root.on("click", "button", function(event){
    //console.log(event);
            event.stopPropagation();
            const targetData = event.target.dataset;
            // NOT click or allowed keypress or a form submit button that was clicked
            if(! targetData?.action) {
                return;
            }
    //console.log("handling above event. Dataset action: ", event.target.dataset.action);
            switch(targetData.action) {
                // Run function
                case "run_func":
                    runButtonFunction(targetData.func, targetData.value);
                    break;

//                case "showhide":
//                    doShowHide($(event.target));
//                    break;
//                case "setvalue":
//                    // data elements on the button contain the target & text to set if button pressed
//                    $(targetData.target).val(targetData.text);
//                    break;
            }; // end-switch
        });
    }

    function setFilterClickHandlers(){
        const matchClassLookup = {
            E: ".exists",
            C: ".child-exact, .xchild-exact",
            P: ".parent-exact, .xparent-exact",
            R: ".related-exact, .xrelated-exact",
            O: ".none"
        };
        // Set click handlers on filter radio-buttons & checkboxes
        $orgIdFilters.on("click", "input", function(event){
            event.stopPropagation();
    //console.log(event);
            switch(event.target.name) {
                // Either show or hide Org-Id table rows that correspond to existing Match param Identifiers
                case "show_all":
                    // Remove hide from all elements that have it
                    $foundIdsTbody.find(".hide").each(function(){
                        $(this).removeClass("hide");
                    });
                    // Check all the checkboxes
                    $checkboxes.each(function(){
                        $(this).prop('checked', true);
                    });
                    break;

                // Either show or hide Org-Id table rows depending on tick-box values
                case "show_match":
                    // Create concatenated string of all checked checkbox values
                    let showSelectors = [];
                    let hideSelectors = [];
                    // Checkboxes are enclosed in a <fieldset> - which is the parent of the event.target
                    $checkboxes.each(function(){
                        if (this.checked) {
                            showSelectors.push(matchClassLookup[this.value]);
                        }
                        else {
                            hideSelectors.push(matchClassLookup[this.value]);
                        }
                    });
                    if (showSelectors.length) {
                        $foundIdsTbody.find(showSelectors.join(", ")).each(function(){
                            $(this).removeClass("hide");
                        });
                    }
                    if (hideSelectors.length){
                        $foundIdsTbody.find(hideSelectors.join(", ")).each(function(){
                            $(this).addClass("hide");
                        });
                        $radBtn.prop('checked', false);
                    } else {
                        $radBtn.prop('checked', true);
                    }
                    break;
            } // end-switch
        });  // end-$orgIdFilters.on
    }

    // Set click handlers on buttons
    setRootBtnClickHandlers();
    // Set click handlers on filter controls
    setFilterClickHandlers();
}
