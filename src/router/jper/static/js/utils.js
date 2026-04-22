/**
*   Utility functions

 Author: Jisc
**/

function sleep(ms) {
/*
*   Sleep in milliseconds
*   Usage:
*       sleep(500).then(() => {
*           Do something after the sleep!
*       });
*/
    return new Promise(resolve => setTimeout(resolve, ms));
}

function formatDateToDDMMYYYY(date) {
	return ("0" + date.getDate()).slice(-2) + "-" + ("0"+(date.getMonth()+1)).slice(-2) + "-" + date.getFullYear();
}

function formatDateToDDMMYYYYhhmmss(date) {
	return formatDateToDDMMYYYY(date) + " " + ("0" + date.getHours()).slice(-2) + ":" + ("0" + date.getMinutes()).slice(-2) + ":" + ("0" + date.getSeconds()).slice(-2);
}

function isClickOrAllowedKeypress(e, stopProp = true) {
/*
*	Check whether keypress is allowed or not
*
*	@param e: object returned by event handler
*	@returns Boolean: True - a click or an allowed keypress; False - not allowed keypress
*/
    if(stopProp) {
        e.stopPropagation();
    }
    if(e.type === 'click') {
        return true;
    }
//console.log("*", e.key, "->", e.key.charCodeAt(0));
    // Must be keypress; return true if key is a Space (32), Enter (69) or Return (13); otherwise false
    if([32, 69, 13].includes(e.key.charCodeAt(0))){
        e.preventDefault();     // This stops window scrolling on spacebar press
        return true;
    }
    return false;   // Not an allowed keypress
}


function initInfoAccordion() {
/**
* Code to initialise Info accordions and Title accordions - adds a clickable icon.
* For accessibility the text exposed by the clickable icon is visually-hidden, but always visible to screen-readers
**/
    const $body = $('body');

    // Construct Info accordion HTML
    $('.accordion').hide().wrap('<div class="x-accordion x-info x-hide" tabindex="0"></div>');
    // Click handler for Info accordion
    $body.on("click keydown", '.x-accordion', function(e){
        if (isClickOrAllowedKeypress(e)) {
            $(this).toggleClass("x-show x-hide").children(".accordion").slideToggle("linear");
        }
    });

    // Construct Title accordion HTML
    $('.title-accordion').each(function(){
        const $this = $(this);
        const $firstChild = $this.children().first();
        const label = '<span class="x-title">' + $firstChild.text() + '</div>';
        $firstChild.remove();
        $this.hide().wrap('<div class="xt-accordion x-hide" tabindex="0"></div>').before(label);
    } );
    // Click handler for Title accordion
    $body.on("click keydown", '.xt-accordion', function(e){
        if (isClickOrAllowedKeypress(e)){
            $(this).toggleClass("x-show x-hide").children(".title-accordion").slideToggle("linear");
        }
    });

}

function showPageNumbers($pgNumContainer, numPages, pgNum) {

    function prevNextLi(pgNum, prev){
        let prevNext = prev ? "Previous" : "Next";
        const delta = prev ? -1 : 1;
        const spans = [
            `<span class="icon icon-chevron-${prev ? 'left' : 'right'} icon--heavy"></span>`,
            `<span class="pagination__text">${prevNext}</span>`
        ];
        let html = `<li class="pag_item pag_item--${prevNext.toLowerCase()}"><a href="" data-param="page" data-value="${pgNum + delta}" aria-label="${prevNext} page">`;
        if (prev){
            html += spans[0] + spans[1];
        } else {
            html += spans[1] + spans[0];
        }
        return html + '</a> </li>';
    }

    function outputLi(start, end, numPages, pgNum){
        let html = "";
        const currClass = "pag_item--current" + (numPages == pgNum ? " pag_item--last" : "");
        for (let x = start; x <= end; x++) {
            html += `<li class="pag_item ${x === pgNum ? currClass : ''}"><a href="" data-param="page" data-value="${x}" aria-label="Go to page ${x}">${x}</a> </li>`;
        }
        return html;
    }

    if (numPages <= 1){
        return
    }

    let html = '<ul class="pagination-container">';
    if (pgNum >= 2) {
        // Add 'Prev' button
        html += prevNextLi(pgNum, true);
    }
    // Output first 2 <li> elements
    html += outputLi(1, 2, numPages, pgNum);

    let lastStart = 0;
    if (numPages < 10) {
        lastStart = 3;
    }
    else {
        let start = 0;
        let end = 0;
        lastStart = numPages - 1;
        if (pgNum <= 5){
            start = 3;
            end = 7;
        }
        else {
            html += '<li class="pag_item pag_item--space">&hellip;</li>';
            if (pgNum <= (numPages - 5)) {
                start = pgNum - 2;
                end = pgNum + 2;
            }
            else {
                start = pgNum - 6;
                end = pgNum - 2;
            }
        }
        html += outputLi(start, end, numPages, pgNum);
        if (pgNum <= (numPages - 5)) {
            html += '<li class="pag_item pag_item--space">&hellip;</li>';
        }
    }
    html += outputLi(lastStart, numPages, numPages, pgNum);
    if (pgNum < numPages) {
        html += prevNextLi(pgNum, false);
    }
    html += '</ul>';
    $pgNumContainer.addClass("pag-pages").append(html);
}

