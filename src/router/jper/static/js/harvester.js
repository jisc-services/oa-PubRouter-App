/*
* Script to control the button on the harvester manage page, turning a harvester service on/off
*/

$(document).ready(function() {
    function setElementValues($el, pressed, label){
        $el.attr("aria-pressed", pressed).attr("aria-label", label);
    }

    function handle_click(btn_class, on_off_classes){
        $('#webservices-list span.' + btn_class).on("click keydown", function(e){
            if(isClickOrAllowedKeypress(e)) {
                const $el = $(this);
                // if the class is in waiting mode, you can't do anything
                if ($el.hasClass("waiting")){
                    return;
                }
                // set state of button to be waiting, till the request involved is complete
                $el.addClass("waiting");
                const url = $el.data("url");
                // make a POST request to the url to deactivate/reactivate the harvester service
                $.post(url).done(function(retData){
                    // toggle the button from on/off; remove waiting class
                    $el.toggleClass(on_off_classes).removeClass("waiting");
                    setElementValues($el, retData.status, (retData.status ? "Deactivate": "Activate") + " harvester");
                })
                .fail(function(xhr, status, error){
                    // Remove waiting class if we fail
                    $el.removeClass("waiting");
                    alert(xhr.responseJSON.error);
                });
            }
        });
    }
    /**
    * Function to handle click of the toggle button that enables/disables the harvester web-service
    **/
    handle_click('harvester-toggle-button', 'harvester-on harvester-off')
    // handle_click('harvester-live-btn', 'harvester-live harvester-test')
});

