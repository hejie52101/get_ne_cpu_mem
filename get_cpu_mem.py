import re
import paramiko
import sys
import time
import threading
import time
from pyecharts import Line, Grid
import csv
import os

def wait_end(chan, mode="oper"):
    result = ""
    if mode == "oper":
        reg = r">"
    elif mode == "login":
        reg = r".*login:"
    elif mode == "bash":
        reg = r"bash-4\.2\$"
    else:
        reg = r"~#"
    while True:
        if re.findall(reg, result[-15:]):
            break
        else:
            time.sleep(1)
            if chan.recv_ready():
                result += chan.recv(9999999).decode()
    return chan, result
def get_process_mem(chan, process, mode="bash"):
    chan.send('pidof '+process+'\n')
    chan, rst_pid = wait_end(chan, mode)
    # print(rst_pid)
    process_pid = re.findall(r"\n(?:\x00)?(\d+)(?:\x00)?\r",rst_pid)[0]
    chan.send("cat /proc/" + process_pid + "/status|grep VmRSS\n")
    chan.send("cat /proc/" + process_pid + "/status|grep VmRSS\n")
    chan, rst_mem = wait_end(chan, mode)
    process_mem = str(round(int(re.findall(r"VmRSS:\s*(\d+)",rst_mem)[0])/1024,2))
    return process_mem
def ssh_connect(ip, counter_list, username, password):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        ssh.connect(ip, 22, username, password)
    except Exception as e:
        try:
            ssh.connect(ip, 22, username, password)
        except Exception as e:
            raise e
    print("has login to " + ip)
    sys.stdout.flush()
    chan = ssh.invoke_shell()
    time.sleep(1)
    chan.recv(9999).decode()
    chan.send("\nshow chassis status|no-more\n")
    chan, rst_chassis = wait_end(chan)
    act_mcp = re.findall("([x|m]s[a|b]).*operational.*act", rst_chassis)[0]
    act_cips = re.findall("(cs[a|b]).*operational.*act", rst_chassis)[0]
    print("%s--->act_mcp: %s" % (threading.current_thread().name, act_mcp))
    sys.stdout.flush()
    print("%s--->act_cips: %s" % (threading.current_thread().name, act_cips))
    sys.stdout.flush()
    chan.send("start shell\n")
    chan, rst_chassis = wait_end(chan, "bash")
    chan.send("top -n 1 -b|grep -E 'DSWP.out|rcpd|cfgd|cips_app'|awk '{print $12,$9}'\n")
    chan, rst_top = wait_end(chan, "bash")
    rcpd = re.findall(r"rcpd (\S+)", rst_top)[0]
    cfgd = re.findall(r"cfgd (\S+)", rst_top)[0]
    dswp = str(sum(float(x) for x in re.findall(r"DSWP\.out (\S+)", rst_top)))
    chan.send("echo 3 > /proc/sys/vm/drop_caches\n")
    chan, rst_echo = wait_end(chan, "bash")
    chan.send("free -m|awk 'NR==3 {print $4}'\n")
    chan, rst_free = wait_end(chan, "bash")
    mem = re.findall(r"(\d+)\r\n", rst_free)[0]
    dswp_mem = get_process_mem(chan, "DSWP.out")
    rcpd_mem = get_process_mem(chan, "rcpd")
    cfgd_mem = get_process_mem(chan, "cfgd")
    if "ms" in act_mcp:
        if act_mcp == "msa":
            if act_cips == "csa":
                chan.send("telnet 169.254.3.4\n")
                chan, rst = wait_end(chan, "login")
                chan.send("root\n")
                chan, rst = wait_end(chan, "shell")
            elif act_cips == "csb":
                chan.send("telnet 169.254.4.5\n")
                chan, rst = wait_end(chan, "login")
                chan.send("root\n")
                chan, rst = wait_end(chan, "shell")
        else:
            if act_cips == "csa":
                chan.send("telnet 169.254.13.4\n")
                chan, rst = wait_end(chan, "login")
                chan.send("root\n")
                chan, rst = wait_end(chan, "shell")
            elif act_cips == "csb":
                chan.send("telnet 169.254.14.5\n")
                chan, rst = wait_end(chan, "login")
                chan.send("root\n")
                chan, rst = wait_end(chan, "shell")
        chan.send("top -n 1 -b|awk '{print $9,$8}'|grep cips_app\n")
        chan, rst_cips = wait_end(chan, "shell")
        cips_app = re.findall(r"cips_app (\S+)", rst_cips)[0]
        cips_mem = get_process_mem(chan, "cips_app", "shell")
    # elif act_mcp == "xsa" and act_cips == "csa" or act_mcp == "xsb" and act_cips == "csb":
    #     chan, rst = wait_end(chan, "shell")
    elif act_mcp == "xsa" and act_cips == "csa" or act_mcp == "xsb" and act_cips == "csb":
        cips_app = re.findall(r"cips_app (\S+)", rst_top)[0]
        cips_mem = get_process_mem(chan, "cips_app")
    else:
        if act_mcp == "xsa" and act_cips == "csb":
            chan.send("telnet 169.254.1.3\n")
            chan, rst = wait_end(chan, "login")
            chan.send("root\n")
            chan, rst = wait_end(chan, "shell")
        elif act_mcp == "xsb" and act_cips == "csa":
            chan.send("telnet 169.254.1.2\n")
            chan, rst = wait_end(chan, "login")
            chan.send("root\n")
            chan, rst = wait_end(chan, "shell")
        chan.send("top -n 1 -b|grep cips_app|awk '{print $12,$9}'\n")
        chan, rst_cips = wait_end(chan, "shell")
        cips_app = re.findall(r"cips_app (\S+)", rst_cips)[0]
        cips_mem = get_process_mem(chan, "cips_app", "shell")
    counter_list.append([ip, cips_app, dswp, rcpd, cfgd, cips_mem, dswp_mem, rcpd_mem, cfgd_mem, mem])