function doShowHide($btnEl, onlyIf = null){
/*
    SHOW/HIDE a block when a button is pressed - Toggle button text & show/hide target element

    :param $btnEl: jQuery button element, which must have 2 data attributes:
                   `data-text="..."` attribute containing text to display (which is then prefixed by "Hide " or "Show ")
                   `data-target="..."` attribute containing jQuery selector (e.g. "#something") of element to show/hide.
    :param onlyIf: Boolean or null - True/False: doShowHide execution is conditional on whether $btnEl is currently On/Off;
                                     null (default): doShowHide always executes:
    :return: New state: true if Showing; false if Hiding
*/
    // willBeShowing is set to the NEW "state" of the target after function exits
    const willBeShowing = ! $btnEl.hasClass("on");

    // If execution dependent on current state, and not in required state then don't change anything
    if (onlyIf === willBeShowing){
      return ! willBeShowing;
    }
    $btnEl.toggleClass("on off").text((willBeShowing ? "Hide " : "Show ") + $btnEl.data("text") );
    $($btnEl.data("target")).toggleClass("visuallyhidden");
    return willBeShowing;
}

function triggerClick(onOffNull, eTargetData){
/*
    Trigger a click on another element using a Selector ID specified by eTargetData, depending on value of `onOffNull`.

    :param onOffNull: Has one of these values which determines which data attribute to use to find Id of button to trigger
                    - null: Use `data-trigger` value; true: Use `data-trigger_on` value; false: use `data-trigger_off` value
    :param: eTargetData: the value of `event.target.dataset`
*/
    const triggerBtnId = onOffNull === null ? eTargetData.trigger : onOffNull ? eTargetData.trigger_on : eTargetData.trigger_off;
    if (triggerBtnId !== undefined){
        $(triggerBtnId).trigger("click");
    }
}

function clipboardCopy(eTarget, eTargetDataset){
/*
    Copy content of element to clipboard.

    :param: eTarget: Clicked element
    :param: eTargetDataset: Clicked element data values object
*/

  // if clicked element has no data-target attribute, then the clicked element itself is assumed to be the copy source
  const $cpyFrom = $(eTargetDataset?.target ?? eTarget);
  let val = null;
  switch(eTargetDataset.function) {
    case "copy_link":
        val = $cpyFrom.attr("href");
        // If HREF is not a full URL, then assume it is relative to current pages domain
        if (! val.startsWith("http")) {
            val = window.location.protocol + window.location.host + val;
        }
        break;
    case "copy_text":
        val = $cpyFrom.text();
        break;
    case "copy_val":    // Copy Value of the target element
        val = $cpyFrom.val();
        break;
    case "copy_data_val":   // Copy Value of data-val attribute
        val = eTargetDataset?.val ?? '';
        break;
    case "copy_table":
        let rows = [];
        $cpyFrom.find("tr").each(function(){
                let cells = [];
                $(this).children().each(function(){cells.push($(this).text())});
                rows.push(cells.join(", "));
            });
        val = rows.join("\n");
        break;
  }
  if (val) {
    navigator.clipboard.writeText(val);
    $cpyFrom.fadeOut(50).fadeIn(200);   // Flash the element that was just copied
  }
}

function setActionClickHandlers(selectors='body', filters='.do_action'){
/*
*   :param selectors: String - selector to use for the click handler - can be element or class or id; or
                        different values separated by commas - e.g. ".things, #an_id".
                      DEFAULT is <body> element.
*   :param filters: String - selector to use for filtering events caught by the click selector. Different values
                        should be selected by commas - e.g. ".action, .do-it"
                      DEFAULT is '.do_action' CSS class-name.
*/
    if (! selectors){
      selectors = 'body';
    }
    $(selectors).on("click keydown", filters, function(event){
// console.log(event);
        if (isClickOrAllowedKeypress(event)) {
            const eTarget = event.target;
            const eTargetDataset = eTarget.dataset;

            switch(eTargetDataset.action) {
                case "clipboard":
                    clipboardCopy(eTarget, eTargetDataset);
                    break;

                case "showhide":
                    const showing = doShowHide($(eTarget));
                    // Process any auto-trigger that is indicated in the element data (in eTargetDataset)
                    triggerClick(showing, eTargetDataset);
                    break;

                case "confirm":
                    // If HTML element has `data-no_suffix` attribute then DON'T append "Are you sure?"
                    const ok = confirm("\n" + eTargetDataset.msg + ("no_suffix" in eTargetDataset ? "" : ".\n\nAre you sure?"));
                    if (! ok) {
                        event.preventDefault();
                    }

            };
        }
    });
}

