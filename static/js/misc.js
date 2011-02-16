
// String.prototype.trim = function() { return this.replace(/^\s+|\s+$/, ''); };
String.prototype.trim = function() { return this.replace(/^\s*/, "").replace(/\s*$/, ""); };

var EmailFilter = /^([a-zA-Z0-9_\.\-])+\@(([a-zA-Z0-9\-])+\.)+([a-zA-Z0-9]{2,4})+$/;

// Major version of Flash required
var requiredMajorVersion = 9;
// Minor version of Flash required
var requiredMinorVersion = 0;
// Minor version of Flash required
var requiredRevision = 124;

function urlencode(str)
{
    return escape(str).replace(/\+/g, "%2B").replace(/\//g, "%2F");
}

// Generic handler for all ajax errors!
function ajaxErrorHandler(data)
{
    var errorsWindow = window.open("", "errors_window", "width=800, height=800, resizable=yes, scrollbars=yes, toolbar=no");
    if (errorsWindow == null)
    {
        // probably blocked by the browser?
        alert("Could not show errors.  Please enable popup windows in your browser for this host");
    }
    else
    {
        errorsWindow.focus();
        errorsWindow.document.open();
        errorsWindow.document.write(data.responseText);
        errorsWindow.document.close();
    }
}

// Wrapper for doing an ajax request.
function yuiAjax(type, url, callback, data)
{
    YAHOO.util.Connect.asyncRequest(type, url, callback, data);
}

// Makes an ajax request with jQuery
function jqueryAjax(req_url, success_callback,
                    req_type,       /* = "GET" */
                    req_data,       /* = null */
                    error_callback, /* = ajaxErrorHandler */
                    req_timeout     /* = 30000 */)
{
    if (typeof req_type === "undefined" || req_type == null)
        req_type = "GET";

    if (typeof req_data === "undefined")
        req_data = null;

    if (typeof req_timeout === "undefined" || req_timeout == null)
        req_timeout = 30000;

    if (typeof error_callback === "undefined" || error_callback == null)
        error_callback = ajaxErrorHandler;

    $.ajax({url: req_url, type: req_type, data: req_data, timeout: req_timeout,
            dataType: "json", error: error_callback, success: success_callback});
}

function gotoPage(url)
{
    window.location.href = url;
}

function refreshPage()
{
    location.reload(true);
}

function SetCookie(cookieName, cookieValue, nDays)
{
    var today = new Date();
    var expire = new Date();
    if (nDays == null || nDays == 0) nDays = 1;
    expire.setTime(today.getTime() + 3600000 * 24 * nDays);
    document.cookie = cookieName + "=" + escape(cookieValue) +
                      ";expires=" + expire.toGMTString();
}

function set_cookie(name, value, exp_y, exp_m, exp_d, path, domain, secure)
{
    var cookie_string = name + "=" + escape(value);

    if (exp_y)
    {
        var expires = new Date(exp_y, exp_m, exp_d);
        cookie_string += ";expires=" + expires.toGMTString();
    }

    if (path)
        cookie_string += ";path=" + escape(path);

    if (domain)
        cookie_string += ";domain=" + escape(path);

    if (secure)
        cookie_string += ";secure";

    document.cookie = cookie_string;
}

function delete_cookie(cookie_name)
{
    var cookie_date = new Date();
    cookie_date.setTime(cookie_date.getTime() - 1);
    document.cookie = (cookie_name + "=;expires=Thu, 01-Jan-1970 00:00:01 GMT");
    // get_cookie(cookie_name);
}

function get_cookie(cookie_name)
{
    var results = document.cookie.match('(^|;) ?' + cookie_name + '=([^;]*)(;|$)' );

    if (results)
        return unescape(results[2]);
    else
        return null;
}

// temporary to create a panel for use as a dialog box
function createLightPanel(title, div, size)
{
    var width = size || "400px";
    var panel = new YAHOO.widget.Panel(title,{width: width, 
                                              constraintoviewport: true,
                                              fixedcenter: true,
                                              close: true,
                                              // draggable: true,
                                              zindex:4,
                                              modal: true,
                                              visible: true});
    panel.setHeader(title);
    panel.setBody(div);
    panel.render(document.body);
    div.style.display = "block";
    return panel;
}

function strcmp ( str1, str2 ) {
    // http://kevin.vanzonneveld.net
    // +   original by: Waldo Malqui Silva
    // +      input by: Steve Hilder
    // +   improved by: Kevin van Zonneveld (http://kevin.vanzonneveld.net)
    // +    revised by: gorthaur
    // *     example 1: strcmp( 'waldo', 'owald' );
    // *     returns 1: 1
    // *     example 2: strcmp( 'owald', 'waldo' );
    // *     returns 2: -1

    return ( ( str1 == str2 ) ? 0 : ( ( str1 > str2 ) ? 1 : -1 ) );
}