def func_thread(ip_list, counter_list, username, password):
    print("Thread %s is running..." % threading.current_thread().name)
    sys.stdout.flush()
    try:
        for ip in ip_list:
            locals()["t_"+ip] = threading.Thread(target=ssh_connect, args=(ip, counter_list, username, password), name="Thread_" + ip)
            locals()["t_"+ip].start()
        for ip in ip_list:
            locals()["t_"+ip].join()
    except Exception as e:
        raise e
    finally:
        print("Thread %s ended." % threading.current_thread().name)
        sys.stdout.flush()

def write_file(dirs, time_now, counter):
    file = os.path.join(dirs, counter[0])
    counter[0] = time_now
    print("write_file: " + file)
    sys.stdout.flush()
    with open(file+".csv", "a+", newline="") as f:
        fw = csv.writer(f, delimiter=",", lineterminator="\n")
        fw.writerow(counter)
    gen_echart(file)

def gen_echart(file):
    line_cpu = Line("NE Process CPU Utility", "(%)", page_title="ne_cpu_mem")
    line_mem = Line("NE Memory Utility", "(MB)", title_top="48%")
    date = []
    cpus = ["cips_app","DSWP.out","rcpd","cfgd"]
    mems = ["cips_app","DSWP.out","rcpd","cfgd","mcp_free"]
    # for cpu, mem in zip(cpus, mems):
    #     locals()[cpu] = []
    #     locals()[mem] = []
    for cpu in cpus:
        locals()[cpu+"_cpu"] = []
    for mem in mems:
        locals()[mem+"_mem"] = []
    with open(file+".csv", "r", newline="") as f:
        reader = csv.reader(f)
        for row in reader:
            date.append(row[0])
            for index, val in enumerate(cpus):
                locals()[val+"_cpu"].append(row[index+1])
            for index, val in enumerate(mems):
                locals()[val+"_mem"].append(row[index+5])
    for item in cpus:
        line_cpu.add(item, date, locals()[item+"_cpu"], is_smooth=True, legend_pos="25%")
    for item in mems:
        line_mem.add(item, date, locals()[item+"_mem"], is_smooth=True, legend_pos="25%", legend_top="49%")
    # line_mem.add(ne, date, memory, is_smooth=True, legend_pos="25%", legend_top="49%")
    grid = Grid(height=700, width=1000)
    grid.add(line_cpu, grid_bottom="55%")
    grid.add(line_mem, grid_top="55%")
    grid.render(file + ".html")

