#!/usr/bin/env python3
"""Generate the Open MitraStar 0.3 original-web unlock overlay.

The script copies the stock web pages from the extracted rootfs and applies a
small, reproducible UI-only unlock layer. It does not read device backups or
secrets.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path


VERSION = "openmitrastar-0.3-original-ui-unlock"
ROOT = Path(__file__).resolve().parents[1]
SRC_WWW = ROOT / "work" / "revival" / "rootfs" / "var" / "www"
PREV_OVERLAY = ROOT / "versions" / "revival-0.2.1-openmitrastar-statusfix" / "overlay"
OVERLAY = ROOT / "versions" / VERSION / "overlay"

TARGET_PAGES = [
    "advanced.html",
    "wifi5g_adv.html",
    "wifi24g.html",
    "wifi5g.html",
    "lan.html",
]

VISIBLE_IDS = [
    "basic_zone",
    "adv_set",
    "assoc_list",
    "macfltlist",
    "wps_zone",
    "ruleN",
    "wifi_TKIPAES",
    "wifi24_TKIPAES",
    "redLocal",
    "ReqIP",
    "MinAddrv4",
    "MaxAddrv4",
    "div_wifi_bandwidth",
    "div_cur_bandwidth",
    "Qhop_MBS",
    "Qhop_RBS",
    "MBS_message",
    "MBS_Off_message",
    "automode_too_far_message",
    "automode_too_close_message",
    "automode_iptv_warning_message",
    "long_distance_iptv_message",
    "long_distance_data_message",
    "data_change_iptv_warning",
    "col_wpsstapin",
    "col_wpsappin",
]

SECRET_PLACEHOLDERS = [
    "##wlKey1##",
    "##wlWpaPsk##",
    "##wl24Key1##",
    "##wl24WpaPsk##",
]


CSS = """\
/* Open MitraStar 0.3: original UI unlock and inline documentation layer. */
.help-bubble {
  display: inline-block;
  min-width: 16px;
  height: 16px;
  line-height: 16px;
  margin-left: 6px;
  border-radius: 50%;
  border: 1px solid #4a76a8;
  background: #eef6ff;
  color: #1f4f82;
  font-weight: bold;
  font-size: 11px;
  text-align: center;
  cursor: help;
  vertical-align: middle;
}
.openmitrastar-visible {
  display: block !important;
  visibility: visible !important;
}
.openmitrastar-inline-visible {
  display: inline-block !important;
  visibility: visible !important;
}
.openmitrastar-unlocked-control {
  outline: 1px dotted rgba(31, 79, 130, 0.35);
  outline-offset: 1px;
}
.openmitrastar-secret-note {
  color: #7a4b00;
  font-size: 11px;
  margin-left: 6px;
}
"""


JS = r"""/* Open MitraStar 0.3: unlock stock pages without exposing secrets. */
(function () {
  var VISIBLE_IDS = [
    "basic_zone", "adv_set", "assoc_list", "macfltlist", "wps_zone",
    "ruleN", "wifi_TKIPAES", "wifi24_TKIPAES", "redLocal", "ReqIP",
    "MinAddrv4", "MaxAddrv4", "div_wifi_bandwidth", "div_cur_bandwidth",
    "Qhop_MBS", "Qhop_RBS", "MBS_message", "MBS_Off_message",
    "automode_too_far_message", "automode_too_close_message",
    "automode_iptv_warning_message", "long_distance_iptv_message",
    "long_distance_data_message", "data_change_iptv_warning",
    "col_wpsstapin", "col_wpsappin"
  ];

  var SKIP_NAMES = /^(SessionKey|credential|token|cookie|submitValue|action|rebootFlag|intf_id|.*_value)$/i;
  var SECRET_IDS = /^(wifiPass|wifi24Pass|wpsappin|wpspin)$/i;

  var DOCS = [
    [/ssid|visible|hide/i, "What: SSID/visibility. Up: more networks/flex. Down: less airtime. Safe: only needed SSIDs. Breaks: duplicate/hidden SSIDs confuse clients. Legal: no RF limit."],
    [/channel|numcanal|canal/i, "What: auto/fixed RF channel. Up/down: changes channel. Safe: Auto. Breaks: DFS/congestion can drop clients. Legal: ES/EU DFS/channel rules apply."],
    [/bandwidth|bw_|ancho/i, "What: WiFi width. Up: more peak speed. Down: more compatibility. Safe: 20 MHz dense 2.4G, 40/80 clean 5G. Breaks: instability/interference. Legal: ES/EU RF limits apply."],
    [/power|tx|transmit/i, "What: TX power. Up: more reach. Down: less heat/interference. Safe: vendor/lowest stable. Breaks: too low drops clients; too high can be illegal/unstable. Legal: ES/EU EIRP applies."],
    [/dfs|ocac/i, "What: radar-aware 5G use. On: DFS channels. Off: fewer channel moves. Safe: on for DFS. Breaks: radar move or non-compliance. Legal: DFS mandatory on affected ES/EU channels."],
    [/qhop/i, "What: Quantenna backhaul/repeater mode. Up/change: favors reach/IPTV/data. Safe: Auto. Breaks: repeater/IPTV/data association. Legal: follows RF channel/power rules."],
    [/wmm|apsd/i, "What: WiFi QoS/power save. On: better modern voice/video. Off: legacy tests. Safe: enabled. Breaks: lower throughput/roaming. Legal: no RF limit."],
    [/mcs|tx_rate|rate/i, "What: PHY/MCS rate. Up/fixed: lab speed. Down/auto: range/compat. Safe: Auto. Breaks: fixed high rate can drop distant clients. Legal: no RF limit."],
    [/beacon|bcn/i, "What: beacon ms. Up: less overhead. Down: faster discovery. Safe: 100 ms, 50-1000. Breaks: high values delay roaming. Legal: no RF limit."],
    [/dtim/i, "What: multicast cadence. Up: battery. Down: responsiveness. Safe: 1-3. Breaks: high delays IPTV/mDNS. Legal: no RF limit."],
    [/rts/i, "What: RTS/CTS threshold. Down: hidden-node help. Up: less overhead. Safe: ~2347. Breaks: too low wastes airtime. Legal: no RF limit."],
    [/frag|fragment/i, "What: frame fragmentation. Down: noisy-link help. Up: less overhead. Safe: ~2346. Breaks: low value kills speed. Legal: no RF limit."],
    [/coexist|sideband|11n|gi|guard|beam|pmf|preamble/i, "What: PHY/security advanced mode. Aggressive: speed/protection. Conservative: compatibility. Safe: vendor default. Breaks: legacy disconnects. Legal: via channel/power."],
    [/mac|filter|rule/i, "What: MAC allow/deny list. Restrict: fewer clients. Off: normal WPA access. Safe: off unless fixed clients. Breaks: lockout by bad allow list. Legal: no RF limit."],
    [/wps|pin|pbc/i, "What: WPS pairing. On: easy onboarding. Off: safer. Safe: off unless pairing. Breaks: WPS PIN is weak. Legal: no RF limit."],
    [/dhcp|gateway|dns|ipaddr|netmask|reqip|minaddr|maxaddr|bridge|vlan/i, "What: LAN/DHCP/bridge. Wider: more leases. Narrower: control. Safe: gateway/subnet/range consistent. Breaks: device unreachable. Legal: no RF limit."],
    [/sec|encrypt|tkip|aes|pass|key/i, "What: WiFi security. Stronger: privacy. Legacy: old clients. Safe: WPA2-PSK AES. Breaks: WEP/TKIP/WPS weak; password change drops clients. Legal: no RF limit."]
  ];

  function each(list, fn) {
    for (var i = 0; i < list.length; i++) {
      fn(list[i], i);
    }
  }

  function textOf(node) {
    return node ? (node.textContent || node.innerText || "") : "";
  }

  function controlKey(el) {
    var s = (el.id || "") + " " + (el.name || "") + " " + (el.className || "");
    var p = el.parentNode;
    var hops = 0;
    while (p && hops < 3) {
      s += " " + textOf(p);
      p = p.parentNode;
      hops++;
    }
    return s;
  }

  function docFor(el) {
    var key = controlKey(el);
    for (var i = 0; i < DOCS.length; i++) {
      if (DOCS[i][0].test(key)) {
        return DOCS[i][1];
      }
    }
    return "What: Open MitraStar exposed setting. Up/down: depends on value. Safe: vendor default. Breaks: bad values can cut access. Legal: RF rules apply to channel/power/DFS/region.";
  }

  function isHiddenControl(el) {
    return ((el.type || "").toLowerCase() === "hidden") || SKIP_NAMES.test(el.name || "") || SKIP_NAMES.test(el.id || "");
  }

  function isConfigControl(el) {
    var tag = (el.tagName || "").toLowerCase();
    if (tag !== "input" && tag !== "select" && tag !== "textarea" && tag !== "button") {
      return false;
    }
    return !isHiddenControl(el);
  }

  function showElement(el) {
    if (!el) {
      return;
    }
    el.removeAttribute("hidden");
    el.style.visibility = "visible";
    if (el.style.display === "none") {
      el.style.display = "";
    }
    el.className += (el.className ? " " : "") + "openmitrastar-visible";
  }

  function unlockControl(el) {
    if (!isConfigControl(el)) {
      return;
    }
    el.disabled = false;
    el.removeAttribute("disabled");
    if (!SECRET_IDS.test(el.id || "")) {
      el.readOnly = false;
      el.removeAttribute("readonly");
    }
    if (el.options) {
      for (var i = 0; i < el.options.length; i++) {
        el.options[i].disabled = false;
        el.options[i].removeAttribute("disabled");
      }
    }
    if ((" " + el.className + " ").indexOf(" openmitrastar-unlocked-control ") < 0) {
      el.className += (el.className ? " " : "") + "openmitrastar-unlocked-control";
    }
  }

  function protectSecretFields() {
    var ids = ["wifiPass", "wifi24Pass"];
    each(ids, function (id) {
      var el = document.getElementById(id);
      if (!el) {
        return;
      }
      if (!el.getAttribute("data-openmitrastar-secret-ready")) {
        el.value = "";
        el.setAttribute("value", "");
        el.setAttribute("placeholder", "Nueva clave solo si quieres cambiarla");
        el.setAttribute("autocomplete", "new-password");
        el.setAttribute("data-openmitrastar-secret-ready", "1");
      }
      if (!el.getAttribute("data-openmitrastar-help-secret")) {
        var note = document.createElement("span");
        note.className = "openmitrastar-secret-note";
        note.appendChild(document.createTextNode("No se pre-rellena la clave actual."));
        el.parentNode.insertBefore(note, el.nextSibling);
        el.setAttribute("data-openmitrastar-help-secret", "1");
      }
    });
  }

  function addHelp(el) {
    if (!isConfigControl(el) || el.getAttribute("data-openmitrastar-helped")) {
      return;
    }
    var span = document.createElement("span");
    span.className = "help-bubble";
    span.setAttribute("title", docFor(el));
    span.appendChild(document.createTextNode("?"));
    if (el.nextSibling) {
      el.parentNode.insertBefore(span, el.nextSibling);
    } else {
      el.parentNode.appendChild(span);
    }
    el.setAttribute("data-openmitrastar-helped", "1");
  }

  function unlockUi() {
    each(VISIBLE_IDS, function (id) {
      showElement(document.getElementById(id));
    });

    var controls = document.getElementsByTagName("input");
    each(controls, unlockControl);
    controls = document.getElementsByTagName("select");
    each(controls, unlockControl);
    controls = document.getElementsByTagName("textarea");
    each(controls, unlockControl);
    controls = document.getElementsByTagName("button");
    each(controls, unlockControl);

    protectSecretFields();

    controls = document.getElementsByTagName("input");
    each(controls, addHelp);
    controls = document.getElementsByTagName("select");
    each(controls, addHelp);
    controls = document.getElementsByTagName("textarea");
    each(controls, addHelp);
    controls = document.getElementsByTagName("button");
    each(controls, addHelp);
  }

  function scheduleUnlocks() {
    unlockUi();
    window.setTimeout(unlockUi, 250);
    window.setTimeout(unlockUi, 1000);
    window.setTimeout(unlockUi, 3000);
  }

  window.OpenMitraStarUnlock = {
    apply: unlockUi
  };

  if (document.addEventListener) {
    document.addEventListener("DOMContentLoaded", scheduleUnlocks, false);
  }
  if (window.addEventListener) {
    window.addEventListener("load", scheduleUnlocks, false);
  } else if (window.attachEvent) {
    window.attachEvent("onload", scheduleUnlocks);
  }
})();
"""


def reset_overlay() -> None:
    if OVERLAY.exists():
        shutil.rmtree(OVERLAY)
    (OVERLAY / "var" / "www").mkdir(parents=True)
    (OVERLAY / "etc" / "init.d").mkdir(parents=True)
    (OVERLAY / "scripts").mkdir(parents=True)


def copy_runtime_layer() -> None:
    for rel in [
        Path("etc") / "openmitrastar.conf",
        Path("etc") / "init.d" / "S93openmitrastar",
        Path("scripts") / "openmitrastar-apply",
    ]:
        src = PREV_OVERLAY / rel
        dst = OVERLAY / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

    (OVERLAY / "etc" / "openmitrastar-release").write_text(
        "OPENMITRASTAR_VERSION=openmitrastar-0.3-original-ui-unlock\n"
        "OPENMITRASTAR_MODE=original-ui-full-unlock\n",
        encoding="utf-8",
    )


def remove_display_none_from_target_tag(match: re.Match[str]) -> str:
    tag = match.group(0)
    id_match = re.search(r"\bid\s*=\s*(['\"])([^'\"]+)\1", tag)
    if not id_match or id_match.group(2) not in VISIBLE_IDS:
        return tag
    style_match = re.search(r"\bstyle\s*=\s*(['\"])(.*?)\1", tag, flags=re.I)
    if not style_match:
        return tag
    quote = style_match.group(1)
    style = re.sub(r"(^|;)\s*display\s*:\s*none\s*;?", ";", style_match.group(2), flags=re.I)
    style = re.sub(r"\s*;\s*;", ";", style).strip(" ;")
    if style:
        new_style = f" style={quote}{style}{quote}"
    else:
        new_style = ""
    return tag[: style_match.start()] + new_style + tag[style_match.end() :]


def strip_config_disabled_attrs(text: str) -> str:
    text = re.sub(r"\sreadonly\s*=\s*(['\"])(?:readonly|1)\1", "", text, flags=re.I)
    text = re.sub(r"\sdisabled\s*=\s*(['\"])(?:disabled|1)\1", "", text, flags=re.I)
    text = re.sub(r"(\.disabled\s*=\s*)true", r"\1false", text)
    text = re.sub(r"(\.options\s*\[[^\]]+\]\.disabled\s*=\s*)true", r"\1false", text)
    return text


def patch_target_visibility(text: str) -> str:
    text = re.sub(r"<(div|tr|td|span|fieldset)\b[^>]*>", remove_display_none_from_target_tag, text, flags=re.I)
    for control_id in VISIBLE_IDS:
        text = re.sub(
            r"(\$\(\s*['\"]#%s['\"]\s*\)\.)hide\s*\(" % re.escape(control_id),
            r"\1show(",
            text,
        )
    return text


def scrub_secret_prefill(text: str) -> str:
    for placeholder in SECRET_PLACEHOLDERS:
        text = text.replace(f'decodeURIComponent("{placeholder}")', '""')
        text = text.replace(f"decodeURIComponent('{placeholder}')", '""')
        text = text.replace(placeholder, "")
    text = re.sub(
        r'(<input\b[^>]*\bid\s*=\s*["\'](?:wifiPass|wifi24Pass)["\'][^>]*?)\svalue\s*=\s*["\'][^"\']*["\']',
        r"\1",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"<!--input\s+type=\"hidden\"\s+id=\"wlKey1\".*?wlWpaPsk.*?/-->",
        "<!-- Open MitraStar: stock hidden WiFi-key prefill removed. -->",
        text,
        flags=re.I | re.S,
    )
    return text


def inject_assets(text: str) -> str:
    css = '<link href="/openmitrastar_unlock.css" rel="stylesheet" type="text/css"/>'
    js = '<script type="text/javascript" src="/openmitrastar_unlock.js"></script>'
    if "openmitrastar_unlock.css" not in text:
        text = text.replace("</head>", f"{css}\n{js}\n</head>", 1)
    return text


def compact_lines(text: str) -> str:
    return "\n".join(line.strip() for line in text.splitlines() if line.strip()) + "\n"


def patch_html(page: str) -> str:
    text = (SRC_WWW / page).read_text(encoding="utf-8", errors="ignore")
    text = inject_assets(text)
    text = patch_target_visibility(text)
    text = strip_config_disabled_attrs(text)
    text = scrub_secret_prefill(text)
    return text


def write_web_layer() -> None:
    www = OVERLAY / "var" / "www"
    (www / "openmitrastar_unlock.css").write_text(compact_lines(CSS), encoding="utf-8", newline="\n")
    (www / "openmitrastar_unlock.js").write_text(compact_lines(JS), encoding="utf-8", newline="\n")
    for page in TARGET_PAGES:
        (www / page).write_text(patch_html(page), encoding="utf-8", newline="\n")


def main() -> int:
    if not SRC_WWW.exists():
        raise FileNotFoundError(SRC_WWW)
    if not PREV_OVERLAY.exists():
        raise FileNotFoundError(PREV_OVERLAY)
    reset_overlay()
    copy_runtime_layer()
    write_web_layer()
    print(f"generated {OVERLAY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
