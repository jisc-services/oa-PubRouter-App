/***************************************************************************************************************
*   navbar.js - Makes menu navigation bar (navbar) focusable so it be navigated by keyboard input alone, rather
*               than relying on mouse.
****************************************************************************************************************/

$(document).ready(function() {
    let $lastActive = null;
    let currentActive = null;

    // Remove the active class
    function removeActiveClass() {
        if ($lastActive !== null) {
            //console.log("++++remove-active");
            $lastActive.removeClass("active");
            $lastActive = null;
            currentActive = null;
        }

    }

    // Bind 2 event handlers to the navbar top-level li items
    $('nav.masthead__nav li.nav__item')
        // Bind a focus or mouseenter event - relies on the events bubbling up
        // Function deactivates any previous toplevel element, and activates the current item
        .on("focusin mouseenter", function(event){
            //console.log("add-active");
            event.stopPropagation();

            // This event may fire if one of the sub-menu items is tabbed to, in that case we don't want to change anything
            if (currentActive === this) {
                return;
            }
            // Deactivate previously active
            if ($lastActive !== null) {
                //console.log("--remove-active");
                $lastActive.removeClass("active");
            }
            // console.log("--add-active");
            currentActive = this;
            // Reset lastActive to point to current, and activate it
            $lastActive = $(this);
            $lastActive.addClass("active");
        })
        // Bind a mouseleave event to a navbar's top-level link which makes it inactive if mouseleave event occurs
        .on("mouseleave", removeActiveClass);


    // Bind a focus event to the top level elements which are NOT in nav section - relies on 'focusin' event bubbling up
    // Makes the last active top-level nav element inactive when focus moves away from the Nav menu
    $('body').on("focusin", removeActiveClass);
});