if __name__ == '__main__':
    ip_list = sys.argv[1].replace(" ", "").split(",")
    username = "admin"
    password = "admin1"
    counter_list = []
    counter_list_sorted = []
    func_thread(ip_list, counter_list, username, password)
    for x in ip_list:
        for y in counter_list:
            if y[0]==x:
                counter_list_sorted.append(y)
    print(f"+{'-'*15}+{'-'*80}+")
    print(f"|{'NE IP'.center(15)}|{'cips_app'.center(8)}|{'DSWP.out'.center(8)}|{'rcpd'.center(4)}|{'cfgd'.center(4)}|{'cips_app(MB)'.center(12)}|{'DSWP.out(MB)'.center(12)}|{'rcpd(MB)'.center(8)}|{'cfgd(MB)'.center(8)}|{'free(MB)'.center(8)}|")
    print(f"+{'-'*15}+{'-'*80}+")
    sys.stdout.flush()
    for counter in counter_list_sorted:
        print("|%s|%s|%s|%s|%s|%s|%s|%s|%s|%s|" % (counter[0].center(15), counter[1].center(8), counter[2].center(8), counter[3].center(4), counter[4].center(4), counter[5].center(12), counter[6].center(12), counter[7].center(8), counter[8].center(8), counter[9].center(8)))
        sys.stdout.flush()
    print(f"+{'-'*15}+{'-'*80}+")
    # if sys.argv[1] == "200.200.150.82,200.200.130.82,200.200.121.62,200.200.121.65,200.200.180.20,200.200.180.60,200.200.180.61,200.200.121.61,200.200.180.71,200.200.122.51":
    dirs = r"E:\Study\Python\get_cpu_mem\result"
    time_now = time.strftime("%Y-%m-%d_%H%M%S", time.localtime(time.time()))
    for counter in counter_list_sorted:
        write_file(dirs, time_now, counter)
    with open(r"E:\Study\Python\get_cpu_mem\result\index.html", "w") as f:
        f.write('''<!DOCTYPE html>
<html dir="ltr" lang="en">
<head>
<meta charset="utf-8">
<script>
function addRow(name, url) {
  if (name == "." || name == "..")
    return;

  var root = document.location.pathname.split("index.html")[0];
  if (root.substr(-1) !== "/")
    root += "/";

  var tbody = document.getElementById("tbody");
  var row = document.createElement("tr");
  var file_cell = document.createElement("td");
  var link = document.createElement("a");

  link.className = "icon file";

  link.draggable = "true";
  link.addEventListener("dragstart", onDragStart, false);

  link.innerText = name;
  link.href = root + url;

  file_cell.dataset.value = name;
  file_cell.appendChild(link);

  row.appendChild(file_cell);
  // row.appendChild(createCell(size, size_string));
  // row.appendChild(createCell(date_modified, date_modified_string));

  tbody.appendChild(row);
}

function onDragStart(e) {
  var el = e.srcElement;
  var name = el.innerText.replace(":", "");
  var download_url_data = "application/octet-stream:" + name + ":" + el.href;
  e.dataTransfer.setData("DownloadURL", download_url_data);
  e.dataTransfer.effectAllowed = "copy";
}

function createCell(value, text) {
  var cell = document.createElement("td");
  cell.setAttribute("class", "detailsColumn");
  cell.dataset.value = value;
  cell.innerText = text;
  return cell;
}

function start(location) {
  var header = document.getElementById("header");
  header.innerText = header.innerText.replace("LOCATION", location);

  document.getElementById("title").innerText = header.innerText;
}

function onHasParentDirectory() {
  var box = document.getElementById("parentDirLinkBox");
  box.style.display = "block";

  var root = document.location.pathname;
  if (!root.endsWith("/"))
    root += "/";

  var link = document.getElementById("parentDirLink");
  link.href = root + "..";
}

function onListingParsingError() {
  var box = document.getElementById("listingParsingErrorBox");
  box.innerHTML = box.innerHTML.replace("LOCATION", encodeURI(document.location)
      + "?raw");
  box.style.display = "block";
}

function sortTable(column) {
  var theader = document.getElementById("theader");
  var oldOrder = theader.cells[column].dataset.order || '1';
  oldOrder = parseInt(oldOrder, 10)
  var newOrder = 0 - oldOrder;
  theader.cells[column].dataset.order = newOrder;

  var tbody = document.getElementById("tbody");
  var rows = tbody.rows;
  var list = [], i;
  for (i = 0; i < rows.length; i++) {
    list.push(rows[i]);
  }

  list.sort(function(row1, row2) {
    var a = row1.cells[column].dataset.value;
    var b = row2.cells[column].dataset.value;
    if (column) {
      a = parseInt(a, 10);
      b = parseInt(b, 10);
      return a > b ? newOrder : a < b ? oldOrder : 0;
    }

    // Column 0 is text.
    if (a > b)
      return newOrder;
    if (a < b)
      return oldOrder;
    return 0;
  });

  // Appending an existing child again just moves it.
  for (i = 0; i < list.length; i++) {
    tbody.appendChild(list[i]);
  }
}
</script>

<style>

  h1 {
    border-bottom: 1px solid #c0c0c0;
    margin-bottom: 10px;
    padding-bottom: 10px;
    white-space: nowrap;
  }

  table {
    border-collapse: collapse;
  }

  th {
    cursor: pointer;
  }

  td.detailsColumn {
    -webkit-padding-start: 2em;
    text-align: end;
    white-space: nowrap;
  }

  a.icon {
    -webkit-padding-start: 1.5em;
    text-decoration: none;
  }

  a.icon:hover {
    text-decoration: underline;
  }

  a.file {
    background : url("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAABnRSTlMAAAAAAABupgeRAAABHUlEQVR42o2RMW7DIBiF3498iHRJD5JKHurL+CRVBp+i2T16tTynF2gO0KSb5ZrBBl4HHDBuK/WXACH4eO9/CAAAbdvijzLGNE1TVZXfZuHg6XCAQESAZXbOKaXO57eiKG6ft9PrKQIkCQqFoIiQFBGlFIB5nvM8t9aOX2Nd18oDzjnPgCDpn/BH4zh2XZdlWVmWiUK4IgCBoFMUz9eP6zRN75cLgEQhcmTQIbl72O0f9865qLAAsURAAgKBJKEtgLXWvyjLuFsThCSstb8rBCaAQhDYWgIZ7myM+TUBjDHrHlZcbMYYk34cN0YSLcgS+wL0fe9TXDMbY33fR2AYBvyQ8L0Gk8MwREBrTfKe4TpTzwhArXWi8HI84h/1DfwI5mhxJamFAAAAAElFTkSuQmCC ") left top no-repeat;
  }

  a.dir {
    background : url("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAAd5JREFUeNqMU79rFUEQ/vbuodFEEkzAImBpkUabFP4ldpaJhZXYm/RiZWsv/hkWFglBUyTIgyAIIfgIRjHv3r39MePM7N3LcbxAFvZ2b2bn22/mm3XMjF+HL3YW7q28YSIw8mBKoBihhhgCsoORot9d3/ywg3YowMXwNde/PzGnk2vn6PitrT+/PGeNaecg4+qNY3D43vy16A5wDDd4Aqg/ngmrjl/GoN0U5V1QquHQG3q+TPDVhVwyBffcmQGJmSVfyZk7R3SngI4JKfwDJ2+05zIg8gbiereTZRHhJ5KCMOwDFLjhoBTn2g0ghagfKeIYJDPFyibJVBtTREwq60SpYvh5++PpwatHsxSm9QRLSQpEVSd7/TYJUb49TX7gztpjjEffnoVw66+Ytovs14Yp7HaKmUXeX9rKUoMoLNW3srqI5fWn8JejrVkK0QcrkFLOgS39yoKUQe292WJ1guUHG8K2o8K00oO1BTvXoW4yasclUTgZYJY9aFNfAThX5CZRmczAV52oAPoupHhWRIUUAOoyUIlYVaAa/VbLbyiZUiyFbjQFNwiZQSGl4IDy9sO5Wrty0QLKhdZPxmgGcDo8ejn+c/6eiK9poz15Kw7Dr/vN/z6W7q++091/AQYA5mZ8GYJ9K0AAAAAASUVORK5CYII= ") left top no-repeat;
  }

  a.up {
    background : url("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAGXRFWHRTb2Z0d2FyZQBBZG9iZSBJbWFnZVJlYWR5ccllPAAAAmlJREFUeNpsU0toU0EUPfPysx/tTxuDH9SCWhUDooIbd7oRUUTMouqi2iIoCO6lceHWhegy4EJFinWjrlQUpVm0IIoFpVDEIthm0dpikpf3ZuZ6Z94nrXhhMjM3c8895977BBHB2PznK8WPtDgyWH5q77cPH8PpdXuhpQT4ifR9u5sfJb1bmw6VivahATDrxcRZ2njfoaMv+2j7mLDn93MPiNRMvGbL18L9IpF8h9/TN+EYkMffSiOXJ5+hkD+PdqcLpICWHOHc2CC+LEyA/K+cKQMnlQHJX8wqYG3MAJy88Wa4OLDvEqAEOpJd0LxHIMdHBziowSwVlF8D6QaicK01krw/JynwcKoEwZczewroTvZirlKJs5CqQ5CG8pb57FnJUA0LYCXMX5fibd+p8LWDDemcPZbzQyjvH+Ki1TlIciElA7ghwLKV4kRZstt2sANWRjYTAGzuP2hXZFpJ/GsxgGJ0ox1aoFWsDXyyxqCs26+ydmagFN/rRjymJ1898bzGzmQE0HCZpmk5A0RFIv8Pn0WYPsiu6t/Rsj6PauVTwffTSzGAGZhUG2F06hEc9ibS7OPMNp6ErYFlKavo7MkhmTqCxZ/jwzGA9Hx82H2BZSw1NTN9Gx8ycHkajU/7M+jInsDC7DiaEmo1bNl1AMr9ASFgqVu9MCTIzoGUimXVAnnaN0PdBBDCCYbEtMk6wkpQwIG0sn0PQIUF4GsTwLSIFKNqF6DVrQq+IWVrQDxAYQC/1SsYOI4pOxKZrfifiUSbDUisif7XlpGIPufXd/uvdvZm760M0no1FZcnrzUdjw7au3vu/BVgAFLXeuTxhTXVAAAAAElFTkSuQmCC ") left top no-repeat;
  }

  html[dir=rtl] a {
    background-position-x: right;
  }

  #parentDirLinkBox {
    margin-bottom: 10px;
    padding-bottom: 10px;
  }

  #listingParsingErrorBox {
    border: 1px solid black;
    background: #fae691;
    padding: 10px;
    display: none;
  }
</style>

<title id="title"></title>

</head>

<body>

<div id="listingParsingErrorBox">Oh, no! This server is sending data Google Chrome can't understand. Please <a href="http://code.google.com/p/chromium/issues/entry">report a bug</a>, and include the <a href="LOCATION">raw listing</a>.</div>

<h1 id="header">Index of Your NEs</h1>

<div id="parentDirLinkBox" style="display:none">
  <a id="parentDirLink" class="icon up">
    <span id="parentDirText">[parent directory]</span>
  </a>
</div>

<table>
  <thead>
    <tr class="header" id="theader">
      <th onclick="javascript:sortTable(0);">Name</th>
<!--       <th class="detailsColumn" onclick="javascript:sortTable(1);">
        Size
      </th>
      <th class="detailsColumn" onclick="javascript:sortTable(2);">
        Date Modified
      </th> -->
    </tr>
  </thead>
  <tbody id="tbody">
  </tbody>
</table>

</body>

</html>
<script>// Copyright (c) 2012 The Chromium Authors. All rights reserved.
// Use of this source code is governed by a BSD-style license that can be
// found in the LICENSE file.

/**
 * @fileoverview This file defines a singleton which provides access to all data
 * that is available as soon as the page's resources are loaded (before DOM
 * content has finished loading). This data includes both localized strings and
 * any data that is important to have ready from a very early stage (e.g. things
 * that must be displayed right away).
 *
 * Note that loadTimeData is not guaranteed to be consistent between page
 * refreshes (https://crbug.com/740629) and should not contain values that might
 * change if the page is re-opened later.
 */

/**
 * @typedef {{
 *   substitutions: (Array<string>|undefined),
 *   attrs: (Object<function(Node, string):boolean>|undefined),
 *   tags: (Array<string>|undefined),
 * }}
 */
let SanitizeInnerHtmlOpts;

// eslint-disable-next-line no-var
/** @type {!LoadTimeData} */ var loadTimeData;

// Expose this type globally as a temporary work around until
// https://github.com/google/closure-compiler/issues/544 is fixed.
/** @constructor */
function LoadTimeData(){}

(function() {
  'use strict';

  LoadTimeData.prototype = {
    /**
     * Sets the backing object.
     *
     * Note that there is no getter for |data_| to discourage abuse of the form:
     *
     *     var value = loadTimeData.data()['key'];
     *
     * @param {Object} value The de-serialized page data.
     */
    set data(value) {
      expect(!this.data_, 'Re-setting data.');
      this.data_ = value;
    },

    /**
     * Returns a JsEvalContext for |data_|.
     * @returns {JsEvalContext}
     */
    createJsEvalContext: function() {
      return new JsEvalContext(this.data_);
    },

    /**
     * @param {string} id An ID of a value that might exist.
     * @return {boolean} True if |id| is a key in the dictionary.
     */
    valueExists: function(id) {
      return id in this.data_;
    },

    /**
     * Fetches a value, expecting that it exists.
     * @param {string} id The key that identifies the desired value.
     * @return {*} The corresponding value.
     */
    getValue: function(id) {
      expect(this.data_, 'No data. Did you remember to include strings.js?');
      const value = this.data_[id];
      expect(typeof value != 'undefined', 'Could not find value for ' + id);
      return value;
    },

    /**
     * As above, but also makes sure that the value is a string.
     * @param {string} id The key that identifies the desired string.
     * @return {string} The corresponding string value.
     */
    getString: function(id) {
      const value = this.getValue(id);
      expectIsType(id, value, 'string');
      return /** @type {string} */ (value);
    },

    /**
     * Returns a formatted localized string where $1 to $9 are replaced by the
     * second to the tenth argument.
     * @param {string} id The ID of the string we want.
     * @param {...(string|number)} var_args The extra values to include in the
     *     formatted output.
     * @return {string} The formatted string.
     */
    getStringF: function(id, var_args) {
      const value = this.getString(id);
      if (!value) {
        return '';
      }

      const args = Array.prototype.slice.call(arguments);
      args[0] = value;
      return this.substituteString.apply(this, args);
    },

    /**
     * Make a string safe for use with with Polymer bindings that are
     * inner-h-t-m-l (or other innerHTML use).
     * @param {string} rawString The unsanitized string.
     * @param {SanitizeInnerHtmlOpts=} opts Optional additional allowed tags and
     *     attributes.
     * @return {string}
     */
    sanitizeInnerHtml: function(rawString, opts) {
      opts = opts || {};
      return parseHtmlSubset('<b>' + rawString + '</b>', opts.tags, opts.attrs)
          .firstChild.innerHTML;
    },

    /**
     * Returns a formatted localized string where $1 to $9 are replaced by the
     * second to the tenth argument. Any standalone $ signs must be escaped as
     * $$.
     * @param {string} label The label to substitute through.
     *     This is not an resource ID.
     * @param {...(string|number)} var_args The extra values to include in the
     *     formatted output.
     * @return {string} The formatted string.
     */
    substituteString: function(label, var_args) {
      const varArgs = arguments;
      return label.replace(/\$(.|$|\n)/g, function(m) {
        assert(m.match(/\$[$1-9]/), 'Unescaped $ found in localized string.');
        return m == '$$' ? '$' : varArgs[m[1]];
      });
    },

    /**
     * Returns a formatted string where $1 to $9 are replaced by the second to
     * tenth argument, split apart into a list of pieces describing how the
     * substitution was performed. Any standalone $ signs must be escaped as $$.
     * @param {string} label A localized string to substitute through.
     *     This is not an resource ID.
     * @param {...(string|number)} var_args The extra values to include in the
     *     formatted output.
     * @return {!Array<!{value: string, arg: (null|string)}>} The formatted
     *     string pieces.
     */
    getSubstitutedStringPieces: function(label, var_args) {
      const varArgs = arguments;
      // Split the string by separately matching all occurrences of $1-9 and of
      // non $1-9 pieces.
      const pieces = (label.match(/(\$[1-9])|(([^$]|\$([^1-9]|$))+)/g) ||
                      []).map(function(p) {
        // Pieces that are not $1-9 should be returned after replacing $$
        // with $.
        if (!p.match(/^\$[1-9]$/)) {
          assert(
              (p.match(/\$/g) || []).length % 2 == 0,
              'Unescaped $ found in localized string.');
          return {value: p.replace(/\$\$/g, '$'), arg: null};
        }

        // Otherwise, return the substitution value.
        return {value: varArgs[p[1]], arg: p};
      });

      return pieces;
    },

    /**
     * As above, but also makes sure that the value is a boolean.
     * @param {string} id The key that identifies the desired boolean.
     * @return {boolean} The corresponding boolean value.
     */
    getBoolean: function(id) {
      const value = this.getValue(id);
      expectIsType(id, value, 'boolean');
      return /** @type {boolean} */ (value);
    },

    /**
     * As above, but also makes sure that the value is an integer.
     * @param {string} id The key that identifies the desired number.
     * @return {number} The corresponding number value.
     */
    getInteger: function(id) {
      const value = this.getValue(id);
      expectIsType(id, value, 'number');
      expect(value == Math.floor(value), 'Number isn\'t integer: ' + value);
      return /** @type {number} */ (value);
    },

    /**
     * Override values in loadTimeData with the values found in |replacements|.
     * @param {Object} replacements The dictionary object of keys to replace.
     */
    overrideValues: function(replacements) {
      expect(
          typeof replacements == 'object',
          'Replacements must be a dictionary object.');
      for (const key in replacements) {
        this.data_[key] = replacements[key];
      }
    }
  };

  /**
   * Checks condition, displays error message if expectation fails.
   * @param {*} condition The condition to check for truthiness.
   * @param {string} message The message to display if the check fails.
   */
  function expect(condition, message) {
    if (!condition) {
      console.error(
          'Unexpected condition on ' + document.location.href + ': ' + message);
    }
  }

  /**
   * Checks that the given value has the given type.
   * @param {string} id The id of the value (only used for error message).
   * @param {*} value The value to check the type on.
   * @param {string} type The type we expect |value| to be.
   */
  function expectIsType(id, value, type) {
    expect(
        typeof value == type, '[' + value + '] (' + id + ') is not a ' + type);
  }

  expect(!loadTimeData, 'should only include this file once');
  loadTimeData = new LoadTimeData;
})();
</script>
''')
    with open(r"E:\Study\Python\get_cpu_mem\result\index.html", "a+") as f:
        for ip in ip_list:
            f.write('<script>addRow("'+ip+'","'+ip+'.html");</script>\n')
