/**********************************************************************
* Cut down version of ux.jisc-1.1.0.jper.script-foot.js that contains
* ONLY the funcctionality required by JPER.
*
* It includes a modification to Jquery UI widget: jisc.sortableRwdtable
* to allow for a sortable first column. (self.zeroOffset was introduced).
*
* The architecture of this file is determined by the original Jisc UX
* code. It is believed that it was produced via Browserfy process.
*
* DEPENDENCIES:
*   Unlike the original, this file is NOW dependent on EXTERNALLY LOADED:
*       - JQuery
*       - JQuery-UI
***********************************************************************/

/*
* REQUIRE FUNCTION
*/
require = (function e(t, n, r) {
	function s(o, u) {
		if (!n[o]) {
			if (!t[o]) {
				let a = typeof require == "function" && require;

				if (!u && a)
					return a(o, !0);
				if (i)
					return i(o, !0);
				let f = new Error("Cannot find module '" + o + "'");
				throw f.code = "MODULE_NOT_FOUND", f
			}
			let l = n[o] = {
				exports: {}
			};
			t[o][0].call(l.exports, function (e) {
				let n = t[o][1][e];
				return s(n ? n : e)
			}, l, l.exports, e, t, n, r)
		}
		return n[o].exports
	}
	let i = typeof require == "function" && require;
	for (let o = 0; o < r.length; o++)
		s(r[o]);
	return s
})({

/**
* Screen resizing handler - NO dependencies
*/
1: [function (require, module, exports) {
/**
* @fileOverview A plugin to manage the execution of javascript callbacks across breakpoints
* @author CX Partners, Andy Mantell
* @name conduct
* @dependencies: None
*/

/**
* Main conduct function.
* For a given array of media queries and callbacks, we will register a resize event and test the media queries,
* applying and unapplying the relevant callbacks at each point.
*
* @param Object breakpoints
*   Object containing an Array (media_queries) of callbacks and media queries in the following format and
*   an optional Number (timeout) to supply a debounce delay in milliseconds.
*    {
*     'media_queries': [
*       {
*         query: 'max-width: 600px',
*         match: function() {
*           // This code will run when this media query moves from an unmatched state to a matched state
*         },
*         unmatch: function() {
*           // This code will run when this media query moves from a matched state to an unmatched state
*         }
*       },
*       {
*         query: 'min-width: 601px',
*         fallback: true,
*         match: function() {
*           // This code will run when this media query moves from an unmatched state to a matched state
*         },
*         unmatch: function() {
*           // This code will run when this media query moves from a matched state to an unmatched state
*         }
*       },
*     ],
*      'timeout': 250
*    }
* Important note: The order that these callbacks appear in the array is important.
* When resizing *up*, the callbacks will be unmatched and matched in an ascending order.
* When resizing *down*, the callbacks will be unmatched and matched in a descending order.
* The logic behind this is that you tend to want to unmatch a "desktop" breakpoint before matching
* a "mobile" breakpoint.
*/

(function() {
  'use strict';

  function Conduct(breakpoints) {

    // Timeout to allow us to debounce the resize event
    let debounce = null;

    // Keep track of the window width between resize events so that we can know whether we are resizing up or down
    let windowSize = window.innerWidth;

    // Fail gracefully if no configuration is specified
    breakpoints = breakpoints || {};
    breakpoints.media_queries = breakpoints.media_queries || [];

    // Set default timeout value
    breakpoints.timeout = breakpoints.timeout || 300;

    /**
    * Evaluate the current breakpoints
    * On page load, run over all the available breakpoints and apply them all
    */
    function evaluate() {
      for (let i = 0; i < breakpoints.media_queries.length; i++) {

        // By default, we'll record that the breakpoint is not matched
        breakpoints.media_queries[i].matched = false;

        // And then attempt to apply the breakpoint callback if it matches
        apply(breakpoints.media_queries[i]);
      }
    }

    /**
    * Main function which is used to apply a given media query / callback combination
    */
    function apply(breakpoint) {

      // If this browser doesn't support matchMedia, just match all breakpoints that are marked as fallbacks
      if(typeof(window.matchMedia) !== 'function') {
        if(breakpoint.fallback && !breakpoint.matched) {
          breakpoint.match();
          breakpoint.matched = true;
        }

        // And then bail out, there's nothing more to do
        return;
      }

      // Does the media query match?
      if (window.matchMedia(breakpoint.query).matches) {
        // Yes, this breakpoint is active
        // If it *wasn't* active last time we tested, then we have moved from an unmatched to a matched state
        if (!breakpoint.matched) {

          // Run the match callback and record this breakpoint as being currently matched
          setTimeout(function() {
            if(typeof(breakpoint.match) === 'function') {
              breakpoint.match();
            }

            breakpoint.matched = true;
          }, 0);
        }
      } else {
        // No, the breakpoint is not active
        // If it *was* active last time we tested, we have moved from a matched to an unmatched state
        if (breakpoint.matched) {

          // Run the unmatch callback and record this breakpoint as being not currently matched
          setTimeout(function() {
            if(typeof(breakpoint.unmatch) === 'function') {
              breakpoint.unmatch();
            }

            breakpoint.matched = false;
          }, 0);
        }
      }
    }

    /**
    * Main resize handler
    */
    function resize() {

      // Debounce the resize event
      clearTimeout(debounce);
      debounce = setTimeout(function() {

        // If the last recorded window size was more than current, then we are resizing down
        if (windowSize > window.innerWidth) {

          // Apply the breakpoints in reverse order, starting with the last one in the array
          for (let i = breakpoints.media_queries.length - 1; i >= 0; i--) {
            apply(breakpoints.media_queries[i]);
          }

        } else if (windowSize < window.innerWidth) {
          // Else if the last recorded window size was less than current, we are resizing up
          // Apply the breakpoints in normal, ascending order starting with the first one in the array
          for (let j = 0; j < breakpoints.media_queries.length; j++) {
            apply(breakpoints.media_queries[j]);
          }
        }

        // Record the current width of the window so we can compare it on the next resize event
        windowSize = window.innerWidth;

      }, breakpoints.timeout);
    }

    // Kick off an initial evaluation of breakpoints
    evaluate();

    // If we've got matchMedia support...
    if(typeof(window.matchMedia) === 'function') {

      // Bind the resize handler to the window resize event
      if (window.addEventListener) {
        window.addEventListener('resize', resize, false);
      } else if (window.attachEvent) {
        window.attachEvent('onresize', resize);
      }
    }

    /**
    * Public methods
    */
    return {
      'evaluate': evaluate
    };

  }

  // Expose as a CommonJS module for browserify
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = Conduct;
  } else {
    // Otherwise expose as a global for non browserify users
    window.Conduct = Conduct;
  }

})();
},
{}],


/**
* jQuery UI
*/
3:[function(require,module,exports){ // jQueryUI

//console.log("***3-jqueryUI***");
},{}],


/**
* Jisc Collapsibles (Accordion)
*/
5:[function(require,module,exports){ //jisc.collapsibles (Accordion)
//console.log("***5***");
var $ = require('jquery');
require('jquery-ui');

/**
 * @fileOverview A jQuery UI Widget to show and hide collapsible sections of a page
 * @author Andy Mantell
 * @name $.jisc.collapsibles
 * @dependencies: jQuery, jQuery UI widget factory
 */

/**
 * Collapsible sections
 *
 * This plugin fires events for create, destroy, collapse, expand which can be listened to in one of two ways:
 *
 * // Using a listener
 * $(':jisc-collapsibles').on('collapsiblesexpand', function() {})
 *
 * // Passing in a callback to the widget
 * $('.foo').collapsibles({ expand: function() { ... }})


 */

  $.widget("jisc.collapsible", {

    options: {
      triggerSelector: '.show_hide__trigger:eq(0)',
      targetSelector: '.show_hide__target:eq(0)',
      expandedClass: 'show_hide--is-expanded',
      collapsedClass: 'show_hide--is-collapsed',
      containerClass: 'show_hide__container',
      effectDuration: 250
    },

    /**
     * The standard jQuery UI create function
     * Set up our variables and events
     */
    _create: function() {

      // get the context
      this._self = this;

      // get the vars
      this._container = $(this.element);
      this._collapsible_target = this._container.find(this.options.targetSelector);

      // Grab our trigger

      this._collapsible_trigger = this._container.find(this.options.triggerSelector);


      // Store our original trigger before we modify it, to be restored on destroy
      this._original_collapsible_trigger = this._collapsible_trigger.clone(true, true);

      // Make a link to put inside the trigger for keyboarders
      // @TODO: Consider use of ARIA roles and tabindex=0 to make headings directly focusable clickable?
      // Is using an <a> tag here to get that focusablility and interactivity technically (in)correct?
      // What is support for these ARIA roles like?
      let $trigger_link = $('<a href="#"></a>');
      $trigger_link.on('click', function(e) {
        e.preventDefault();
      });

	  //Set up text
	  let $hiddenrow = $('<span class="visuallyhidden">[Open panel below]</span>');

	  this._collapsible_trigger.prepend($hiddenrow);
      // Wrap the trigger in this link
      this._collapsible_trigger.wrapInner($trigger_link);

      // Set up the events
      this._on(this._collapsible_trigger, { 'click': this.toggle });

      this._trigger('create');
    },

    /**
     * Standard jQuery UI init function
     */
    _init: function() {

      // If the target isn't marked as expanded, then collapse it
      if(!this._container.hasClass(this.options.expandedClass)) {
        this.collapse(0);
      }

      this._container.addClass(this.options.containerClass);
    },

    /**
     * Main toggle function
     * Used as a click handler on the _collapsible_trigger
     */
    toggle: function(e) {

      if(typeof(e) !== 'undefined') {
        e.preventDefault();
      }

      if(this._container.hasClass(this.options.expandedClass)) {
        this.collapse();
      } else {
        this.expand();
      }
    },

    /**
     * Helper function to collapse the _collapsible_target
     */
    collapse: function(duration) {

      let self = this;

	  //Set visually hidden text to open panel
	  self._collapsible_trigger.children().children(".visuallyhidden").text("[Open panel below]");

      // Allow this function to take an optional effect duration. Used to instantly hide sections on _create()
      if(typeof(duration) === 'undefined') {
        duration = this.options.effectDuration;
      }

      // Collapse the section
      this._collapsible_target
        .slideUp(duration, function() {

          // Switch the appropriate classes once the animation has finished
          self._container
            .addClass(self.options.collapsedClass)
            .removeClass(self.options.expandedClass);
        });

      this._trigger('collapse');
    },

    /**
     * Helper function to expand the _collapsible_target
     */
    expand: function(duration) {

      let self = this;

	  // Change text within visually hidden span for expand action
      self._collapsible_trigger.children().children(".visuallyhidden").text("[Close panel below]");

      // Allow this function to take an optional effect duration. Used to instantly hide sections on _create()
      if(typeof(duration) === 'undefined') {
        duration = this.options.effectDuration;
      }

      // Expand the section
      this._collapsible_target
        .slideDown(duration, function() {

          // Switch the appropriate classes once the animation has finished
          self._container
            .addClass(self.options.expandedClass)
            .removeClass(self.options.collapsedClass);
        });

      this._trigger('expand');
    },

    /**
     * Tear everything down again.
     */
    destroy: function() {

      // Remove the click handler from the trigger
      this._off(this._collapsible_trigger, 'click');

      // Restore our original trigger, without the wrapping <a>
      this._collapsible_trigger.replaceWith(this._original_collapsible_trigger);

      // Remove all classes from the container
      this
        ._container
        .removeClass(this.options.containerClass)
        .removeClass(this.options.collapsedClass)
        .removeClass(this.options.expandedClass);

      // Make sure the content is visible again
      this._collapsible_target.show();

      this._trigger('destroy');

      // call the base destroy function
      $.Widget.prototype.destroy.call(this);
    },

    /**
     * The standard jQuery UI _setOption function
     */
    _setOption: function(key, value) {
      this._super( key, value );
    }

  });

},{"jquery":"jquery","jquery-ui":3}],


/**
* Jisc func data-collapsible
*/
6:[function(require,module,exports){ // *1* Something to do with data-collapsible
// JavaScript Document'use strict';
//console.log("***6***");
var $ = require('jquery');
var getDOMConfig = require('../core/js/getDOMConfig');

// Grab the options spec from the pagination widget
var options = require('./jquery.jisc.show_hide--menu');

$('[data-collapsible]').each(function(index, item) {
  let $item = $(item);

  // Based on the "options spec" provided by the plugin, grab any overrides
  // from the DOM
  let settings = getDOMConfig($item, options);

  $item.collapsible(settings);
});
},{"../core/js/getDOMConfig":11,"./jquery.jisc.show_hide--menu":5,"jquery":"jquery"}],





/**
* CHECK VALUES
* Jisc - Export values used by CSS Breakpoint configuration function
*/
10:[function(require,module,exports){  // Export values used by CSS Breakpoint configuration function - need to check values
/**
 * @fileOverview  Breakpoint configuration
 * Must always match what is stored in /src/core/_variables.scss
 */
module.exports = {
  'inner': 565,
  'mid': 630,
  'outer': 757,
  'intermediate': 850,
  'max': 950
};

},{}],


/**
* Jisc - getDOMConfig, has 2 methods: getAttributes(...), getDOMConfig(...)
*/
11:[function(require,module,exports){   // Jisc - getDOMConfig
/**
 * @file Grab plugin settings from data attributes on a DOM element based on
 * a "spec". This spec is just an object, who's keys are used to search for
 * data attributes of the same name.
 */
var $ = require('jquery');

/**
 * Recursive function to grab data attributes from a DOM element based on an options spec
 * @param  {Element} $element    The DOM element from which to grab data
 * @param  {Object}  settings    The settings object that found data should be added to
 * @param  {Object}  optionsSpec The options spec object defining the possible structure for the settings
 * @param  {String}  path        When called recursively, this will be used to build up the full structure of the data attribute
 */
function getAttributes($element, settings, optionsSpec, path) {

  if(typeof(path) === 'undefined') {
    path = '';
  }

  // Loop over the passed in spec
  $.each(optionsSpec, function(key, value) {

    // If it's an object, then we will need to recurse
    if($.isPlainObject(value)) {

      // Recurse with a new object to represent this branch of the tree
      let subSettings = {};

      // Call this function recursively to grab data from this part of the options spec
      getAttributes($element, subSettings, value, path + key.toLowerCase() + '-');

      // Only assign it to the settings object on the way back up if the result was not empty
      if(!$.isEmptyObject(subSettings)) {
        settings[key] = subSettings;
      }

    } else {

      // Try and grab a value of data-KEY from the DOM
      // html5 data attributes are accessed in lowercase, regardless of the
      // case in which they are defined in the DOM
      let data = $element.data(path + key.toLowerCase());

      // If we've found the data, pop it on our settings to return back
      if(typeof(data) !== 'undefined') {
        settings[key] = data;
      }

    }

  });
}

function getDOMConfig($element, optionsSpec) {
  let settings = {};

  getAttributes($element, settings, optionsSpec);

  return settings;
}

module.exports = getDOMConfig;

},{"jquery":"jquery"}],


/**
* CANDIDATE FOR REMOVAL
* Jisc - function for lazy load of images (looks for data attrib: "data-img-src" - NOT used by JPER
*/
//12:[function(require,module,exports){   // Jisc - function for lazy load of images [REMOVE ?]
//var $ = require('jquery');
//
///**
// * Function to lazy load images
// * @param  {Element} element The DOM element within which to lazy load iamges
// */
//module.exports = function(element) {
//
//  $(element).find('[data-img-src]').each( function(){
//
//    var $this = $(this),
//        $imgClass = $this.attr('class'),
//        $imgSrc = $this.data('img-src'),
//
//    // Create image element
//        $img = $('<img />')
//            .addClass($imgClass)
//            .attr('src', $imgSrc)
//            .attr('alt', '');
//
//    // Add class to parent so we can apply CSS
//    $this.parent().addClass('has-media');
//
//    // Inject img into DOM in place of span
//    $this.replaceWith($img);
//
//  });
//
//};
//
//},{"jquery":"jquery"}],


/**
* Helper function that simply runs $.uniform() on <select> elements
*/
16:[function(require,module,exports){   // *4* Helper function that simply runs $.uniform() on <select> elements [KEEP]
var $ = require('jquery');

require('./vendor/jquery.uniform.js');

$('select').uniform();

},{"./vendor/jquery.uniform.js":17,"jquery":"jquery"}],


/**
* CANDIDATE FOR REMOVAL - LOOKS LIKE ONLY APPLIED TO <SELECT> stmts
*   3rd party library: Uniform - https://github.com/antoniocarboni/uniform - "Sexy forms"
*   Only used for select statements by default (see #16 above
*/
17:[function(require,module,exports){   // Uniform (3rd party library) - "sexy forms" [KEEP]
/*

Uniform v2.1.2
Copyright Â© 2009 Josh Pyles / Pixelmatrix Design LLC
http://pixelmatrixdesign.com

Requires jQuery 1.3 or newer

Much thanks to Thomas Reynolds and Buck Wilson for their help and advice on
this.

Disabling text selection is made possible by Mathias Bynens
<http://mathiasbynens.be/> and his noSelect plugin.
<https://github.com/mathiasbynens/jquery-noselect>, which is embedded.

Also, thanks to David Kaneda and Eugene Bond for their contributions to the
plugin.

Tyler Akins has also rewritten chunks of the plugin, helped close many issues,
and ensured version 2 got out the door.

License:
MIT License - http://www.opensource.org/licenses/mit-license.php

Enjoy!

*/
/*global jQuery, document, navigator*/

(function (wind, $, undef) {
    "use strict";

    /**
     * Use .prop() if jQuery supports it, otherwise fall back to .attr()
     *
     * @param jQuery $el jQuery'd element on which we're calling attr/prop
     * @param ... All other parameters are passed to jQuery's function
     * @return The result from jQuery
     */
    function attrOrProp($el) {
        let args = Array.prototype.slice.call(arguments, 1);

        if ($el.prop) {
            // jQuery 1.6+
            return $el.prop.apply($el, args);
        }

        // jQuery 1.5 and below
        return $el.attr.apply($el, args);
    }

    /**
     * For backwards compatibility with older jQuery libraries, only bind
     * one thing at a time.  Also, this function adds our namespace to
     * events in one consistent location, shrinking the minified code.
     *
     * The properties on the events object are the names of the events
     * that we are supposed to add to.  It can be a space separated list.
     * The namespace will be added automatically.
     *
     * @param jQuery $el
     * @param Object options Uniform options for this element
     * @param Object events Events to bind, properties are event names
     */
    function bindMany($el, options, events) {
        let name, namespaced;

        for (name in events) {
            if (events.hasOwnProperty(name)) {
                namespaced = name.replace(/ |$/g, options.eventNamespace);
                $el.on(namespaced, events[name]);
            }
        }
    }

    /**
     * Bind the hover, active, focus, and blur UI updates
     *
     * @param jQuery $el Original element
     * @param jQuery $target Target for the events (our div/span)
     * @param Object options Uniform options for the element $target
     */
    function bindUi($el, $target, options) {
        bindMany($el, options, {
            focus: function () {
                $target.addClass(options.focusClass);
            },
            blur: function () {
                $target.removeClass(options.focusClass);
                $target.removeClass(options.activeClass);
            },
            mouseenter: function () {
                $target.addClass(options.hoverClass);
            },
            mouseleave: function () {
                $target.removeClass(options.hoverClass);
                $target.removeClass(options.activeClass);
            },
            "mousedown touchbegin": function () {
                if (!$el.is(":disabled")) {
                    $target.addClass(options.activeClass);
                }
            },
            "mouseup touchend": function () {
                $target.removeClass(options.activeClass);
            }
        });
    }

    /**
     * Remove the hover, focus, active classes.
     *
     * @param jQuery $el Element with classes
     * @param Object options Uniform options for the element
     */
    function classClearStandard($el, options) {
        $el.removeClass(options.hoverClass + " " + options.focusClass + " " + options.activeClass);
    }

    /**
     * Add or remove a class, depending on if it's "enabled"
     *
     * @param jQuery $el Element that has the class added/removed
     * @param String className Class or classes to add/remove
     * @param Boolean enabled True to add the class, false to remove
     */
    function classUpdate($el, className, enabled) {
        if (enabled) {
            $el.addClass(className);
        } else {
            $el.removeClass(className);
        }
    }

    /**
     * Updating the "checked" property can be a little tricky.  This
     * changed in jQuery 1.6 and now we can pass booleans to .prop().
     * Prior to that, one either adds an attribute ("checked=checked") or
     * removes the attribute.
     *
     * @param jQuery $tag Our Uniform span/div
     * @param jQuery $el Original form element
     * @param Object options Uniform options for this element
     */
    function classUpdateChecked($tag, $el, options) {
        let c = "checked",
            isChecked = $el.is(":" + c);

        if ($el.prop) {
            // jQuery 1.6+
            $el.prop(c, isChecked);
        } else {
            // jQuery 1.5 and below
            if (isChecked) {
                $el.attr(c, c);
            } else {
                $el.removeAttr(c);
            }
        }

        classUpdate($tag, options.checkedClass, isChecked);
    }

    /**
     * Set or remove the "disabled" class for disabled elements, based on
     * if the element is detected to be disabled.
     *
     * @param jQuery $tag Our Uniform span/div
     * @param jQuery $el Original form element
     * @param Object options Uniform options for this element
     */
    function classUpdateDisabled($tag, $el, options) {
        classUpdate($tag, options.disabledClass, $el.is(":disabled"));
    }

    /**
     * Wrap an element inside of a container or put the container next
     * to the element.  See the code for examples of the different methods.
     *
     * Returns the container that was added to the HTML.
     *
     * @param jQuery $el Element to wrap
     * @param jQuery $container Add this new container around/near $el
     * @param String method One of "after", "before" or "wrap"
     * @return $container after it has been cloned for adding to $el
     */
    function divSpanWrap($el, $container, method) {
        switch (method) {
        case "after":
            // Result:  <element /> <container />
            $el.after($container);
            return $el.next();
        case "before":
            // Result:  <container /> <element />
            $el.before($container);
            return $el.prev();
        case "wrap":
            // Result:  <container> <element /> </container>
            $el.wrap($container);
            return $el.parent();
        }

        return null;
    }


    /**
     * Create a div/span combo for uniforming an element
     *
     * @param jQuery $el Element to wrap
     * @param Object options Options for the element, set by the user
     * @param Object divSpanConfig Options for how we wrap the div/span
     * @return Object Contains the div and span as properties
     */
    function divSpan($el, options, divSpanConfig) {
        let $div, $span, id;

        if (!divSpanConfig) {
            divSpanConfig = {};
        }

        divSpanConfig = $.extend({
            bind: {},
            divClass: null,
            divWrap: "wrap",
            spanClass: null,
            spanHtml: null,
            spanWrap: "wrap"
        }, divSpanConfig);

        $div = $('<div />');
        $span = $('<span />');

        // Automatically hide this div/span if the element is hidden.
        // Do not hide if the element is hidden because a parent is hidden.
        if (options.autoHide && $el.is(':hidden') && $el.css('display') === 'none') {
            $div.hide();
        }

        if (divSpanConfig.divClass) {
            $div.addClass(divSpanConfig.divClass);
        }

        if (options.wrapperClass) {
            $div.addClass(options.wrapperClass);
        }

        if (divSpanConfig.spanClass) {
            $span.addClass(divSpanConfig.spanClass);
        }

        id = attrOrProp($el, 'id');

        if (options.useID && id) {
            attrOrProp($div, 'id', options.idPrefix + '-' + id);
        }

        if (divSpanConfig.spanHtml) {
            $span.html(divSpanConfig.spanHtml);
        }

        $div = divSpanWrap($el, $div, divSpanConfig.divWrap);
        $span = divSpanWrap($el, $span, divSpanConfig.spanWrap);
        classUpdateDisabled($div, $el, options);
        return {
            div: $div,
            span: $span
        };
    }


    /**
     * Wrap an element with a span to apply a global wrapper class
     *
     * @param jQuery $el Element to wrap
     * @param object options
     * @return jQuery Wrapper element
     */
    function wrapWithWrapperClass($el, options) {
        let $span;

        if (!options.wrapperClass) {
            return null;
        }

        $span = $('<span />').addClass(options.wrapperClass);
        $span = divSpanWrap($el, $span, "wrap");
        return $span;
    }


    /**
     * Test if high contrast mode is enabled.
     *
     * In high contrast mode, background images can not be set and
     * they are always returned as 'none'.
     *
     * @return boolean True if in high contrast mode
     */
    function highContrast() {
        let c, $div, el, rgb;

        // High contrast mode deals with white and black
        rgb = 'rgb(120,2,153)';
        $div = $('<div style="width:0;height:0;color:' + rgb + '">');
        $('body').append($div);
        el = $div.get(0);

        // $div.css() will get the style definition, not
        // the actually displaying style
        if (wind.getComputedStyle) {
            c = wind.getComputedStyle(el, '').color;
        } else {
            c = (el.currentStyle || el.style || {}).color;
        }

        $div.remove();
        return c.replace(/ /g, '') !== rgb;
    }


    /**
     * Change text into safe HTML
     *
     * @param String text
     * @return String HTML version
     */
    function htmlify(text) {
        if (!text) {
            return "";
        }

        return $('<span />').text(text).html();
    }

    /**
     * If not MSIE, return false.
     * If it is, return the version number.
     *
     * @return false|number
     */
    function isMsie() {
        return navigator.cpuClass && !navigator.product;
    }

    /**
     * Return true if this version of IE allows styling
     *
     * @return boolean
     */
    function isMsieSevenOrNewer() {
        if (wind.XMLHttpRequest !== undefined) {
            return true;
        }

        return false;
    }

    /**
     * Test if the element is a multiselect
     *
     * @param jQuery $el Element
     * @return boolean true/false
     */
    function isMultiselect($el) {
        let elSize;

        if ($el[0].multiple) {
            return true;
        }

        elSize = attrOrProp($el, "size");

        if (!elSize || elSize <= 1) {
            return false;
        }

        return true;
    }

    /**
     * Meaningless utility function.  Used mostly for improving minification.
     *
     * @return false
     */
    function returnFalse() {
        return false;
    }

    /**
     * noSelect plugin, very slightly modified
     * http://mths.be/noselect v1.0.3
     *
     * @param jQuery $elem Element that we don't want to select
     * @param Object options Uniform options for the element
     */
    function noSelect($elem, options) {
        let none = 'none';
        bindMany($elem, options, {
            'selectstart dragstart mousedown': returnFalse
        });

        $elem.css({
            MozUserSelect: none,
            msUserSelect: none,
            webkitUserSelect: none,
            userSelect: none
        });
    }

    /**
     * Updates the filename tag based on the value of the real input
     * element.
     *
     * @param jQuery $el Actual form element
     * @param jQuery $filenameTag Span/div to update
     * @param Object options Uniform options for this element
     */
    function setFilename($el, $filenameTag, options) {
        let filename = $el.val();

        if (filename === "") {
            filename = options.fileDefaultHtml;
        } else {
            filename = filename.split(/[\/\\]+/);
            filename = filename[(filename.length - 1)];
        }

        $filenameTag.text(filename);
    }


    /**
     * Function from jQuery to swap some CSS values, run a callback,
     * then restore the CSS.  Modified to pass JSLint and handle undefined
     * values with 'use strict'.
     *
     * @param jQuery $el Element
     * @param object newCss CSS values to swap out
     * @param Function callback Function to run
     */
    function swap($elements, newCss, callback) {
        let restore, item;

        restore = [];

        $elements.each(function () {
            let name;

            for (name in newCss) {
                if (Object.prototype.hasOwnProperty.call(newCss, name)) {
                    restore.push({
                        el: this,
                        name: name,
                        old: this.style[name]
                    });

                    this.style[name] = newCss[name];
                }
            }
        });

        callback();

        while (restore.length) {
            item = restore.pop();
            item.el.style[item.name] = item.old;
        }
    }


    /**
     * The browser doesn't provide sizes of elements that are not visible.
     * This will clone an element and add it to the DOM for calculations.
     *
     * @param jQuery $el
     * @param String method
     */
    function sizingInvisible($el, callback) {
        let targets;

        // We wish to target ourselves and any parents as long as
        // they are not visible
        targets = $el.parents();
        targets.push($el[0]);
        targets = targets.not(':visible');
        swap(targets, {
            visibility: "hidden",
            display: "block",
            position: "absolute"
        }, callback);
    }


    /**
     * Standard way to unwrap the div/span combination from an element
     *
     * @param jQuery $el Element that we wish to preserve
     * @param Object options Uniform options for the element
     * @return Function This generated function will perform the given work
     */
    function unwrapUnwrapUnbindFunction($el, options) {
        return function () {
            $el.unwrap().unwrap().unbind(options.eventNamespace);
        };
    }

    let allowStyling = true,  // False if IE6 or other unsupported browsers
        highContrastTest = false,  // Was the high contrast test ran?
        uniformHandlers = [  // Objects that take care of "unification"
            {
                // Buttons
                match: function ($el) {
                    return $el.is("a, button, :submit, :reset, input[type='button']");
                },
                apply: function ($el, options) {
                    let $div, defaultSpanHtml, ds, getHtml, doingClickEvent;
                    defaultSpanHtml = options.submitDefaultHtml;

                    if ($el.is(":reset")) {
                        defaultSpanHtml = options.resetDefaultHtml;
                    }

                    if ($el.is("a, button")) {
                        // Use the HTML inside the tag
                        getHtml = function () {
                            return $el.html() || defaultSpanHtml;
                        };
                    } else {
                        // Use the value property of the element
                        getHtml = function () {
                            return htmlify(attrOrProp($el, "value")) || defaultSpanHtml;
                        };
                    }

                    ds = divSpan($el, options, {
                        divClass: options.buttonClass,
                        spanHtml: getHtml()
                    });
                    $div = ds.div;
                    bindUi($el, $div, options);
                    doingClickEvent = false;
                    bindMany($div, options, {
                        "click touchend": function () {
                            let ev, res, target, href;

                            if (doingClickEvent) {
                                return;
                            }

                            if ($el.is(':disabled')) {
                                return;
                            }

                            doingClickEvent = true;

                            if ($el[0].dispatchEvent) {
                                ev = document.createEvent("MouseEvents");
                                ev.initEvent("click", true, true);
                                res = $el[0].dispatchEvent(ev);

                                if ($el.is('a') && res) {
                                    target = attrOrProp($el, 'target');
                                    href = attrOrProp($el, 'href');

                                    if (!target || target === '_self') {
                                        document.location.href = href;
                                    } else {
                                        wind.open(href, target);
                                    }
                                }
                            } else {
                                $el.trigger("click");
                            }

                            doingClickEvent = false;
                        }
                    });
                    noSelect($div, options);
                    return {
                        remove: function () {
                            // Move $el out
                            $div.after($el);

                            // Remove div and span
                            $div.remove();

                            // Unbind events
                            $el.unbind(options.eventNamespace);
                            return $el;
                        },
                        update: function () {
                            classClearStandard($div, options);
                            classUpdateDisabled($div, $el, options);
                            $el.detach();
                            ds.span.html(getHtml()).append($el);
                        }
                    };
                }
            },
            {
                // Checkboxes
                match: function ($el) {
                    return $el.is(":checkbox");
                },
                apply: function ($el, options) {
                    let ds, $div, $span;
                    ds = divSpan($el, options, {
                        divClass: options.checkboxClass
                    });
                    $div = ds.div;
                    $span = ds.span;

                    // Add focus classes, toggling, active, etc.
                    bindUi($el, $div, options);
                    bindMany($el, options, {
                        "click touchend": function () {
                            classUpdateChecked($span, $el, options);
                        }
                    });
                    classUpdateChecked($span, $el, options);
                    return {
                        remove: unwrapUnwrapUnbindFunction($el, options),
                        update: function () {
                            classClearStandard($div, options);
                            $span.removeClass(options.checkedClass);
                            classUpdateChecked($span, $el, options);
                            classUpdateDisabled($div, $el, options);
                        }
                    };
                }
            },
            {
                // File selection / uploads
                match: function ($el) {
                    return $el.is(":file");
                },
                apply: function ($el, options) {
                    let ds, $div, $filename, $button;

                    // The "span" is the button
                    ds = divSpan($el, options, {
                        divClass: options.fileClass,
                        spanClass: options.fileButtonClass,
                        spanHtml: options.fileButtonHtml,
                        spanWrap: "after"
                    });
                    $div = ds.div;
                    $button = ds.span;
                    $filename = $("<span />").html(options.fileDefaultHtml);
                    $filename.addClass(options.filenameClass);
                    $filename = divSpanWrap($el, $filename, "after");

                    // Set the size
                    if (!attrOrProp($el, "size")) {
                        attrOrProp($el, "size", $div.width() / 10);
                    }

                    // Actions
                    function filenameUpdate() {
                        setFilename($el, $filename, options);
                    }

                    bindUi($el, $div, options);

                    // Account for input saved across refreshes
                    filenameUpdate();

                    // IE7 doesn't fire onChange until blur or second fire.
                    if (isMsie()) {
                        // IE considers browser chrome blocking I/O, so it
                        // suspends tiemouts until after the file has
                        // been selected.
                        bindMany($el, options, {
                            click: function () {
                                $el.trigger("change");
                                setTimeout(filenameUpdate, 0);
                            }
                        });
                    } else {
                        // All other browsers behave properly
                        bindMany($el, options, {
                            change: filenameUpdate
                        });
                    }

                    noSelect($filename, options);
                    noSelect($button, options);
                    return {
                        remove: function () {
                            // Remove filename and button
                            $filename.remove();
                            $button.remove();

                            // Unwrap parent div, remove events
                            return $el.unwrap().unbind(options.eventNamespace);
                        },
                        update: function () {
                            classClearStandard($div, options);
                            setFilename($el, $filename, options);
                            classUpdateDisabled($div, $el, options);
                        }
                    };
                }
            },
            {
                // Input fields (text)
                match: function ($el) {
                    if ($el.is("input")) {
                        let t = (" " + attrOrProp($el, "type") + " ").toLowerCase(),
                            allowed = " color date datetime datetime-local email month number password search tel text time url week ";
                        return allowed.indexOf(t) >= 0;
                    }

                    return false;
                },
                apply: function ($el, options) {
                    let elType, $wrapper;

                    elType = attrOrProp($el, "type");
                    $el.addClass(options.inputClass);
                    $wrapper = wrapWithWrapperClass($el, options);
                    bindUi($el, $el, options);

                    if (options.inputAddTypeAsClass) {
                        $el.addClass(elType);
                    }

                    return {
                        remove: function () {
                            $el.removeClass(options.inputClass);

                            if (options.inputAddTypeAsClass) {
                                $el.removeClass(elType);
                            }

                            if ($wrapper) {
                                $el.unwrap();
                            }
                        },
                        update: returnFalse
                    };
                }
            },
            {
                // Radio buttons
                match: function ($el) {
                    return $el.is(":radio");
                },
                apply: function ($el, options) {
                    let ds, $div, $span;
                    ds = divSpan($el, options, {
                        divClass: options.radioClass
                    });
                    $div = ds.div;
                    $span = ds.span;

                    // Add classes for focus, handle active, checked
                    bindUi($el, $div, options);
                    bindMany($el, options, {
                        "click touchend": function () {
                            // Find all radios with the same name, then update
                            // them with $.uniform.update() so the right
                            // per-element options are used
                            $.uniform.update($(':radio[name="' + attrOrProp($el, "name") + '"]'));
                        }
                    });
                    classUpdateChecked($span, $el, options);
                    return {
                        remove: unwrapUnwrapUnbindFunction($el, options),
                        update: function () {
                            classClearStandard($div, options);
                            classUpdateChecked($span, $el, options);
                            classUpdateDisabled($div, $el, options);
                        }
                    };
                }
            },
            {
                // Select lists, but do not style multiselects here
                match: function ($el) {
                    if ($el.is("select") && !isMultiselect($el)) {
                        return true;
                    }

                    return false;
                },
                apply: function ($el, options) {
                    let ds, $div, $span, origElemWidth;
//console.log($el);
                    if (options.selectAutoWidth) {
                        sizingInvisible($el, function () {
                            origElemWidth = $el.width();
                        });
//console.log("origElemWidth", origElemWidth);
                    }

                    ds = divSpan($el, options, {
                        divClass: options.selectClass,
                        spanHtml: ($el.find(":selected:first") || $el.find("option:first")).html(),
                        spanWrap: "before"
                    });
                    $div = ds.div;
                    $span = ds.span;

                    if (options.selectAutoWidth) {
                        // Use the width of the select and adjust the
                        // span and div accordingly
                        sizingInvisible($el, function () {
                            // Force "display: block" - related to bug #287
                            swap($([ $span[0], $div[0] ]), {
                                display: "block"
                            }, function () {
                                let spanPad = $span.outerWidth() - $span.width();
                                $div.width(origElemWidth + spanPad);
//                                $div.attr('style', `width: ${origElemWidth + spanPad}px !important`);
                                $span.width(origElemWidth);
//                                $span.attr('style', `width: ${origElemWidth}px !important`);
                            });
                        });
                    } else {
                        // Force the select to fill the size of the div
                        $div.addClass('fixedWidth');
                    }

                    // Take care of events
                    bindUi($el, $div, options);
                    bindMany($el, options, {
                        change: function () {
                            $span.html($el.find(":selected").html());
                            $div.removeClass(options.activeClass);
                        },
                        "click touchend": function () {
                            // IE7 and IE8 may not update the value right
                            // until after click event - issue #238
                            let selHtml = $el.find(":selected").html();

                            if ($span.html() !== selHtml) {
                                // Change was detected
                                // Fire the change event on the select tag
                                $el.trigger('change');
                            }
                        },
                        keyup: function () {
                            $span.html($el.find(":selected").html());
                        }
                    });
                    noSelect($span, options);
                    return {
                        remove: function () {
                            // Remove sibling span
                            $span.remove();

                            // Unwrap parent div
                            $el.unwrap().unbind(options.eventNamespace);
                            return $el;
                        },
                        update: function () {
                            if (options.selectAutoWidth) {
                                // Easier to remove and reapply formatting
                                $.uniform.restore($el);
                                $el.uniform(options);
                            } else {
                                classClearStandard($div, options);

                                // Reset current selected text
                                $span.html($el.find(":selected").html());
                                classUpdateDisabled($div, $el, options);
                            }
                        }
                    };
                }
            },
            {
                // Select lists - multiselect lists only
                match: function ($el) {
                    if ($el.is("select") && isMultiselect($el)) {
                        return true;
                    }

                    return false;
                },
                apply: function ($el, options) {
                    let $wrapper;

                    $el.addClass(options.selectMultiClass);
                    $wrapper = wrapWithWrapperClass($el, options);
                    bindUi($el, $el, options);

                    return {
                        remove: function () {
                            $el.removeClass(options.selectMultiClass);

                            if ($wrapper) {
                                $el.unwrap();
                            }
                        },
                        update: returnFalse
                    };
                }
            },
            {
                // Textareas
                match: function ($el) {
                    return $el.is("textarea");
                },
                apply: function ($el, options) {
                    let $wrapper;

                    $el.addClass(options.textareaClass);
                    $wrapper = wrapWithWrapperClass($el, options);
                    bindUi($el, $el, options);

                    return {
                        remove: function () {
                            $el.removeClass(options.textareaClass);

                            if ($wrapper) {
                                $el.unwrap();
                            }
                        },
                        update: returnFalse
                    };
                }
            }
        ];

    // IE6 can't be styled - can't set opacity on select
    if (isMsie() && !isMsieSevenOrNewer()) {
        allowStyling = false;
    }

    $.uniform = {
        // Default options that can be overridden globally or when uniformed
        // globally:  $.uniform.defaults.fileButtonHtml = "Pick A File";
        // on uniform:  $('input').uniform({fileButtonHtml: "Pick a File"});
        defaults: {
            activeClass: "active",
            autoHide: true,
            buttonClass: "button",
            checkboxClass: "checker",
            checkedClass: "checked",
            disabledClass: "disabled",
            eventNamespace: ".uniform",
            fileButtonClass: "action",
            fileButtonHtml: "Choose File",
            fileClass: "uploader",
            fileDefaultHtml: "No file selected",
            filenameClass: "filename",
            focusClass: "focus",
            hoverClass: "hover",
            idPrefix: "uniform",
            inputAddTypeAsClass: true,
            inputClass: "uniform-input",
            radioClass: "radio",
            resetDefaultHtml: "Reset",
            resetSelector: false,  // We'll use our own function when you don't specify one
            selectAutoWidth: false,
            selectClass: "selector",
            selectMultiClass: "uniform-multiselect",
            submitDefaultHtml: "Submit",  // Only text allowed
            textareaClass: "uniform",
            useID: true,
            wrapperClass: null
        },

        // All uniformed elements - DOM objects
        elements: []
    };

    $.fn.uniform = function (options) {
        let el = this;
        options = $.extend({}, $.uniform.defaults, options);

        // If we are in high contrast mode, do not allow styling
        if (!highContrastTest) {
            highContrastTest = true;

            if (highContrast()) {
                allowStyling = false;
            }
        }

        // Only uniform on browsers that work
        if (!allowStyling) {
            return this;
        }

        // Code for specifying a reset button
        if (options.resetSelector) {
            $(options.resetSelector).mouseup(function () {
                wind.setTimeout(function () {
                    $.uniform.update(el);
                }, 10);
            });
        }

        return this.each(function () {
            let $el = $(this), i, handler, callbacks;

            // Avoid uniforming elements already uniformed - just update
            if ($el.data("uniformed")) {
                $.uniform.update($el);
                return;
            }

            // See if we have any handler for this type of element
            for (i = 0; i < uniformHandlers.length; i = i + 1) {
                handler = uniformHandlers[i];

                if (handler.match($el, options)) {
                    callbacks = handler.apply($el, options);
                    $el.data("uniformed", callbacks);

                    // Store element in our global array
                    $.uniform.elements.push($el.get(0));
                    return;
                }
            }

            // Could not style this element
        });
    };

    $.uniform.restore = $.fn.uniform.restore = function (elem) {
        if (elem === undef) {
            elem = $.uniform.elements;
        }

        $(elem).each(function () {
            let $el = $(this), index, elementData;
            elementData = $el.data("uniformed");

            // Skip elements that are not uniformed
            if (!elementData) {
                return;
            }

            // Unbind events, remove additional markup that was added
            elementData.remove();

            // Remove item from list of uniformed elements
            index = $.inArray(this, $.uniform.elements);

            if (index >= 0) {
                $.uniform.elements.splice(index, 1);
            }

            $el.removeData("uniformed");
        });
    };

    $.uniform.update = $.fn.uniform.update = function (elem) {
        if (elem === undef) {
            elem = $.uniform.elements;
        }

        $(elem).each(function () {
            let $el = $(this), elementData;
            elementData = $el.data("uniformed");

            // Skip elements that are not uniformed
            if (!elementData) {
                return;
            }

            elementData.update($el, elementData.options);
        });
    };
}(this, jQuery));

},{}],


/**
* Jisc  - Function to add an active class - works on classes that JPER doesn't use
*/
18:[function(require,module,exports){   //Function to add an active class - works on classes that JPER doesn't use
// temporary way to add active class

var $ = require('jquery');

if ($('.pattern-library__component-title').length > 0) {

  $('.filter__title__link').each(function() {
    if ($(this).html().toLowerCase() === $('.pattern-library__component-title').html().toLowerCase()) {
      let filter = $(this).closest('.filter');
      filter.addClass('is-open');
    }
  });

  $('.filter.is-open').find('.local-nav li:first a').addClass('active');

}

// widget start

$.widget('ui.pagenav', {

  options: {
    'navSelector': '.in-page-navigation:first',
    'wrapper': '.pattern-library__page-content--nav > .inner',
    'fixedClass': 'in-page-navigation--fixed',
    'offset': 30
  },

  /**
   * The standard jQuery UI _create function
   */
  _create: function() {

    // get the context
    this._self = this;
    this._window = $(window);
    let self = this._self;
    this.fixBottom = false;
    this.lastId;

    this._target = $(self.options.wrapper);
    this._options = self.options;
    this._nav = this._target.find(this._options.navSelector);

    this._timeoutId = null;

  },

  _init: function () {
    let self = this._self;
    let target = this._target;
    let nav = this._nav;

    // window height and nav height
    let wh = $(window).height();
    let nh = nav.outerHeight();

    // work out if we can activate the nav
    if (nh < wh) {

      // temp
      let menuItems = $('.filter.is-open .local-nav a'),
      scrollItems = menuItems.map(function(index, value){
        let item = $('#' + value.href.split('#')[1]);
        if (item.length) {
          return item;
        }
      });

      menuItems.on("click", function(e) {
        let offsetTop = $('#' + $(this).attr('href').split('#')[1]).offset().top;
        $('html, body').stop().animate({
            scrollTop: (offsetTop + 1)
        }, 300);
        e.preventDefault();
      });

      function setSizes() {
        nav.css({
          'position': 'static',
          'transition': 'none',
          'width': 'auto'
        });

        // adjustment values
        let left = nav.offset().left,
        top = parseInt(target.css('padding-top'));

        nav.css({
          'left': left,
          'top': top,
          'width': nav.outerWidth()
        });

        self.scrollHandler(nav, target, menuItems, scrollItems);
      }

      // adding a throttling behaviour
      // ie8 would die occasionally
      function resizeHandler () {
        clearTimeout(self._timeoutId);

        // running a throttled resize
        self._timeoutId = setTimeout(function () {

          setSizes();

        }, 200);

      }

      self._window.on('scroll.win', function(){
        self.scrollHandler(nav, target, menuItems, scrollItems);
      });
      self._window.on('orientationchange.win', resizeHandler);
      self._window.on('resize.win', resizeHandler);
      setSizes();

    }
  },

  scrollHandler: function(nav, target, menuItems, scrollItems) {
    let fromTop = this._window.scrollTop();
    let offset = this.options.offset;

    // scroll
    if (nav.offset().top + nav.height() > $('footer').offset().top) {

      nav.css({
        'position': 'absolute',
        top: $('footer').offset().top  - (nav.height() + offset)
      });
      this.fixBottom = true;
    }
    else if ( nav.offset().top > parseInt(fromTop) ) {
      nav
        .css({
        'position': 'fixed',
        top: offset + 'px'
      });
      this.fixBottom = false;
    }

    if (!this.fixBottom) {
      if (parseInt(fromTop) > target.offset().top) {
        nav
          .css({
            'position': 'fixed'
        });
      } else {
        nav
          .css({
          'position': 'static'
        });
      }
    }



    // Get id of current scroll item
    let cur = scrollItems.map(function(){
      if ($(this).offset().top < fromTop)
        return this;
    });

    // Get the id of the current element
    cur = cur[cur.length-1];
    let id = cur && cur.length ? cur[0].id : '';

    if (this.lastId !== id) {
      this.lastId = id;
      // Set/remove active class
      if (id != '') {
        menuItems.each(function() {
          let $this = $(this);
          $this.removeClass('active');
          if ($this.attr('href').match(id)) {
            $this.addClass('active');
          }
        });
      }
    }

  },

  _destroy: function () {
    this._window.off('resize.win');
    this._window.off(' orientationchange.win');
    this._window.off('scroll.win');
    this._nav.css({
      'position': 'static',
      'width': 'auto'
    });
  }

});

},{}],


/**
* jquery.jisc.mobile-inpagenav - Not clear what it does - maybe something to do with accordion or menu on Mobile devices
*/
19:[function(require,module,exports){   // jquery.jisc.mobile-inpagenav - maybe something to do with accordion or menu on Mobile devices
'use strict';
var Collapsible = require('../show-hide/jquery.jisc.show_hide');
var $ = require('jquery');

// widget start

$.widget('ui.pagenav_mobile', {

  options: {
    'triggerWrap': '<span class="filter-panel__title"><span class="filter-panel__title__text">Contents</span></span>',
    'contentWrap': '<div class="show_hide__target"/>',
    'triggerClass': 'show_hide__trigger',
    'collapsibleClass': 'is-collapsible show_hide__container'
  },

  /**
   * The standard jQuery UI _create function
   */
  _create: function() {
    // get the context
    this._self = this;

    // get the contents of the element
    this._contents = this.element.children();

    // wrapitallup
    this._contents.wrapAll(this.options.contentWrap);

    // create a trigger
    this.trigger = $(this.options.triggerWrap);
    this.trigger.addClass(this.options.triggerClass);

    // inject it
    this.element
      .prepend(this.trigger)
      .addClass(this.options.collapsibleClass);

    // make it collapsible - apply the already present collapsibles to the section
    this.element.collapsible();
  },

  // break it all down again
  _destroy: function () {
    // check for the presence of the wrapper before unwrapping
    // or you'll unravel your entire website : )
    if (this.element.find('.' + this.options.triggerClass)) {
      this._contents.unwrap();
      this.trigger.remove();
    }

    // remove collapsible using it's own destroy method
    this.element.collapsible('destroy');
    this.element.removeClass(this.options.collapsibleClass);
  }

});

},{"../show-hide/jquery.jisc.show_hide":32}],


/**
* Jisc function looks like something to do with  navigation (menu) management
*/
20: [
function(require,module,exports){   // *5* Looks like something to do with  navigation (menu) management [INVESTIGATE?]
    'use strict';
    var $ = require('jquery');
    require('jquery-ui');

    var breakpoints = require('../core/js/breakpoints');
    var Conduct = require('conduct.js');

// Grab the options spec from the pagination widget
var getDOMConfig = require('../core/js/getDOMConfig');
var options = require('./jquery.jisc.inpagenav');
var mobile_nav = require('./jquery.jisc.mobile-inpagenav');

    /**
     * Helper function to intialise the main nav dropdowns
     */
    function setupInpagenav(item) {
      item.pagenav({
        wrapper: '.pattern-library__page-content--nav > .inner'
      });
    }

    /**
     * Helper function to destroy the main nav dropdowns
     */
    function destroyInpagenav(item) {
      item.pagenav('destroy');
    }

    /**
     * Helper function to intialise toggle menu on mobile
     */
    function setupInpagenavMobile(item) {
      item.pagenav_mobile();
    }

    /**
     * Helper function to destroy the main nav dropdowns
     */
    function destroyInpagenavMobile(item) {
      item.pagenav_mobile('destroy');
    }

    $('[data-pagenav]').each(function(index, item) {
      let $item = $(item);
      let settings = getDOMConfig($item, options);

      let conduct = new Conduct({
        'media_queries': [{
            query: 'screen and (min-width:' + breakpoints.outer + 'px)',
            fallback: true,
            match: function() {
              if (!Modernizr.touch) {
                setupInpagenav($item);
              }
            },
            unmatch: function() {
              if (!Modernizr.touch) {
                destroyInpagenav($item);
              }
            }
          },
          {
            query: 'screen and (max-width:' + (breakpoints.outer - 1) + 'px)',
            match: function() {
              setupInpagenavMobile($item);
            },
            unmatch: function() {
              destroyInpagenavMobile($item);
            }
          }
        ]
      });
    });
  },
{"../core/js/breakpoints": 10,
 "../core/js/getDOMConfig": 11,
 "./jquery.jisc.inpagenav": 18,
 "./jquery.jisc.mobile-inpagenav": 19,
 "conduct.js": 1,
 "jquery": "jquery",
 "jquery-ui": 3}
],


/**
*
*/
24:[function(require,module,exports){   // jisc.mobilemenu_focussed - Mobile menu plugin
var $ = require('jquery');
require('jquery-ui');

/**
 * Mobile menu plugin
 */
$.widget('jisc.mobilemenu_focussed', {

  options: {
    templates: {
      focussed: '<span class="menu-button" tabindex="0">Menu <span class="icon icon-arrow-down"></span></span>',
      mobileMenu: '<div class="mobile-menu mobile-tablet-only" />'
    },
    domElements: {
      insertPoint: '.title-nav',
      bottomNav: '.masthead__nav--primary > ul'
    }

  },

/**
 * The standard jQuery UI _create function
 */
  _create: function(event) {
    //  needs to have a 'focussed' class else bail out
    if (!this.element.hasClass('masthead--focussed')) {
      event.preventDefault();
      return;
    }

    let self = this;

    // find the insertion point for the menu button
    this._titleNav = this.element.find(this.options.domElements.insertPoint);

    // create menu button
    this._menuButton = $(this.options.templates.focussed);

    // add button at insertion point
    this._titleNav.append(this._menuButton);

    // create mobile menu wrapper
    this._mobileMenu = $(this.options.templates.mobileMenu);

    // bind event handlers
    this._on(this._menuButton, {
      'click': this._clickHandler,
      'keydown': this._keyboardHandler
    });

    // duplicate them if needed - saves destroying the menu and re-making it each time
    this._topNav = this._titleNav.find('.submenu > ul').clone();
    this._bottomNav = this.element.find(this.options.domElements.bottomNav).clone();

    // add mobile menu and populate it
    this._titleNav.append(this._mobileMenu);
    this._mobileMenu
      .append(this._topNav)
      .append(this._bottomNav);

    // remove classes and add nav__item
    this._mobileMenu.find('li')
      .removeClass()
      .addClass('nav__item');

  },


  _clickHandler: function () {
    this._mobileMenu.slideToggle(200);
    this._menuButton.toggleClass('is-open');
  },

  _keyboardHandler: function (e) {
    e.preventDefault();
    if (e.keyCode === 13) {
      this._clickHandler();
    }
  },

  /**
    Remove all handlers and clean up
   */
  destroy: function() {


  }

});

},{"jquery":"jquery","jquery-ui":3}],


/**
*
*/
25:[function(require,module,exports){   // jisc.mobilemenu - something to do with mobile menu
var $ = require('jquery');
require('jquery-ui');

/**
 * Mobile menu plugin
 */
$.widget('jisc.mobilemenu', {

  options: {
    templates: {
      menuButton: '<span class="menu-button" tabindex="0">Menu <span class="icon icon-arrow-down"></span></span>'
    },
    domElements: {
      insertPoint: '.nav-wrapper'
    }

  },

/**
 * The standard jQuery UI _create function
 */
  _create: function() {
    let self = this;
    // find the insertion point for the menu button
    this._navWrapper = this.element.find(this.options.domElements.insertPoint);
    this._menuButton = $(this.options.templates.menuButton);
    this._navWrapper.before(this._menuButton);

    this._on(this._menuButton, {
      'click': this._clickHandler,
      'keydown': this._keyboardHandler
    });
  },

  _clickHandler: function () {
    this._navWrapper.slideToggle(200);
    this._menuButton.toggleClass('is-open');
  },

  _keyboardHandler: function (e) {
    e.preventDefault();
    if (e.keyCode === 13) {
      this._clickHandler();
    }
  },

  /**
    Remove all handlers and clean up
   */
  destroy: function() {
  }

});

},{"jquery":"jquery","jquery-ui":3}],


/**
*
*/
26:[function(require,module,exports){   // *7* Jisc controller for nav dropdowns and mobile menu [NEEDED]
/**
 * @fileOverview Controller for the primary nav dropdowns and mobile menu
 */

var $ = require('jquery');
require('jquery-ui');

var breakpoints = require('../core/js/breakpoints');
var Conduct = require('conduct.js');
//var loadDesktopImages = require('../core/js/load-desktop-images');
require('./jquery.jisc.mobilemenu');
require('./jquery.jisc.mobilemenu-focussed');

// use a data attribute to target this to make it independent of classnames
let $nav = $('[data-dropdown]');
let $navMobile = $('[data-mobilemenu]');
let $navMobileFocussed = $('[data-mobilemenu-focussed]');



/**
 * Helper function to set up the mobile menu
 */
function setupMainNavSmall() {
  $navMobile.mobilemenu();
  $navMobileFocussed.mobilemenu_focussed();
}

/**
 * Helper function to destroy the mobile menu
 */
function destroyMainNavSmall() {
  if ($navMobile.is(':jisc-mobilemenu')) {
    $navMobile.mobilemenu('destroy');
  }
  if ($navMobileFocussed.is(':jisc-mobilemenu_focussed')) {
    $navMobileFocussed.mobilemenu_focussed('destroy');
  }
}

/**
 * Initialise / destroy the menu plugins at different breakpoints
 */
var conduct = new Conduct({
  'media_queries': [
//    {
//      query: 'screen and (min-width:' + breakpoints.outer + 'px)',
//      fallback: true,
//      match: function() {
//        loadDesktopImages($nav);
//      },
//      unmatch: function(){}
//    },
    {
      query: 'screen and (max-width:' + (breakpoints.outer - 1) + 'px)',
      match: setupMainNavSmall,
      unmatch: destroyMainNavSmall
    }
  ]
});

},
{"../core/js/breakpoints":10,
// "../core/js/load-desktop-images":12,
 "./jquery.jisc.mobilemenu":25,
 "./jquery.jisc.mobilemenu-focussed":24,
 "conduct.js":1,
 "jquery":"jquery",
 "jquery-ui":3}],


/**
*
*/
32:[function(require,module,exports){   // $.jisc.show_hide
var $ = require('jquery');
require('jquery-ui');

/**
 * @fileOverview A jQuery UI Widget to show and hide show_hide sections of a page
 * @author Andy Mantell
 * @name $.jisc.show_hide
 * @dependencies: jQuery, jQuery UI widget factory
 */

/**
 * show_hide sections
 *
 * This plugin fires events for create, destroy, collapse, expand which can be listened to in one of two ways:
 *
 * // Using a listener
 * $(':jisc-show_hide').on('show_hideexpand', function() {})
 *
 * // Passing in a callback to the widget
 * $('.foo').show_hide({ expand: function() { ... }})


 */

  $.widget("jisc.show_hide", {

    options: {
      triggerSelector: '.show_hide__trigger:eq(0)',
      targetSelector: '.show_hide__target:eq(0)',
      expandedClass: 'show_hide--is-expanded',
      collapsedClass: 'show_hide--is-collapsed',
      containerClass: 'show_hide__container',
      effectDuration: 250
    },

    /**
     * The standard jQuery UI create function
     * Set up our variables and events
     */
    _create: function() {

      // get the context
      this._self = this;

      // get the vars
      this._container = $(this.element);
      this._show_hide_target = this._container.find(this.options.targetSelector);

      // Grab our trigger

      this._show_hide_trigger = this._container.find(this.options.triggerSelector);


      // Store our original trigger before we modify it, to be restored on destroy
      this._original_show_hide_trigger = this._show_hide_trigger.clone(true, true);

      // Make a link to put inside the trigger for keyboarders
      // @TODO: Consider use of ARIA roles and tabindex=0 to make headings directly focusable clickable?
      // Is using an <a> tag here to get that focusablility and interactivity technically (in)correct?
      // What is support for these ARIA roles like?
      let $trigger_link = $('<a href="#"></a>');
      $trigger_link.on('click', function(e) {
        e.preventDefault();
      });

      // Wrap the trigger in this link
      this._show_hide_trigger.wrapInner($trigger_link);

      // Set up the events
      this._on(this._show_hide_trigger, { 'click': this.toggle });

      this._trigger('create');
    },

    /**
     * Standard jQuery UI init function
     */
    _init: function() {

      // If the target isn't marked as expanded, then collapse it
      if(!this._container.hasClass(this.options.expandedClass)) {
        this.collapse(0);
      }

      this._container.addClass(this.options.containerClass);
    },

    /**
     * Main toggle function
     * Used as a click handler on the _show_hide_trigger
     */
    toggle: function(e) {

      if(typeof(e) !== 'undefined') {
        e.preventDefault();
      }

      if(this._container.hasClass(this.options.expandedClass)) {
        this.collapse();
      } else {
        this.expand();
      }
    },

    /**
     * Helper function to collapse the _show_hide_target
     */
    collapse: function(duration) {

      let self = this;

      // Allow this function to take an optional effect duration. Used to instantly hide sections on _create()
      if(typeof(duration) === 'undefined') {
        duration = this.options.effectDuration;
      }

      // Collapse the section
      this._show_hide_target
        .slideUp(duration, function() {

          // Switch the appropriate classes once the animation has finished
          self._container
            .addClass(self.options.collapsedClass)
            .removeClass(self.options.expandedClass);
        });

      this._trigger('collapse');
    },

    /**
     * Helper function to expand the _show_hide_target
     */
    expand: function(duration) {

      let self = this;

      // Allow this function to take an optional effect duration. Used to instantly hide sections on _create()
      if(typeof(duration) === 'undefined') {
        duration = this.options.effectDuration;
      }

      // Expand the section
      this._show_hide_target
        .slideDown(duration, function() {

          // Switch the appropriate classes once the animation has finished
          self._container
            .addClass(self.options.expandedClass)
            .removeClass(self.options.collapsedClass);
        });

      this._trigger('expand');
    },

    /**
     * Tear everything down again.
     */
    destroy: function() {

      // Remove the click handler from the trigger
      this._off(this._show_hide_trigger, 'click');

      // Restore our original trigger, without the wrapping <a>
      this._show_hide_trigger.replaceWith(this._original_show_hide_trigger);

      // Remove all classes from the container
      this
        ._container
        .removeClass(this.options.containerClass)
        .removeClass(this.options.collapsedClass)
        .removeClass(this.options.expandedClass);

      // Make sure the content is visible again
      this._show_hide_target.show();

      this._trigger('destroy');

      // call the base destroy function
      $.Widget.prototype.destroy.call(this);
    },

    /**
     * The standard jQuery UI _setOption function
     */
    _setOption: function(key, value) {
      this._super( key, value );
    }

  });

},{"jquery":"jquery","jquery-ui":3}],


/**
*
*/
33:[function(require,module,exports){   // *10* Controller for show-hide accordions
// JavaScript Document'use strict';
var $ = require('jquery');
var getDOMConfig = require('../core/js/getDOMConfig');

// Grab the options spec from the pagination widget
var options = require('./jquery.jisc.show_hide');

$('[data-collapsible]').each(function(index, item) {
  let $item = $(item);

  // Based on the "options spec" provided by the plugin, grab any overrides
  // from the DOM
  let settings = getDOMConfig($item, options);

  $item.collapsible(settings);
});
},{"../core/js/getDOMConfig":11,"./jquery.jisc.show_hide":32,"jquery":"jquery"}],


/**
*
*/
34:[function(require,module,exports){   // $.jisc.cx_rwdtable - Table functions
/**
* @fileOverview Scripts for the tables test page
* @author Maggie Wachs, www.filamentgroup.com, revised by Russell Kirkland
* @name $.jisc.cx_rwdtable
* @requires jQuery, jQuery UI widget factory
*/

var $ = require('jquery');
require('jquery-ui');


$.widget( 'jisc.rwdtable', {

  options: {
    idprefix: null,   // specify a prefix for the id/headers values
    persist: null, // specify a class assigned to column headers (th) that should always be present; the script not create a checkbox for these columns
    checkContainer: null // container element where the hide/show checkboxes will be inserted; if none specified, the script creates a menu
  },

  /**
   * The standard jQuery UI _create function
   */
  _create: function() {

    let self = this,
      o = self.options;

      self.element.wrap('<div class="table-wrap table-wrap--responsive">');
      let outer = self.element.parent('.table-wrap');
      let table = outer.find('table');
      let thead = table.find('thead');
      let tbody = table.find('tbody');
      let tfoot = table.find('tfoot');
      let hdrCols = thead.find('th');
      let bodyRows = tbody.add(tfoot).find('tr');
      let container = o.checkContainer ? $(o.checkContainer) : $('<div class="table-menu"><ul /></div>');

    // private vars
    this._table = table;
    this._container = container;
    this._timeoutId = null;
    this._windowWidth = 0;

    // add class for scoping styles - cells should be hidden only when JS is on
    table.addClass('enhanced');
    outer.addClass('table-menu-hidden');

    hdrCols.each(function(i){
      let th = $(this),
        id = th.attr('id'),
        classes = th.attr('class');

      // assign an id to each header, if none is in the markup
      if (!id) {
        id = ( o.idprefix ? o.idprefix : 'col-' ) + self.uuid + '-' + i;
        th.attr('id', id);
      }

      if (!classes) {
        th.addClass('unspecified');
        classes = th.attr('class');
      }

      // assign matching "headers" attributes to the associated cells
      // TEMP - needs to be edited to accommodate colspans
      bodyRows.each(function(){
        let cell = $(this).find('th, td').eq(i);
        cell.attr('headers', id);
        if (classes) {
          cell.addClass(classes);
        }
      });

      // create the hide/show toggles
      if ( !th.is('.' + o.persist) ) {
        let toggle = $('<li><input type="checkbox" name="toggle-cols" id="toggle-' + id + '" value="' + id + '" /> <label for="toggle-' + id + '">'+th.text()+'</label></li>');

        container.find('ul').append(toggle);

        toggle.find('input')
          .on("change", function(){
            let input = $(this),
              val = input.val(),
              cols = table.find('#' + val + ', [headers='+ val +']');

            if (input.is(':checked')) {
              cols.show();
              cols.removeClass('rwd-hid');
              cols.addClass('rwd-vis');
            } else {
              cols.hide();
              cols.removeClass('rwd-vis');
              cols.addClass('rwd-hid');
            }

            // trigger update event
            container.trigger('inputChange');
          })
          .on('updateCheck', function(){

            if (th.is(':visible')) {
              $(this).prop('checked', true);
            }
            else {
              $(this).prop('checked', false);
            }

            // trigger update event
            container.trigger('inputChange');
          })
          .trigger('updateCheck');
      }

    }); // end hdrCols loop

    // Bind resize and orientation change handlers
    this._on(this.window, {'resize': this._resizeHandler, 'orientationchange': this._resizeHandler});

    // if no container specified for the checkboxes, create a "Display" menu
    if (!o.checkContainer) {
      let iconElem;
      let menuWrapper = $('<div class="table-menu-wrapper" />'),
      menuBtn = $('<a href="#" class="table-menu-btn"><span class="label">Show columns</span> <span class="icon icon-arrow-down"></a>');

      menuBtn.on("click", function(){
        iconElem = $('.icon', menuBtn);
        if ( iconElem.hasClass('icon-arrow-down') ) {
          iconElem.removeClass('icon-arrow-down').addClass('icon-chevron-up');
        }
        else {
          iconElem.removeClass('icon-arrow-up').addClass('icon-chevron-down');
        }

        outer.toggleClass('table-menu-hidden');

        return false;
      });

      menuWrapper.append(menuBtn).append(container);
      table.before(menuWrapper);

      // bind label text to input change
      container.on('inputChange', function() {
        let hiddenCols = container.find('[type=checkbox]').not(':checked').length,
            menuLabel = menuBtn.find('.label');

        if (hiddenCols) {
          menuLabel.text('Show ' + hiddenCols + ' more columns');
        } else {
          menuLabel.text('Hide columns');
        }



      });


      // assign click-to-close event
      $(document).on("click", function(e){
        if ( !$(e.target).is( container ) && !$(e.target).is( container.find('*') ) ) {
          outer.addClass('table-menu-hidden');
        }
      });
    }

    // Kick off an initial calculation of what to show
    this._resizeHandler();

  }, // end _create


  _resizeHandler: function(event) {

    let self = this;

    // Only run if the window width has actually changed to curb the infinite loop in IE8
    if(this._windowWidth === $(window).width()) {
      event.preventDefault();
      return;
    }

    this._windowWidth = $(window).width();

    // show/hide optional columns
    clearTimeout(this._timeoutId);
    this._timeoutId = setTimeout(function() {
      self._showHideOptional();
    }, 250);
  },

  // show/hide optional columns
  _showHideOptional: function() {
    // get the context
    let self = this;

    // get the optional and show them
    let optional = $('.optional', this._table),
      unspecified = $('.unspecified', this._table),
      toggles = $('input[name=toggle-cols]', this._table.parent());

    // show all columns on resize
    optional.show();
    optional.removeClass('rwd-hid');
    optional.addClass('rwd-vis');
    unspecified.show();
    unspecified.removeClass('rwd-hid');
    unspecified.addClass('rwd-vis');

    // First hide optional columns if the table is too wide for it's container
    if ($(self._table).outerWidth(true) > $(self._table).parent().width()) {
      optional.hide();
      optional.removeClass('rwd-vis');
      optional.addClass('rwd-hid');
    }

    // If the table is too wide, hide the columns which weren't specified as either optional of essential
    if ($(self._table).outerWidth(true) > $(self._table).parent().width()) {
      unspecified.hide();
      unspecified.removeClass('rwd-vis');
      unspecified.addClass('rwd-hid');
    }

    toggles.trigger('updateCheck');
  },


  /**
   * The standard jQuery UI _setOption function.
   */
  _setOption: function(key, value) {
    this._super( key, value );
  }

});

},{"jquery":"jquery","jquery-ui":3}],


/**
*
*/
35:[function(require,module,exports){   // $.jisc.sortableRwdtable - Jisc sortable table
/**
 * @fileOverview Sortable table script
 * @author Jon Brace
 * @name $.jisc.sortableRwdtable
 * @requires jQuery, jQuery UI widget factory, jisc.rwdtable
 */

var $ = require('jquery');
require('jquery-ui');

$.widget( 'jisc.sortableRwdtable', $.jisc.rwdtable, {

  zeroOffset: 1, // By default tables have a non-sortable first column, but this may be overridden by including data-sortable-col-zero in the <table> element
  currentHeadingIndex: -1,
  direction: 1,

  options: {
    iconsClasses: {
      up: 'icon-caret-up',
      down: 'icon-caret-down'
    }
  },

  _create: function() {
    this._applyHeadingLinks();
    this._setDefault();
    this._super();
  },

  /**
   * Set the initial sort order.  This will re-render the table
   * but will be easier to use.
   *
   * @private
   */
  _setDefault: function() {
    this.zeroOffset = "undefined" == typeof this.element.data("sortable-col-zero")? 1 : 0;
    let defaultIndex = $('thead th', this.element).index($('th[data-sort-default]'));
      // defaultIndex.find('a').append('<span class="icon ' + iconClass + ' icon--sortable-head"></span>');
    if ( defaultIndex !== -1) {
      this._sortRows(defaultIndex - this.zeroOffset);
    }

  },

  /**
   * Add the links to the thead elements to allow user
   * to click to sort.
   * @private
   */
  _applyHeadingLinks: function() {

    let self = this;
    let innerLink;

    $('thead > tr > th', this.element).each(function() {

      innerLink = $('<a />', {href: '#'}).on('click', self._sortClick.bind(self));

      $(this).wrapInner(innerLink);
    });

  },

  /**
   * Default sort value is the actual text value of the table
   * cell. We need to clean it up as much as possible to use it
   * as such.
   * @param value
   * @returns {*}
   * @private
   */
  _cleanHtml: function(value) {
    return value.replace(/(\r\n|\n|\r)/gm, '').trim();
  },

  /**
   * Add icon to the link
   * @param elem
   * @private
   */
  _applyIcon: function(elem) {

    let iconClass;
     // Add aria-expanded set to true
     // self._collapsible_trigger.children().attr("aria-expanded", "false");

	  // Set visually hidden text to open panel
      //self._collapsible_trigger.children().children(".visuallyhidden").text("[Open panel below]");
    $('thead > tr > th:eq("' + (this.currentHeadingIndex + this.zeroOffset) + '")', this.element).find('span.icon').remove();

    if ( this.direction === 1 ) {
      iconClass = this.options.iconsClasses.up;
    }
    else {
      iconClass = this.options.iconsClasses.down;
    }

    elem.find('a').append('<span class="icon ' + iconClass + ' icon--sortable-head"></span>');
  },

  /**
   * Sort the rows on column defined by index
   * @param headingIndex
   * @private
   */
  _sortRows: function(headingIndex) {
    let self = this;
    let trElems = $('tbody > tr', this.element).detach();
    if ( this.currentHeadingIndex === headingIndex ) {
      this.direction = this.direction * -1;
    }
    this._applyIcon($('thead > tr > th:eq("' + (headingIndex + this.zeroOffset) + '")', this.element));
    this.currentHeadingIndex = headingIndex;

    /*
     * Use JS's sort function to sort the jQuery tr elements
     */
    trElems.sort(function(a, b) {

      let compareElems = [a, b];

      /*
       * Need to find the value in the row's table cell to
       * use as the sort value.
       */
      compareElems = $.map(compareElems, function(elem) {

        let tdElem = $(elem).find('td:eq("' + headingIndex + '")');

        /*
         * If td has `sortValue` data attribute, then use that
         * as the sort value.
         */

        if ( tdElem.data('sort-value') ) {
          return tdElem.data('sort-value');
        }

        return self._cleanHtml(tdElem.html());

      });

      let sortVal;

      /*
       * The sort function.
       */
      if (compareElems[0] < compareElems[1]) {
        sortVal = -1;
      }
      else if (compareElems[0] > compareElems[1]) {
        sortVal = 1;
      } else {
        sortVal = 0;
      }

      /*
       * Adjust sort value to include direction of sort
       */
      return sortVal * self.direction;
    });

    /*
     * Replace the table body
     */
    $('tbody', this.element).append(trElems);
  },

  /**
   * Table heading link has been clicked on.
   * @param e
   * @private
   */
  _sortClick: function(e) {

    // get index of the selected column
    let index = $('thead > tr > th', this.element).index($(e.currentTarget).parent('th')) - this.zeroOffset;
    this._sortRows(index);
    e.preventDefault();
  }
});

if(typeof String.prototype.trim !== 'function') {
  String.prototype.trim = function() {
    return this.replace(/^\s+|\s+$/g, '');
  };
}

},{"jquery":"jquery","jquery-ui":3}],


/**
*
*/
36:[function(require,module,exports){   // *11* Controller for jisc table
var $ = require('jquery');
require('./jquery.jisc.rwdtable');
require('./jquery.jisc.sortable-rwdtable');

let config = {
  idprefix: 'co-',
  persist: 'persist'
};

$('.data-table, .content-table, [data-rwdtable]').each(function() {
  if ( typeof $(this).data('rwdtable-sortable') !== 'undefined' ) {
    $(this).sortableRwdtable(config);
  }
  else {
    $(this).rwdtable(config);
  }
});

},{"./jquery.jisc.rwdtable":34,"./jquery.jisc.sortable-rwdtable":35,"jquery":"jquery"}],


/**
*
*/
37:[function(require,module,exports){   // $.ui.teaserblocks - set teasers to equal height
/**
 * @fileOverview A jQuery UI Widget to set headers and wrappers in a container to equal height
 * @author Stefan Goodchild
 * @name $.ui.teaserblocks
 * @OPTIMIZE: There are lots of repeated selector lookups in this plugin, inside a function that is run on window resize. These ought really to be cached to improve performance
 */

'use strict';

var $ = require('jquery');
require('jquery-ui');

let options = {
  breakpoint_inner: 565,
  breakpoint_outer: 768,
  resize_throttle: 50
};

module.exports = options;

$.widget('ui.teaserblocks', {

  options: options,

  /**
   * Widget constructor.
   *
   * @private
   */
  _create: function () {
    /** The standard jQuery UI _create function. Sets resize listener to trigger functions based on breakpoint and triggers initial resize */
    let self = this;
    this.timeout = '';

    // Keep track of the width of the window between resize events so that we know whether the expensive resize function needs to run
    self._windowWidth = 0;
    self._reset_heights();
    // IE8 runs this resize event in an infinite loop, since changing the size of something inside a resize event
    // triggers the resize event in IE8!
    // To protect against this slightly, IE8 gets a much higher timeout than other browsers

    if ($('html').hasClass('ie8')) {
      self.options.resize_throttle = 500;
    }

    // Listen for the window resize event, clear then set a timeout to throttle the resizing.
    $(window).resize(function () {
      clearTimeout(self.timeout);
      if ($(window).width() >= self.options.breakpoint_inner) {
        self.timeout = setTimeout(function () {
          self._resize($(self.element));
        }, self.options.resize_throttle);
      } else {
        self.timeout = setTimeout(function () {
          self._reset_heights();
        }, self.options.resize_throttle);
      }
    });

    // Dont trigger the resize until the fonts are loaded otherwise the heights will be wrong.
    $(window).bind('load', function () {
      if ($(window).width() >= self.options.breakpoint_inner) {
        setTimeout(function () {
          self._resize($(self.element));
        }, 0);
      }
    });
  },

  /**
   * Triggers the appropriate resize function
   *
   * @param {jQuery} $el The jQuery object for the wrapper element
   * @private
   */
  _resize: function ($el) {

    let winWidth = $(window).width();
    // Don't run this slightly expensive function if the window width hasn't actually changed
    // Initially conceived as additional protection against crashing IE8 but it makes sense not to run this function
    // in *any* browser if there is nothing to actually do!
    // The main effect of this is that in IE8 it will stop the resize event from running infinitely (Which occurs when things change dimensions inside a resize event in IE8)
    if (this._windowWidth === winWidth) {
      return;
    }

    this._windowWidth = winWidth;

    let blocks = {};
    //blocks = $el.find('.block');

    // If in the inbetween state where some blocks are 50% only affect the last two
    if (this._windowWidth <= this.options.breakpoint_outer && this.element.hasClass('region--3-up')) {
      blocks = $el.find('.block').not('.block-1');
    } else {
      blocks = $el.find('.block');
    }

    this._reset_heights(blocks);

    if (blocks.hasClass('has-inner')) {
      this._resize_inner(blocks);
      return;
    }

    if (blocks.length > 1) { // ignore blocks in one up layouts
      this._resize_header(blocks);
      this._resize_copy(blocks);
      this._resize_block(blocks);
    }

    if (this._windowWidth >= this.options.breakpoint_outer && this.element.hasClass('js-equal-blocks')) {
      this.element.find('.box__inner').height('auto');
    }
  },

  /**
   * Scans through elements within the row and resets height attributes to auto.
   *
   * @param {jQuery} The jQuery object for the teasers within the wrapper element
   * @private
   */
  _reset_heights: function () {
    let self = this;

    if (self.element.hasClass('js-equal-blocks')) {
      this._resize_panels(self.element);
      return;
    }

    let $blocks = self.element.find('.block');

    $.each($blocks, function (i, b) {
      let $b = $(b);
      $b.find('.teaser__title').height('auto');
      $b.find('> :first-child').height('auto');
      $b.find('.teaser__body').height('auto');
      $b.find('.box__inner').height('auto');
    });
  },


  /**
   * Scans for elements with the class .teaser__title, works out which is currently the tallest then sets all the other to the same height.
   * Ignores headers in teasers on the front page until desired behaviour is decided.
   *
   * @param {jQuery} The jQuery object for the teasers within the wrapper element
   * @private
   */
  _resize_header: function ($blocks) {

    let h_height = 0;

    $.each($blocks, function (i, b) {
      let $b = $(b);
      if ($b.find('.teaser__title').innerHeight() > h_height) {
        h_height = $b.find('.teaser__title').innerHeight();

      }
    });

    if (($blocks.find('.teaser-home').length === 0) && ($blocks.find('.has-media--side').length === 0)) {
      $.each($blocks, function (i, b) {
        $(b).find('> :first-child .teaser__title').innerHeight(h_height + 'px');
      });
    }
  },

  /**
   * Scans for wrapper elements, works out which is currently the tallest then sets all the other to the same height
   *
   * @param {jQuery} $blocks The jQuery object for the teasers within the wrapper element
   * @private
   */
  _resize_copy: function ($blocks) {
    /*
     */
    let c_height = 0;

    $.each($blocks, function (i, b) {
      let $b = $(b);
      if ($b.find('.media').height() > c_height) {
        c_height = $b.find('.media').height();
      }
    });

    if ($blocks.find('.teaser-home').length !== 0) {
      $.each($blocks, function (i, b) {
        let $b = $(b);
        if (($b.find('.teaser__body').length !== 0) && ($b.find('.teaser-home__text-only').length === 0)) {
          if ($b.find('.teaser__body').innerHeight() < c_height) {
            $b.find('.teaser__body').innerHeight(c_height + 'px');
          }
        }
      });
    }

  },

  /**
   * Scans for wrapper elements, works out which is currently the tallest then sets all the other to the same height
   *
   * @param {jQuery} The jQuery object for the teasers within the wrapper element
   * @private
   */

  _resize_block: function ($blocks) {

    let b_height = 0;

    $.each($blocks, function (i, b) {
      let $b = $(b);
      if ($b.find('> :first-child').innerHeight() > b_height) {
        b_height = $b.find('> :first-child').innerHeight();
      }
    });

    $.each($blocks, function (i, b) {
      $(b).find('> :first-child').innerHeight(b_height + 'px');
    });
  },

  /**
   * Scans for wrapper elements, works out which is currently the tallest then sets all the other to the same height
   *
   * @param {jQuery} The jQuery object for the teasers within the wrapper element
   * @private
   */
  _resize_panels: function ($blocks) {

    let h_height = 0;
    $blocks = $blocks.find('.box__inner');

    $.each($blocks, function (i, b) {
      let $b = $(b);
      $b.height('auto');
      if ($b.innerHeight() > h_height) {
        h_height = $b.innerHeight();
      }
    });

    $.each($blocks, function (i, b) {
      $(b).innerHeight(h_height + 'px');
    });
  },

  /**
   * Scans for inner elements, works out which is currently the tallest then sets all the other to the same height
   *
   * @param {jQuery} The jQuery object for the teasers within the wrapper element
   * @private
   */
  _resize_inner: function ($blocks) {

    let h_height = 0;

    $.each($blocks, function (i, b) {
      let $b = $(b).find('.box__inner');

      if ($b.innerHeight() > h_height) {
        h_height = $b.innerHeight();

      }
    });

    $.each($blocks, function (i, b) {
      $(b).find('.box__inner').innerHeight(h_height + 'px');
    });
  },

  /**
   * The standard jQuery UI _destroy function. Clears window resize listener and resets heights to auto
   */
  destroy: function () {

    $(window).unbind('resize');

    let blocks = $(this.element).find('.block');
    this._reset_heights(blocks);

  },

  /**
   * The standard jQuery UI _setOption function.
   * @private
   */
  _setOption: function (key, value) {
    this._super(key, value);
  }

});

},{"jquery":"jquery","jquery-ui":3}],


/**
*
*/
38:[function(require,module,exports){   // *12* Something to do with teaserblocks

var getDOMConfig = require('../core/js/getDOMConfig');
var options = require('./jquery.teaser.js');

var $ = require('jquery');

$('[data-equal-height]').each(function(index, item) {
  let $item = $(item);

  let settings = getDOMConfig($item, options);

  $item.teaserblocks(settings);
});

},{"../core/js/getDOMConfig":11,"./jquery.teaser.js":37,"jquery":"jquery"}],



"jquery":[function(require,module,exports){ // JQuery v1.11.2
//console.log("***JQuery***");
module.exports = jQuery;
},

{}]},{},[6,16,20,26,33,36,38]);
