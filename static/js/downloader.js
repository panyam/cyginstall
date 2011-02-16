
var currPackage         = -1;       // package over which the mouse is currently selected
var currOrdering        = "";
var packages_by_index   = [];
var packages_by_name    = {};
var mirrors_by_index    = [ ];
var mirrors_by_name     = { };
var suppressOnChange    = false;
const ORDERBY_SELECTED    = "selected";
const ORDERBY_SIZE        = "size";
const ORDERBY_PROGRESS    = "progress";
const ORDERBY_NAME        = "name";
var pkgSortFunctions = {
    "selected": function (pkg1, pkg2) {
        if (pkg1.selected != pkg2.selected)
        {
            return pkg2.selected - pkg1.selected;
        }
        else
        {
            var diff = pkg2.progress.completed_pct - pkg1.progress.completed_pct;
            return diff ;
            if (diff != 0)
                return diff;
            else
                return getPackageSize(pkg2) - getPackageSize(pkg1);
        }
    },
    "size": function (pkg1, pkg2) { return getPackageSize(pkg1) - getPackageSize(pkg2); },
    "progress": function (pkg1, pkg2) {
        var diff = pkg1.progress.completed_pct - pkg2.progress.completed_pct;
        if (diff == 0)
            return pkg2.selected - pkg1.selected;
        else
            return diff;
    },
    "name": function (pkg1, pkg2) { return strcmp(pkg1.name, pkg2.name); },
};

$(document).ready(initialize);

function getPackageSize(pkg, source)
{
    if (typeof(source) === "undefined" || source == null)
        source = false;

    if (source || !('install_file' in pkg.main))
    {
        if ('source_size' in pkg.main)
            return pkg.main.source_size;
        else
            return 0;
    }
    else
    {
        return pkg.main.install_size;
    }
}

function getPackageFile(pkg, source)
{
    if (typeof(source) === "undefined" || source == null)
        source = false;

    if (source || !('install_file' in pkg.main))
    {
        if ('source_file' in pkg.main)
            return pkg.main.source_file;
        else
            return null;
    }
    else
    {
        return pkg.main.install_file;
    }
}

/**
 * Called on load.
 */
function initialize()
{
    refresh_package_list();
    refresh_mirror_list();
}

/**
 * Refreshes the list of mirrors.
 */
function refresh_mirror_list()
{
    function onSuccessCallback(response)
    {
        if (response.code == 0)
        {
            mirrors_by_index    = [];
            mirrors_by_name     = response.value.mirrors;
            for (var mirror_key in mirrors_by_name)
            {
                var mirror = mirrors_by_name[mirror_key];
                mirror['path'] = mirror_key;
                mirrors_by_index.push(mirror);
            }

            // sort the mirrors by health
            mirrors_by_index.sort(function(m1, m2) {
                if (m1.health == m2.health)
                    return 0;
                else if (m1.health == "Down")
                    return -1;
                else if (m2.health == "Down")
                    return 1;
                else if (typeof(m1.health) === "undefined" || m1.health == null)
                    return -1;
                else if (typeof(m2.health) === "undefined" || m2.health == null)
                    return 1;
                else
                    return m1.health - m2.health;
            });
            mirrors_by_index.reverse();

            createMirrorListHtml();
        }
        else
        {
            alert("Error: " + response.value);
        }
    }

    function onErrorCallback(response)
    {
        alert('Could not get mirror list.  Please try again.');
    }

    jqueryAjax("/mirrors/", onSuccessCallback, "GET", null, onErrorCallback);
}

/**
 * Create's the html to display the mirror list.
 */
