/**
 * Renders JSON as an expandable/collapsable tree structure.
 *
 * Based on original JSONViewer - by Roman Makudera 2016 (c) MIT licence.

Author: Jisc
 */
var JSONViewer = (function(document) {

	/** @constructor */
	function JSONViewer(parentEl, jsonValue, collapseAt) {
//let _date = new Date("2020-03-01")
//jsonValue = {"id":14255, "subject":["the", "cat sat", "on", "the mat"], "emtlist": [], "content":{},"metadata":{"publication_status":null,"accepted_date":_date,"journal":{"identifier-2-else-one-empty":[{"type":"pissn","id":"0959-8138"},{}, [123, "aaa", null, {}, []]]}}};
		this._dom_container = document.createElement("div");
		this._dom_container.classList.add("json-viewer");

        // Click handler for Expanding/Collapsing part of JSON tree
        function _toggleJSON(e) {
            e.stopPropagation();
            // If a key press (NOT a click) and NOT Space (32), Enter (69) or Return (13) then IGNORE it (return)
            if(e.type !== 'click' && ! [32, 69, 13].includes(e.key.charCodeAt(0))){
                return;
            }
            e.preventDefault();     // Stops Space causing page-down
            let _target = e.target;
            if (_target.nodeName !== "A") {
                // Current target is the <span>X items</span> element within the <a> element
                if (_target.classList.contains("items-ph")) {
                    _target = _target.parentNode;   // Set _target to parent <a> element
                }
                // Some other element was clicked - so we ignore it
                else {
                    return;
                }
            }
            let _classList = _target.classList;
            _classList.toggle("collapsed");
            const _isCollapsed = _classList.contains("collapsed");
            _target.title = `Click to ${_isCollapsed ? "expand" : "collapse"}.`;
            _target.setAttribute("aria-expanded", ! _isCollapsed);
        };
        this._dom_container.addEventListener("click", _toggleJSON);
        this._dom_container.addEventListener("keydown", _toggleJSON);


        // Collapse at level colAt, where 0..n, -1 unlimited
		const colAt = typeof collapseAt === "number" ? collapseAt : -1; // collapse at

		this._dom_container.innerHTML = "";
		initWalkJSONTree(this._dom_container, jsonValue, colAt);

        this._allLinks = this._dom_container.querySelectorAll(".list-link");

        // Create Expand/Collapse All button ABOVE the JSON structure
        const expandCollapseBtn1 = createExpandCollapseBtn(false);
        parentEl.appendChild(expandCollapseBtn1);

        // Add JSON dom structure to parent element
        parentEl.appendChild(this._dom_container);

        // Create Expand/Collapse All button BELOW the JSON structure
        const expandCollapseBtn2 = createExpandCollapseBtn(false);
        parentEl.appendChild(expandCollapseBtn2);

        let _this = this;
        // Click handler for Expand/Collapse All buttons
        parentEl.addEventListener("click", function(e){
            e.stopPropagation();
            e.preventDefault();
            const isExpand = e.target.classList.contains("expand");
            if (isExpand) {
                _this.expandAll();
            } else {
                _this.collapseAll();
            }
            // Toggle the 2 buttons (above & below the JSON)
            changeExpandCollapseBtn(expandCollapseBtn1, isExpand);
            changeExpandCollapseBtn(expandCollapseBtn2, isExpand);
        });
	};

	/**
	 * Get container with pre object - this container is used for visualise JSON data.
	 * 
	 * @return {Element}
	 */
	JSONViewer.prototype.getContainer = function() {
		return this._dom_container;
	};

	/**
	 * Expand full JSON
	 */
	JSONViewer.prototype.expandAll = function() {
        for(const element of this._allLinks){
            element.classList.remove('collapsed');
        }
	};

	/**
	 * Collapse JSON
	 */
	JSONViewer.prototype.collapseAll = function() {
	    for(const element of this._allLinks){
	        element.classList.add('collapsed');
	    }
        // Show first element
        this._allLinks[0].classList.remove('collapsed');
	};

    function changeExpandCollapseBtn(btnEl, isCollapse) {
        if (isCollapse){
            btnEl.classList.remove("expand");
            btnEl.classList.add("collapse");
        }
        else {
            btnEl.classList.remove("collapse");
            btnEl.classList.add("expand");
        }
		const title = (isCollapse ? "Hide" : "Show") + " all JSON data."
        btnEl.title = title;
		btnEl.innerHTML = isCollapse ? "Collapse" : "Expand";
    };
    
    function createExpandCollapseBtn(isCollapse){
   		const btnEl = document.createElement("button");
		btnEl.classList.add("expand_collapse", "nav-btn", "btn", "btn--3d", "small-gap-vert");
		btnEl.tabIndex = 0;
		changeExpandCollapseBtn(btnEl, isCollapse);
		return btnEl;
    };

    function initWalkJSONTree(outputParent, value, colAt) {
        const valueType = _getType(value);
        if (valueType.scalar) {
            outputParent.appendChild(_createSimpleViewOf(value, valueType));
        }
        // If we have an Object or Array
		else {
			const isArray = valueType.type === "array";
			const items = isArray ? value : Object.keys(value);
            // root level
            // hide/show
            if (items.length) {
                const rootLink = _createLink(isArray ? "[" : "{", colAt === 0);
                rootLink.appendChild(_createItemsCount(items.length));
                outputParent.appendChild(rootLink); // output the rootLink
                walkJSONTree(outputParent, value, valueType, colAt, 1)
            }
            else {
                outputParent.appendChild(document.createTextNode(isArray ? "[" : "{"));
                outputParent.appendChild(_createItemsCount(0)); // output itemsCount
            }
            outputParent.appendChild(document.createTextNode(isArray ? "]" : "}"));
        }
    }


	/**
	 * Recursive walk for input value.
	 * 
	 * @param {Element} outputParent is the Element that will contain the new DOM
	 * @param {Object|Array|Scalar} JSON value
	 * @param {Object) valueType - describes type of value
	 * @param {Number} colAt Collapse at level, where 0..n, -1 unlimited
	 * @param {Number} lvl Current level
	 */
	function walkJSONTree(outputParent, value, valueType, colAt, lvl) {
        const isArray = valueType.type === "array";
        const items = isArray ? value : Object.keys(value);
        const len = items.length - 1;
        const ulList = document.createElement("ul");
        ulList.setAttribute("data-level", lvl);
        ulList.classList.add("type-" + valueType.type);

        items.forEach(function(key, ix) {
            const item = isArray ? key : value[key];
            const li = document.createElement("li");
            const itemValType = _getType(item);

            // Item is String, Number, Date or null
            if (itemValType.scalar) {
                if (! isArray) {
                    li.appendChild(document.createTextNode(key + " : "));
                }
                li.appendChild(_createSimpleViewOf(item, itemValType));
            }
            // Item is Object or Array
            else {
                const itemIsArray = itemValType.type === "array";
                const itemLen = itemIsArray ? item.length : Object.keys(item).length;
                const prefix = isArray ? "" : key + " : ";
                // empty Object or Array
                if (!itemLen) {
                    li.appendChild(document.createTextNode(prefix + (itemIsArray ? "[ ]" : "{ }")));
                }
                else {
                    const itemTitle = prefix + (itemIsArray ? "[" : "{");
                    const nextLevel = lvl + 1;
                    const itemLink = _createLink(itemTitle, colAt >= 0 && nextLevel >= colAt);

                    itemLink.appendChild(_createItemsCount(itemLen));
                    li.appendChild(itemLink);
                    walkJSONTree(li, item, itemValType, colAt, nextLevel);
                    li.appendChild(document.createTextNode(itemIsArray ? "]" : "}"));
                }
            }
            // add comma to the end
            if (ix < len) {
                li.appendChild(document.createTextNode(","));
            }
            ulList.appendChild(li);
        }, this);

        outputParent.appendChild(ulList); // output ulList
	};

    /**
    * Return Object indicating type - one of these values: "null", "array", "date", "object", "string", "number" and
    * whether value is scalar or not (scalar: true or scalar: false).
    **/
    function _getType(value){
        if (value === null) return {type: "null", scalar: true};
        let _type = typeof value;
        if (_type === "object") {
            if (value instanceof Array) return {type: "array", scalar: false};
            if (value instanceof Date) return {type: "date", scalar: true};
            return {type: "object", scalar: false};
        }
        // _type is "string" or "number"
        return {type: _type, scalar: true};
    };

	/**
	 * Create simple value (no object|array).
	 * 
	 * @param  {Number|String|null|undefined|Date} value Input value
	 * @return {Element}
	 */
	function _createSimpleViewOf(value, valType) {
		const spanEl = document.createElement("span");
		spanEl.className = "type-" + valType.type;
		if (valType.type === "string") {
			spanEl.textContent = `"${value}"`;
		} else if (valType.type === "date") {
			spanEl.textContent = value.toLocaleString();
		} else {
		    spanEl.textContent = "" + value;
		}
		return spanEl;
	};

	/**
	 * Create items count element.
	 * 
	 * @param  {Number} count: Items count
	 * @return {Element}
	 */
	function _createItemsCount(count) {
		const itemsCount = document.createElement("span");
		itemsCount.className = "items-ph";
		itemsCount.textContent = count + (count === 1 ? " item" : " items");
		return itemsCount;
	};

	/**
	 * Create clickable link.
	 * 
	 * @param  {String} title Link title
	 * @return {Element}
	 */
	function _createLink(title, isCollapse=false) {
		const linkEl = document.createElement("a");
		let classes = ["list-link"];
		if (isCollapse) classes.push("collapsed");
		linkEl.classList.add(...classes);
		linkEl.role = "button";
		linkEl.title = `Click to ${isCollapse ? "expand" : "collapse"}.`;
		linkEl.setAttribute("aria-expanded", ! isCollapse);
		linkEl.href = "";
		linkEl.textContent = title;
		return linkEl;
	};

	return JSONViewer;
})(document);