function modalFocusTrap(modalPanelEl, ixOfFirst = 0, prevFocusableElement = document.activeElement){
    modalPanelEl.style.display = "block";   // Show the modal panel
    const focusableEls = Array.from(
      modalPanelEl.querySelectorAll(
        'div[tabindex], textarea:not([disabled]), input:not([disabled]), select:not([disabled]), button:not([disabled])'
      )
    );
    const firstFocusableEl = focusableEls[0];
    const lastFocusableEl = focusableEls[focusableEls.length - 1];

    let currentFocus = focusableEls[ixOfFirst];
    currentFocus.focus();

    function handleFocus (e){
      // if the focused element "lives" in your modal container then just focus it
      if (focusableEls.includes(e.target)) {
        currentFocus = e.target;
      } else {
        // Outside of the container
        e.preventDefault();
        e.stopPropagation();
        // if previously the focused element was the first element then focus the last
        // element - means you were using the shift key
        currentFocus = currentFocus === firstFocusableEl ? lastFocusableEl : firstFocusableEl;
        currentFocus.focus();
      }
    };
    function handleClick (e){
      // if the clicked element is outside the modal container, then stop it from having any effect
      if (! focusableEls.includes(e.target)) {
        e.preventDefault();
        e.stopPropagation();
      }
    };

    document.addEventListener("focus", handleFocus, true);
    document.addEventListener("click", handleClick, true);

    return {
      closePanel: () => {
        modalPanelEl.style.display = "none";
        document.removeEventListener("focus", handleFocus, true);
        document.removeEventListener("click", handleClick, true);
        prevFocusableElement.focus();
        return null;
      }
    };
}


function flash_msg_at_location_href() {
    /**
    * Code to determine if URL to current page contains a #reference AND if there is a flash message to display
    * and, if so, to copy the flash message to the re-displayed panel (where, presumably, a button has just
    * been pressed).
    **/
    let url = window.location.href;
    let hashIx = url.indexOf('#');
    // There is a #reference
    if (hashIx > 0){
        // See if there is a flash message - will get the FIRST flash msg
        let flash = document.getElementById('flash-1');
        if (flash !== null) {
            let flashCopy = flash.cloneNode(true);
            let hashEl = document.getElementById(url.substr(hashIx + 1));
            hashEl.append(flashCopy);
            // the data-level value of the Flash message is one of "flash-danger", "flash-info", "flash-success"
            // Add this as class to the panel being redisplayed.
            hashEl.classList.add(flash.getAttribute('data-level'));
        }
    }
}


function addSpinnerTimer() {
    /**
    Adds a timer to the <span class="spinner"></span> element & returns a function
    that starts the timer & displays spinner.

    Calling convention:
        startSpinnerTimerFn = addSpinnerTimer();

    At point where form is submitted, call the function:
        startSpinnerTimerFn();
    **/
	const $spinner = $(".spinner");
	const $timer = $('<span>00:00</span>');

	// add class "larger", hide it, append timer
	$spinner.addClass("larger").hide().append($timer);

	var numSecs = 0;
	var numMins = 0;
	function runTimer() {
	  if(numSecs == 59){
		numSecs = 0;
		numMins ++;
	  } else {
		numSecs ++;
	  }
	  $timer.text(`0${numMins}`.slice(-2) + ":" + `0${numSecs}`.slice(-2));
	}

	function startTimerShowSpinner(){
		setInterval(runTimer, 1000);		// Start & run timer
		sleep(200).then(() => {$spinner.show();});		// Show spinner after 200ms
	}
	return startTimerShowSpinner
}


function addCountdownTimer(numSecs=0, endFn=null) {
    /**
    Adds a timer to the <span class="countdown"></span> element & returns a function
    that starts & displays the timer.

    Calling convention:
        startCountdownTimerFn = addCountdownTimer(5, func-to-run-on-expiry);

    At point where form is submitted, call the function:
        startCountdownTimerFn();
    **/
	const $countdown = $(".countdown");

	$countdown.text(`${numSecs}s`);

	function startCountdown(){
		let timer = setInterval(function() {
		    numSecs --;
            if(numSecs == 0){
                clearInterval(timer);
                if(endFn){
                    endFn();
                }
            }
            $countdown.text(`${numSecs}s`);
		}
		, 1000);		// Start & run timer
	}
	return startCountdown
}