function createMirrorListHtml()
{
    var html = "<table><thead><td class = 'header_cell'>Activate</td>";
    html     += "<td class = 'header_cell'>Host/Location</td>";
    for (var i = 0, numMirrors = mirrors_by_index.length;i < numMirrors;i++)
    {
        var mirror = mirrors_by_index[i];
        html += "<tr>";
        html += "<td>";
        html += "<center><input type = checkbox value = '" + mirror.path + "' " +
                "   id = 'checkbox_" + i + "' " +
                "   onchange = 'onMirrorSelected(" + i + ");'";
        if (mirror.active)
            html += " checked = 'true' ";
        html += "/><br/>";
        html += "<input type = button id = 'btn_refresh_" + i + 
                " onclick = 'mirror_clicked(" + i + ", true);' value = 'Refresh'/>";
        html += "</center></td>";

        html += "<td><a href='javascript:void(0)' " +
                "onclick = 'mirror_clicked(" + i + ", false);'>" + mirror.path + "</a> <br/>";
        // {# - {{ mirrors[mirror]['location'] }}, #}
        html += "<strong>Health: </strong>";
        html += "<span id = 'health_span_" + i + "'>" + mirror.health + "</span> ";
        html += "<strong>Packages: </strong>";
        html += "<span id = 'num_packages_span_" + i + "'>" + mirror.num_packages + "</span>";
        html += "</td>";
        html += "</tr>";
    }
    html     += "</thead></table>";
    $("#mirror_list_div").html(html);
}

/**
 * Tells the server the mirror is to be activated or not.
 */
function onMirrorSelected(mirror_index)
{
    var checkbox = $("#checkbox_" + mirror_index);
    var checked = checkbox.attr('checked');
    var mirror = mirrors_by_index[mirror_index];
    var command = checked ? "activate" : "deactivate";

    jqueryAjax("/mirrors/" + command + "/",
               function (response) { /* do nothing */ },
               "POST", { 'mirror': mirror.path });
}

/**
 * Tells if a package is selected to be installed or not.
 */
function isPackageSelected(pkg_index)
{
    return packages_by_index[pkg_index].selected;
}

function shouldShowCompletedPackages()
{
    return $("#show_completed_checkbox").attr("checked");
}

/**
 * Show the list of packages from the packages listed and/or selected.
 */
function createPackageListHtml()
{
    // now create the html
    var numPackages = packages_by_index.length;
    var numPackagesShown = 0;
    var html = "<table border = 0 width = '100%'>";
    var showCompleted = shouldShowCompletedPackages();
    var showHeader = true;
    if (showHeader)
    {
        html += "<thead>";
        html += "<td width = '50'><strong><center>";
        html += "<a href='javascript:void(0)' onclick='toggleOrdering(ORDERBY_SELECTED)'>";
        html += "Select";
        html += "</a>";
        html += "<input type = checkbox id = 'selectAllPackagesCheckbox' " +
                       "onchange = 'onSelectAllPackages(event);'/>";
        html += "</center></strong></td>";

        html += "<td><strong><center>";
        html += "<a href='javascript:void(0)' onclick='toggleOrdering(ORDERBY_NAME)'>";
        html += "Name/Description</a></center></strong></td>";

        html += "<td width = '150'><strong><center>";
        html += "<a href='javascript:void(0)' onclick='toggleOrdering(ORDERBY_PROGRESS)'>Progress</a>";
        html += " / ";
        html += "<a href='javascript:void(0)' onclick='toggleOrdering(ORDERBY_SIZE)'>Size</a>";
        html += "</center></strong></td>";
        html += "</thead>";
    }
    for (var i = 0;i < numPackages;i++)
    {
        var pkg = packages_by_index[i];
        if (showCompleted && pkg.progress.completed_pct >= 100)
            continue;

        numPackagesShown++;
        html += "<tr id = 'package_row_" + i + "'" +
                   " onmouseover='onMouseOverPackage(" + i + ");' " + 
                   " onclick='onMouseClickPackage(event, " + i + ");' " + 
                   " onmouseout='onMouseOutPackage(" + i + ");' " + 
                   " class = 'mouse_" + (isPackageSelected(i) ? "selected" : "out") + "_row'>";
        html += "<td id='package_selected_col_" + i + "' valign = top><center>";
        html += "<input type = checkbox id = 'selectPkgCheckbox_" + i + "'" +
                "onchange = 'onPackagesSelected(event, [" + i + "], event.currentTarget.checked);' "
        if (isPackageSelected(i))
        {
            html += " checked = 'true' ";
        }
        html += "/>";
        html += "</center></td>";
        html += "<td id='package_name_col_" + i + "' valign = top style='width: 350px'>";
        html += "<strong>" + pkg.name + "</strong>: ";
        html += "<br/>" + pkg.main.sdesc;
        html += "</td>";
        html += "<td id='package_progress_col_" + i + "' valign = top style='text-align: center'>";
        html += pkg.progress.completed_bytes + " of " + getPackageSize(pkg) + " - " + pkg.progress.completed_pct + "%";
        html += "</td>";


        // do we need to show mirrors?
        var pkg_mirrors = pkg.mirrors;
        if (false && typeof(pkg_mirrors) != "undefined" && pkg_mirrors != null)
        {
            html += "<td valign = top style='text-align: center'><select>";
            for (var j = 0;j < pkg_mirrors.length;j++)
            {
                html += "<option>" + pkg_mirrors[j] + "</option>";
            }
            html += "</select></td>";
        }
        html += "</tr>";
    }
    html += "</table>";
    $("#mirror_packages_div").html(html);
    $("#mirror_packages_num_left_span").html("( " + numPackagesShown + " left)")
}

/**
 * Called when a mirror is clicked so we now also fetch the files served
 * by the mirror and add it to our package list.
 */
function mirror_clicked(mirror_index, refresh)
{
    var mirror = mirrors_by_index[mirror_index];

    function onSuccessCallback(response)
    {
        if (response.code == 0)
        {
            //  update our package list
            $("#health_span_" + mirror_index).html(response.value.health);
            $("#num_packages_span_" + mirror_index).html(response.value.num_packages);
            var numPackages = response.value.contents.length;
            var newPackages = 0;
            for (var i = 0;i < numPackages;i++)
            {
                var pkg = response.value.contents[i];
                if (!(pkg.name in packages_by_name))
                {
                    pkg['selected'] = false;    // mark it is unselected
                    packages_by_name[pkg.name] = pkg;
                    packages_by_index.push(pkg);
                    newPackages ++;
                }
            }

            if (newPackages == 0)
            {
                // alert("No new packages found.");
            }
            else
            {
                // alert(newPackages + " packages found.");
                createPackageListHtml();
            }
        }
        else
        {
            $("#health_span_" + mirror_index).html("Down");
            alert("Error: " + response.value);
        }
    }

    function onErrorCallback(response)
    {
        $("#health_span_" + mirror_index).html("Down");
    }

    jqueryAjax("/mirror/contents/" +
                "?refresh=" + refresh +
                "&mirror=" + urlencode(mirror.path),
                onSuccessCallback,
                "GET", null,
                onErrorCallback);
}

/**
 * Called to either select or deselect all packages.
 */
function onSelectAllPackages(event)
{
    var selectAll = event.currentTarget.checked;
    var numPackages = packages_by_index.length;
    var package_names = [];
    for (var i =  0;i < numPackages;i++)
    {
        $("#selectPkgCheckbox_" + i).attr("checked", selectAll);
        package_names.push("'" + packages_by_index[i].name + "'");
    }

    package_names = "[" + package_names.join(",") + "]";

    // send a response to select or unselect all packages
    var command = selectAll ? "select" : "unselect";
    jqueryAjax("/packages/" + command + "/",
               function (response) { /* do nothing */ },
               "POST", { 'packages': package_names });
}

/**
 * Called when a package is selected or unselected.
 * Tells the server the mirror is to be activated or not.
 */
function onPackagesSelected(event, pkg_indexes, select)
{
    // var checkbox = $("#selectPkgCheckbox_" + pkg_index);
    // var checked = checkbox.attr('checked');
    if (suppressOnChange)
        return ;
    suppressOnChange = true;
    var command = select ? "select" : "unselect";
    var pkg_names = [];
    for (var i = pkg_indexes.length - 1; i >= 0;i--)
    {
        pkg_names.push("'" + packages_by_index[pkg_indexes[i]].main.name + "'");
    }

    function onSuccessHandler(response)
    {
        if (response.code == 0)
        {
            for (var i = pkg_indexes.length - 1; i >= 0;i--)
            {
                var pkg_tr = $("#package_row_" + i);
                if (packages_by_index[pkg_indexes[i]]['selected'])
                {
                    pkg_tr.removeClass("mouse_out_row");
                    pkg_tr.addClass("mouse_selected_row");
                }
                else
                {
                    pkg_tr.removeClass("mouse_selected_row");
                    pkg_tr.addClass("mouse_out_row");
                }
            }
            suppressOnChange = false;
        }
        else
        {
            alert("Error: " + response.value);
        }
    }
    jqueryAjax("/packages/" + command + "/",
               onSuccessHandler,
               "POST", { 'packages': "[" + pkg_names.join(",") + "]" });
}

function toggleOrdering(order_by)
{
    orderPackages(order_by);
}

/**
 * Order packages by a certain criteria.
 */
function orderPackages(order_by)
{
    // two in a row reverses the decision
    if (currOrdering == order_by)
        order_by = "-" + order_by;

    descending = false;
    while (order_by[0] == '-')
    {
        descending = !descending;
        order_by = order_by.substring(1);
    }

    currOrdering = order_by;

    var sortfunc = pkgSortFunctions[order_by];
    packages_by_index.sort(sortfunc);

    if (descending)
    {
        currOrdering = "-" + currOrdering;
        packages_by_index.reverse();
    }

    createPackageListHtml();
}

/**
 * Refreshes the list of packages.
 */
function refresh_package_list()
{
    function onSuccessCallback(response)
    {
        if (response.code == 0)
        {
            packages_by_index   = [];
            packages_by_name    = response.value.packages;
            var num_selected    = 0;
            for (var pkg_key in packages_by_name)
            {
                var pkg = packages_by_name[pkg_key];
                packages_by_index.push(pkg);
                if (pkg.selected)
                    num_selected ++;
            }

            if (num_selected > 0)
                orderPackages("selected");
            else
                orderPackages("name");
        }
        else
        {
            alert("Error: " + response.value);
        }
    }

    function onErrorCallback(response)
    {
        alert('Could not get package list.  Please try again.');
    }

    jqueryAjax("/packages/", onSuccessCallback, "GET", null, onErrorCallback);
}

/**
 * Called when the download button is clicked.
 */
function handleOnDownload(event)
{
    function onSuccessCallback(response)
    {
    }

    jqueryAjax("/downloads/start/", onSuccessCallback, "POST", { 'orderby': currOrdering }, null);
}

function onMouseOverPackage(pkg_index)
{
    var pkg_tr = $("#package_row_" + pkg_index);
    // alert('Over: ' + pkg_index);
    pkg_tr.removeClass("mouse_out_row");
    pkg_tr.removeClass("mouse_selected_row");
    pkg_tr.addClass("mouse_over_row");
}

function onMouseOutPackage(pkg_index)
{
    var pkg_tr = $("#package_row_" + pkg_index);
    // alert('Out: ' + pkg_index);
    pkg_tr.removeClass("mouse_over_row");
    if (packages_by_index[pkg_index]['selected'])
    {
        pkg_tr.removeClass("mouse_out_row");
        pkg_tr.addClass("mouse_selected_row");
    }
    else
    {
        pkg_tr.removeClass("mouse_selected_row");
        pkg_tr.addClass("mouse_out_row");
    }
}

function onMouseClickPackage(event, pkg_index)
{
    if (event.shiftKey)
    {
        // update multiple items
        var first_selected = packages_by_index[pkg_index]['selected'];
        var pkg_indexes = [];
        var showCompleted = shouldShowCompletedPackages();
        for (var i = pkg_index;i >= 0;i--)
        {
            var pkg = packages_by_index[i];
            if (pkg.progress.completed_pct >= 100)
                continue ;  // skip packages that are complete

            if (pkg.selected != first_selected)
                break ;

            pkg.selected = !pkg.selected;
            $("#selectPkgCheckbox_" + i).attr("checked", pkg.selected);
            pkg_indexes.push(i);
        }
        onPackagesSelected(event, pkg_indexes, !first_selected);
    }
    else
    {
        // only one item to be updated
        var pkg = packages_by_index[pkg_index];
        pkg.selected = !pkg.selected;
        $("#selectPkgCheckbox_" + pkg_index).attr("checked", pkg.selected);
        onPackagesSelected(event, [pkg_index], pkg.selected);
    }
}

