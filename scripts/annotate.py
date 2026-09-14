"""Screenshot pages with Playwright and circle each catalogued feature in red.

    python scripts/annotate.py --site luzzpickleball.com
    python scripts/annotate.py --url https://luzzpickleball.com/ --style box

Locates features by searching the live DOM for the `evidence` quote already
stored in the catalog, draws a red ellipse plus a numbered badge around the
match, then saves a full-page shot and a per-feature crop.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db

SHOT_DIR = db.SHOT_DIR                         # override with CATALOG_SHOTS
SCALE = 2                                      # device pixel ratio; crops multiply by this
# Playwright defaults to 30s for a screenshot. A 20,000px commerce page with
# lazy images routinely needs more than that, and more still when several
# annotator processes compete for the same CPU.
SHOT_TIMEOUT_MS = 180_000
VIEWPORT = {"width": 1440, "height": 900}

# ---------------------------------------------------------------- needles

RE_MD = re.compile(r"[*_`~]+")
RE_SYM = re.compile(r"[™®©‘’“”]")
RE_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    return RE_WS.sub(" ", RE_SYM.sub("", RE_MD.sub("", text or ""))).strip()


RE_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")   # [text](url) -> text
RE_MD_BRACKET = re.compile(r"\[([^\]]*)\]")         # [text]      -> text
RE_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){2,}$")   # url-slug, never on-page
SEPARATORS = r"\s*(?:/|\||\.\.\.|\s-\s|,)\s*"
# Generic words that match half a storefront. A needle this vague will happily
# circle the wrong element - or a bot-challenge page - and report it as a hit.
STOP = {"with", "from", "that", "this", "their", "product", "products",
        "page", "site", "section", "module", "display",
        "collection", "collections", "content", "options", "available",
        "shipping", "support", "program", "programme", "featured", "pricing",
        "customer", "customers", "shopping", "checkout", "category"}


def _clean_evidence(text: str) -> str:
    ev = normalize(text)
    ev = RE_MD_LINK.sub(r"\1", ev)
    ev = RE_MD_BRACKET.sub(r"\1", ev)
    return ev.replace("~", "").strip()


def needles(feature: dict) -> list[str]:
    """Search strings to try, most specific first."""
    out: list[str] = []
    ev = _clean_evidence(feature.get("evidence") or "")

    if ev and not RE_SLUG.match(ev):
        out.append(ev)
        # evidence often stitches several separate on-page strings together
        for part in re.split(SEPARATORS, ev):
            part = part.strip(" \"'()")
            # a 3-character fragment is not evidence of anything; it will
            # match somewhere on any page and report a false hit
            if len(part) >= 12 and not RE_SLUG.match(part):
                out.append(part)
        head = re.split(r"[.;:]", ev)[0].strip()
        if len(head) >= 5:
            out.append(head)
        words = ev.split()
        if len(words) > 8:
            out.append(" ".join(words[:8]))

    name = normalize(feature.get("name") or "")
    if len(name) >= 5:
        out.append(name)
        # last resort: the most distinctive single word in the name
        for w in sorted(name.split(), key=len, reverse=True):
            w = w.strip("()")
            if len(w) >= 7 and w.lower() not in STOP:
                out.append(w)
                break

    seen, uniq = set(), []
    for n in out:
        k = n.lower()
        if k not in seen and len(n) >= 3:
            seen.add(k)
            uniq.append(n)
    return uniq[:12]


# ---------------------------------------------------------------- browser JS

# Finds the deepest visible element containing a needle, draws the marker,
# and returns document-space coordinates.
JS_ANNOTATE = r"""
(payload) => {
  const {items, style} = payload;

  // dedicated overlay layer, appended to body so it paints above page content
  let host = document.getElementById("__fx_overlay");
  if (!host) {
    host = document.createElement("div");
    host.id = "__fx_overlay";
    host.style.cssText = "position:absolute;left:0;top:0;width:0;height:0;" +
                         "overflow:visible;pointer-events:none;z-index:2147483000;display:block!important;visibility:visible!important";
    document.body.appendChild(host);
  }
  // body must be a positioned ancestor for our doc-space coords to hold
  if (getComputedStyle(document.body).position === "static") {
    document.body.style.position = "relative";
  }
  const bodyRect = document.body.getBoundingClientRect();
  const bodyX = bodyRect.left + window.scrollX;
  const bodyY = bodyRect.top + window.scrollY;

  const results = [];
  const norm = s => (s || "").replace(/\s+/g, " ").trim().toLowerCase();

  // smallest visible element containing the needle == tightest circle
  function findSmallest(needle, maxArea) {
    const n = norm(needle);
    if (!n) return null;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_ELEMENT);
    let best = null, bestArea = Infinity;
    while (walker.nextNode()) {
      const el = walker.currentNode;
      const tag = el.tagName;
      if (tag === "SCRIPT" || tag === "STYLE" || tag === "NOSCRIPT") continue;
      if (el.id === "__fx_overlay" || el.closest("#__fx_overlay")) continue;
      if (!norm(el.textContent).includes(n)) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 8 || r.height < 8) continue;
      // Announcement bars and quote carousels duplicate their text into clones
      // parked off-canvas to the left. The clone matches the needle, but its
      // coordinates are negative, so it falls outside the screenshot and no
      // crop can be cut - three features lost their close-up this way. Skip
      // the clones so the on-canvas copy wins.
      if (r.right + window.scrollX < 0 || r.bottom + window.scrollY < 0) continue;
      const cs = getComputedStyle(el);
      if (cs.visibility === "hidden" || cs.display === "none" || cs.opacity === "0") continue;
      const area = r.width * r.height;
      if (maxArea && area > maxArea) continue;   // ancestor, not the feature
      if (area < bestArea) { bestArea = area; best = el; }
    }
    return best;
  }

  items.forEach((item, idx) => {
    let el = null, matched = null, method = "failed";
    // pass 1 rejects oversized ancestors so the circle hugs the real element
    const TIGHT = 520000;
    // Pass 2 used to run uncapped, which let a needle match a whole page
    // section: five features were "located" as ellipses up to 1440x4918, which
    // circle a third of the page and point at nothing. A match that large is
    // not a location, so cap it and let the feature report as failed instead -
    // that surfaces it in `query.py --failed` as evidence worth rewriting.
    const LOOSE = 2000000;
    for (const cap of [TIGHT, LOOSE]) {
      for (let i = 0; i < item.needles.length; i++) {
        el = findSmallest(item.needles[i], cap);
        if (el) {
          matched = item.needles[i];
          method = (i === 0 && cap === TIGHT) ? "exact"
                 : (cap === TIGHT ? "fragment" : "loose");
          break;
        }
      }
      if (el) break;
    }
    if (!el) { results.push({id: item.id, found: false, method: "failed"}); return; }

    const r = el.getBoundingClientRect();
    const docX = r.left + window.scrollX;
    const docY = r.top + window.scrollY;
    const w = r.width, h = r.height;
    // coords relative to the positioned <body>, which is what host sits in
    const x = docX - bodyX;
    const y = docY - bodyY;

    // pad so the marker sits around the element, not on it
    const px = Math.max(12, Math.min(46, w * 0.08));
    const py = Math.max(10, Math.min(34, h * 0.22));

    const box = document.createElement("div");
    // zero-width space: many themes ship `div:empty{display:none}`, which
    // would silently hide an empty marker
    box.textContent = "​";
    box.style.cssText = [
      "position:absolute!important",
      "display:block!important",
      "visibility:visible!important",
      "opacity:1!important",
      "left:" + (x - px) + "px",
      "top:" + (y - py) + "px",
      "width:" + (w + px * 2) + "px",
      "height:" + (h + py * 2) + "px",
      "border:4px solid #FF0033!important",
      (style === "ellipse" ? "border-radius:50%" : "border-radius:8px") + "!important",
      "box-shadow:0 0 0 2px rgba(255,255,255,.9), 0 0 16px rgba(255,0,51,.5)!important",
      "background:transparent!important",
      "pointer-events:none",
      "margin:0!important","padding:0!important",
      "font-size:0!important","line-height:0!important",
      "clip-path:none!important","transform:none!important",
      "box-sizing:border-box!important"
    ].join(";");
    host.appendChild(box);

    // badge hugs the marker's top-left, nudged inward so it never falls off-page
    const bx = Math.max(2, x - px - 10);
    const by = Math.max(2, y - py - 10);
    const badge = document.createElement("div");
    badge.textContent = String(idx + 1);
    badge.style.cssText = [
      "position:absolute!important",
      "display:block!important",
      "visibility:visible!important","opacity:1!important",
      "left:" + bx + "px",
      "top:" + by + "px",
      "min-width:30px","height:30px",
      "padding:0 7px","border-radius:15px",
      "background:#FF0033","color:#fff",
      "font:700 16px/30px system-ui,-apple-system,sans-serif",
      "text-align:center",
      "box-shadow:0 2px 8px rgba(0,0,0,.4)",
      "pointer-events:none"
    ].join(";");
    host.appendChild(badge);

    results.push({id: item.id, found: true, method, matched,
                  x: Math.round(docX), y: Math.round(docY),
                  w: Math.round(w), h: Math.round(h)});
  });

  return results;
}
"""

# Overlay killer. Defined once, used three ways: an explicit call at each
# capture checkpoint, and a MutationObserver + interval installed as an init
# script so it also catches popups that appear on a delay.
#
# The observer is not belt-and-braces. GAMMA's spin-to-win wheel fires on a
# timer: it appeared AFTER the clean plate was taken and BEFORE the annotated
# one, so the clean plate looked perfect and the annotated plate - the one the
# crops are cut from - was ruined. Worse, the modal locked body scrolling, and
# a full-page capture of a scroll-locked page paints only the visible region,
# so 80% of the image came out blank white. Nine crops were solid white before
# this was fixed.
OVERLAY_KILLER = r"""
window.__killOverlays = (opts) => {
  // Never click page controls: on a storefront that can add to cart, open a
  // drawer, or navigate. Remove overlays outright instead - no side effects.
  let removed = 0;
  const vw = innerWidth, vh = innerHeight;

  const looksOverlay = (el) => {
    const s = ((el.className && el.className.baseVal !== undefined
                  ? el.className.baseVal : el.className) || "") + " " + (el.id || "");
    return /popup|modal|dialog|overlay|backdrop|drawer|newsletter|subscribe/i.test(String(s))
        // support panels and privacy notices that are too small to trip "covers"
        || /chat-card|chat-window|intercom|zendesk|drift-|tidio|gorgias|livechat|privacy/i.test(String(s))
        // popup vendors and the gamified discount widgets they ship
        || /klaviyo|privy|justuno|attentive|postscript|optimonk|sumo|wheelio|spin|fortune|wheel/i.test(String(s))
        || el.getAttribute("role") === "dialog"
        || el.getAttribute("aria-modal") === "true";
  };

  // Consent bars are wide but short, so they miss the "big" test that catches
  // modals, and they sit over real content at the top or bottom of the page.
  // Matched by name only: a fixed top bar is otherwise a legitimate feature -
  // GAMMA's free-shipping announcement bar is one we deliberately circle.
  const looksConsent = (el) => {
    const s = ((el.className && el.className.baseVal !== undefined
                  ? el.className.baseVal : el.className) || "") + " " + (el.id || "");
    return /cookie|consent|gdpr|ccpa|cmp-/i.test(String(s));
  };

  // Walk shadow roots too. Consent CMPs and widget vendors mount their panel
  // inside a custom element's shadow DOM, where querySelectorAll cannot reach
  // it - Selkirk's privacy modal survived every rule above for exactly this
  // reason, and a text search of the document could not even find its copy.
  const scan = (root, depth) => {
    if (depth > 4) return;
    root.querySelectorAll("*").forEach(el => {
      if (el.shadowRoot) scan(el.shadowRoot, depth + 1);
      check(el);
    });
  };

  const check = (el) => {
    if (!el.isConnected) return;
    // our own annotation layer is absolutely positioned at a huge z-index;
    // removing it would delete the circles we came here to draw
    if (el.id === "__fx_overlay" || el.closest("#__fx_overlay")) return;
    const cs = getComputedStyle(el);
    if (cs.position !== "fixed" && cs.position !== "absolute") return;
    if (cs.display === "none" || cs.visibility === "hidden") return;
    // z-index:auto parses to NaN. Requiring a number here is what let GAMMA's
    // popup through: it is a fixed, full-viewport <iframe id=attentive_creative>
    // with z-index:auto, which paints above everything by DOM order alone and
    // needs no numeric index at all. Never gate solely on this.
    const z = parseInt(cs.zIndex, 10);
    const raised = Number.isFinite(z) && z > 100;
    const fixed = cs.position === "fixed";
    const r = el.getBoundingClientRect();
    const covers = r.width >= vw * 0.85 && r.height >= vh * 0.85;
    const big = r.width >= 260 && r.height >= 180;
    // Ignore panels parked off-screen - closed cart/search drawers match the
    // name test but are not covering anything, and one of them may hold copy.
    const onScreen = r.left < vw && r.right > 0 && r.top < vh && r.bottom > 0;
    // A fixed layer spanning the viewport is a dimmer or a popup by
    // construction; real content is never positioned that way.
    const fixedFull = fixed && covers;
    // Popup apps mount inside an iframe, where the class names above live on
    // the far side of the boundary and are unreadable from here.
    const popIframe = el.tagName === "IFRAME" && big && (fixed || raised);
    const consentBar = looksConsent(el) && fixed && onScreen && r.width >= vw * 0.5;
    // A closed drawer is parked off-screen by a transform - Selkirk's
    // #dropdown-cart sits at left:1440 in a 1440 viewport. It is invisible to a
    // real visitor, and the onScreen test below correctly skips it, but a
    // full-page capture paints fixed layers anyway and the cart drawer landed
    // across a quarter of the plate. Nothing we circle lives inside a closed
    // drawer, so remove it.
    const parkedPanel = fixed && big && !onScreen;
    if (fixedFull
        || (covers && raised)
        || (looksOverlay(el) && big && onScreen && (fixed || raised))
        || (popIframe && onScreen)
        || consentBar
        || parkedPanel) {
      el.remove(); removed++;
    }
  };

  scan(document.body, 0);

  // Modals routinely lock scrolling. Left in place, a full-page screenshot of
  // the locked page is blank below the fold, so this matters even when the
  // overlay itself is already gone.
  for (const el of [document.documentElement, document.body]) {
    el.style.overflow = ""; el.style.position = ""; el.style.top = "";
    el.classList.remove("no-scroll", "modal-open", "overflow-hidden", "scroll-lock");
  }
  // Only on an explicit call: the observer must never scroll, or it fights
  // JS_AUTOSCROLL and lazy images never load.
  if (opts && opts.scroll) window.scrollTo(0, 0);
  return removed;
};
"""

JS_DISMISS = "() => (window.__killOverlays ? window.__killOverlays({scroll: true}) : 0)"

# Installed via add_init_script so it is armed before any page script runs.
JS_KILLER_INSTALL = OVERLAY_KILLER + r"""
(() => {
  // Throttled: the scan touches every element in the body, and removing a node
  // is itself a mutation, so an unthrottled observer would thrash on any page
  // with a carousel.
  let pending = false;
  const run = () => {
    if (pending) return;
    pending = true;
    setTimeout(() => {
      pending = false;
      try { window.__killOverlays(); } catch (e) {}
    }, 250);
  };
  const arm = () => {
    run();
    new MutationObserver(run).observe(document.documentElement,
                                      {childList: true, subtree: true});
    // Some popups are already in the DOM and merely unhidden by a timer, which
    // mutates no nodes the observer can see.
    setInterval(run, 1000);
  };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", arm);
  } else {
    arm();
  }
})();
"""

JS_EXPAND = r"""
() => {
  // Open content accordions, but not navigation. Shopify themes build their
  // mega-menus out of <details>, so opening every one drapes the whole menu
  // over the hero and the plate captures the menu instead of the page. The
  // aria-expanded path below has always had this guard; this one did not.
  document.querySelectorAll("details").forEach(d => {
    if (d.closest("nav, header, [role=navigation]")) return;
    d.open = true;
  });
  let n = 0;
  const UNSAFE = /add to cart|add to bag|buy|checkout|pre-?order|purchase|subscribe|sign ?up|pay/i;
  document.querySelectorAll('[aria-expanded="false"]').forEach(el => {
    if (n++ > 60) return;
    // never trigger a commerce action just to reveal copy
    const label = ((el.textContent || "") + " " +
                   (el.getAttribute("aria-label") || "")).slice(0, 120);
    if (UNSAFE.test(label)) return;
    if (el.closest("form")) return;

    // Support widgets are disclosure controls too, and opening one drapes a
    // 420x600 panel across the page. Selkirk's #chat-fab has no text label, so
    // the UNSAFE word test above cannot see it - match the widget by name.
    const WIDGET = /chat|messenger|intercom|zendesk|drift|tidio|gorgias|helpdesk|livechat|support-widget/i;
    const idcls = (el.id || "") + " " + String(
      el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className || "");
    if (WIDGET.test(idcls) || (el.closest("[id*=chat],[class*=chat]") !== null)) return;

    // Never click something that can navigate. JOOLA's mega-menu puts
    // aria-expanded on real <a href> items, so "expanding" the nav actually
    // loaded a different page - and the screenshot was of that page, silently.
    // Only same-page anchors (#, javascript:) are safe to click.
    const a = el.closest("a[href]");
    if (a) {
      const href = a.getAttribute("href") || "";
      const samePage = href.startsWith("#") ||
                       href.toLowerCase().startsWith("javascript:") ||
                       href === "" ||
                       href === window.location.href ||
                       href === window.location.pathname;
      if (!samePage) return;
    }
    // Nav and header disclosure widgets are menus, not content. Nothing we
    // want to measure lives behind them, and they are the ones that navigate.
    if (el.closest("nav, header, [role=navigation]")) return;

    try { el.click(); } catch (e) {}
  });
  return n;
}
"""

JS_REVEAL_PANELS = r"""
() => {
  // Tabbed PDPs hide the specs and technology copy in inactive panels, so a
  // text search never finds them. Reveal the panels with CSS instead of
  // clicking - clicking tab controls on a live store is how you end up firing
  // something you did not mean to. Stacked panels are forced back into normal
  // flow so they do not overlap and produce wrong boxes.
  const SEL = [
    '[role="tabpanel"]',
    '.tab-panel', '.tabs__panel', '.tab-content', '.product-tab',
    '[data-tab-panel]', '[id*="product-tab"]', '[id*="tab-panel"]',
  ].join(",");
  let n = 0;
  document.querySelectorAll(SEL).forEach(el => {
    if (n++ > 40) return;
    el.removeAttribute("hidden");
    el.removeAttribute("aria-hidden");
    el.style.setProperty("display", "block", "important");
    el.style.setProperty("visibility", "visible", "important");
    el.style.setProperty("opacity", "1", "important");
    el.style.setProperty("height", "auto", "important");
    el.style.setProperty("max-height", "none", "important");
    el.style.setProperty("overflow", "visible", "important");
    // absolutely-positioned panels stack on top of each other; put them back
    const pos = getComputedStyle(el).position;
    if (pos === "absolute" || pos === "fixed") {
      el.style.setProperty("position", "static", "important");
    }
    el.style.setProperty("transform", "none", "important");
  });
  return n;
}
"""

JS_LOAD_LAZY = r"""
() => {
  // Scrolling triggers most lazy loaders, but not all of them: Six Zero's hero
  // is a Flickity carousel that loads slide images from data-flickity-lazyload
  // when a slide is selected, so the hero captured as a flat black box and the
  // page finished with 91 of 132 images loaded. Promote the deferred URLs by
  // hand instead of hoping the site's own loader fires.
  let n = 0;
  const SRC = ["data-src", "data-original", "data-lazy", "data-flickity-lazyload"];
  const SET = ["data-srcset", "data-lazy-srcset", "data-flickity-lazyload-srcset"];
  document.querySelectorAll("img").forEach(img => {
    for (const a of SRC) {
      const v = img.getAttribute(a);
      if (v && !(img.getAttribute("src") || "").includes(v)) { img.setAttribute("src", v); n++; break; }
    }
    for (const a of SET) {
      const v = img.getAttribute(a);
      if (v) { img.setAttribute("srcset", v); break; }
    }
    if (img.getAttribute("loading") === "lazy") img.setAttribute("loading", "eager");
  });
  document.querySelectorAll("[data-bg],[data-background],[data-bgset]").forEach(el => {
    const v = el.getAttribute("data-bg") || el.getAttribute("data-background")
           || el.getAttribute("data-bgset");
    if (v) { el.style.backgroundImage = "url(" + v.split(" ")[0] + ")"; n++; }
  });
  return n;
}
"""

JS_SETTLE_ANIMATIONS = r"""
() => {
  // Scroll-triggered animation libraries (AOS and friends) start elements at
  // opacity:0 and reveal them when they enter the viewport. A full-page capture
  // resizes the viewport, the library recomputes, and anything it decides is
  // out of view snaps back to hidden - Six Zero's hero images were fully loaded
  // (complete, naturalWidth 1440) and still captured as a flat black box
  // because the wrapper sat at opacity:0. Force the finished state.
  let n = 0;
  document.querySelectorAll("[data-aos]").forEach(el => {
    el.classList.add("aos-animate");
    el.style.setProperty("opacity", "1", "important");
    el.style.setProperty("transform", "none", "important");
    el.style.setProperty("transition", "none", "important");
    n++;
  });
  // the wrappers these libraries hide are often the parent, not the tagged node
  document.querySelectorAll("[class*=hero__image-wrapper], [class*=aos-init]").forEach(el => {
    if (getComputedStyle(el).opacity === "0") {
      el.style.setProperty("opacity", "1", "important");
      el.style.setProperty("transform", "none", "important");
      n++;
    }
  });
  return n;
}
"""

JS_AUTOSCROLL = r"""
async () => {
  await new Promise(res => {
    let y = 0;
    const step = () => {
      window.scrollBy(0, 600); y += 600;
      if (y < document.body.scrollHeight && y < 60000) setTimeout(step, 60);
      else { window.scrollTo(0, 0); setTimeout(res, 400); }
    };
    step();
  });
}
"""


# ---------------------------------------------------------------- main flow

CHALLENGE_MARKERS = (
    "verify you are human",
    "connection needs to be verified",
    "checking your browser",
    "attention required",
    "cf-challenge",
    "just a moment",
)


def same_page(requested: str, actual: str) -> bool:
    """True if `actual` is still the page we asked for.

    Query strings and fragments are ignored - Shopify appends ?variant=... on
    its own, which is not a navigation away from the product.
    """
    from urllib.parse import urlsplit
    a, b = urlsplit(requested), urlsplit(actual)
    return (a.netloc.lower().lstrip("www.") == b.netloc.lower().lstrip("www.")
            and a.path.rstrip("/") == b.path.rstrip("/"))


def is_challenged(page) -> bool:
    """True when we got a bot wall instead of the page.

    Checks three independent signals, because the wall does not always look
    the same: the visible copy, a Turnstile/challenge iframe, and a body that
    is simply too short to be a real commerce page.
    """
    try:
        title = (page.title() or "").lower()
        body = (page.inner_text("body") or "")
    except Exception:
        return False

    blob = (title + " " + body[:2000]).lower()
    if any(m in blob for m in CHALLENGE_MARKERS):
        return True

    try:
        frames = page.evaluate(
            "() => [...document.querySelectorAll('iframe')]"
            ".map(f => f.src || '').join(' ')"
        )
        if "challenges.cloudflare.com" in frames or "turnstile" in frames:
            return True
    except Exception:
        pass

    # A real page we bothered to scrape has far more text than this. A near
    # empty body means we are looking at an interstitial of some kind.
    return len(body.strip()) < 400


def annotate_page(pw, con, page_row, style: str, wait_ms: int,
                  locale: str | None = None) -> dict:
    url = page_row["url"]
    domain = db.domain_of(url)
    feats = con.execute(
        "SELECT id, name, evidence, category FROM features "
        "WHERE page_id = ? ORDER BY id", (page_row["id"],)
    ).fetchall()
    if not feats:
        return {"url": url, "total": 0, "found": 0}

    items = [{"id": f["id"], "needles": needles(dict(f))} for f in feats]

    browser = pw.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
    ctx_args = {"viewport": VIEWPORT, "device_scale_factor": SCALE}
    if locale:
        ctx_args["locale"] = locale
        ctx_args["extra_http_headers"] = {"Accept-Language": locale + ",en;q=0.9"}
    ctx = browser.new_context(**ctx_args)
    ctx.add_init_script(JS_KILLER_INSTALL)   # keeps timed popups dead all session
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            pass
        # A bot challenge renders a real page with a real screenshot, so every
        # needle simply misses and the run reports a confident 0/N. That silent
        # zero reads like "the evidence is wrong" and sends you debugging the
        # wrong thing. Detect it and say so.
        if is_challenged(page):
            return {"url": url, "total": len(feats), "found": 0,
                    "blocked": True}
        try:
            page.keyboard.press("Escape")
            page.evaluate(JS_DISMISS)         # kill cookie/email modals
            page.wait_for_timeout(400)
        except Exception:
            pass
        page.evaluate(JS_AUTOSCROLL)          # trigger lazy-loaded media
        try:
            page.evaluate(JS_LOAD_LAZY)       # and the loaders scrolling misses
            # give the promoted URLs a chance to actually arrive, but never
            # block the capture on a single slow asset
            page.wait_for_function(
                "() => Array.from(document.images).filter(i => !i.complete).length <= 2",
                timeout=15_000)
        except Exception:
            pass
        try:
            page.evaluate(JS_EXPAND)          # open accordions so copy is measurable
            page.wait_for_timeout(600)
        except Exception:
            pass
        if wait_ms:
            page.wait_for_timeout(wait_ms)

        # Nothing we do above is supposed to navigate. If the URL drifted, we
        # are about to screenshot the wrong page and store its coordinates
        # against this page's features - which is worse than failing, because
        # it looks like a successful capture. Bail loudly instead.
        if not same_page(url, page.url):
            return {"url": url, "total": len(feats), "found": 0,
                    "navigated_to": page.url}

        try:
            page.evaluate(JS_DISMISS)
            page.wait_for_timeout(300)
        except Exception:
            pass
        try:
            page.evaluate(JS_SETTLE_ANIMATIONS)
            page.wait_for_timeout(250)
        except Exception:
            pass
        slug0 = db.slugify(url.split(domain, 1)[-1]) or "index"
        out_dir0 = SHOT_DIR / domain
        out_dir0.mkdir(parents=True, exist_ok=True)
        # clean plate first, so the web UI can draw its own overlays
        page.screenshot(path=str(out_dir0 / f"{slug0[:70]}-clean.png"), full_page=True,
                        timeout=SHOT_TIMEOUT_MS)

        results = page.evaluate(JS_ANNOTATE, {"items": items, "style": style})

        # Last checkpoint before the plate the crops are cut from. The annotate
        # pass above takes seconds, which is long enough for a timed popup to
        # land; the killer skips #__fx_overlay so the circles survive.
        try:
            page.evaluate(JS_DISMISS)
            page.evaluate(JS_SETTLE_ANIMATIONS)
            page.wait_for_timeout(200)
        except Exception:
            pass

        slug = db.slugify(url.split(domain, 1)[-1]) or "index"
        out_dir = SHOT_DIR / domain
        out_dir.mkdir(parents=True, exist_ok=True)
        shot = out_dir / f"{slug[:70]}.png"
        page.screenshot(path=str(shot), full_page=True, timeout=SHOT_TIMEOUT_MS)
    finally:
        ctx.close()
        browser.close()

    rel_shot = str(shot.relative_to(db.ROOT)).replace("\\", "/")
    crops_made = _save(con, feats, results, page_row, shot, rel_shot, out_dir, slug)
    found = sum(1 for r in results if r.get("found"))
    return {"url": url, "total": len(feats), "found": found,
            "shot": rel_shot, "crops": crops_made}


def _save(con, feats, results, page_row, shot, rel_shot, out_dir, slug) -> int:
    """Persist coordinates and cut a close-up crop per located feature."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None      # full-page shots are legitimately huge

    by_id = {f["id"]: f for f in feats}
    img = Image.open(shot)
    crop_dir = out_dir / slug[:70]
    made = 0

    for i, r in enumerate(results, 1):
        fid = r["id"]
        name = by_id[fid]["name"]
        crop_rel = None
        if r.get("found"):
            crop_dir.mkdir(parents=True, exist_ok=True)
            pad = 90
            l = max(0, (r["x"] - pad)) * SCALE
            t = max(0, (r["y"] - pad)) * SCALE
            rr = min(img.width, (r["x"] + r["w"] + pad) * SCALE)
            bb = min(img.height, (r["y"] + r["h"] + pad) * SCALE)
            if rr > l and bb > t:
                crop_path = crop_dir / f"{i:02d}-{db.slugify(name)[:50]}.png"
                img.crop((int(l), int(t), int(rr), int(bb))).save(crop_path)
                crop_rel = str(crop_path.relative_to(db.ROOT)).replace("\\", "/")
                made += 1

        con.execute(
            "INSERT INTO annotations (feature_id,page_id,screenshot_path,crop_path,"
            "x,y,w,h,matched_text,match_method) VALUES (?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(feature_id) DO UPDATE SET "
            "page_id=excluded.page_id, screenshot_path=excluded.screenshot_path, "
            "crop_path=excluded.crop_path, x=excluded.x, y=excluded.y, w=excluded.w, "
            "h=excluded.h, matched_text=excluded.matched_text, "
            "match_method=excluded.match_method, created_at=datetime('now')",
            (fid, page_row["id"], rel_shot, crop_rel, r.get("x"), r.get("y"),
             r.get("w"), r.get("h"), r.get("matched"), r.get("method")),
        )
    con.commit()
    img.close()
    return made


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", help="domain, e.g. luzzpickleball.com")
    ap.add_argument("--url", help="single page URL")
    ap.add_argument("--style", choices=["ellipse", "box"], default="ellipse")
    ap.add_argument("--wait", type=int, default=1500)
    ap.add_argument("--locale", help="e.g. en-IN, to match the scraped currency")
    ap.add_argument("--pace", type=int, default=10,
                    help="seconds to wait between pages (default 10). Firing "
                         "page loads back to back is what trips bot walls.")
    ap.add_argument("--retry-blocked", type=int, default=1,
                    help="times to retry a blocked page, with backoff")
    a = ap.parse_args()

    con = db.connect()
    if a.url:
        rows = con.execute("SELECT * FROM pages WHERE url = ?", (a.url,)).fetchall()
    elif a.site:
        rows = con.execute(
            "SELECT p.* FROM pages p JOIN sites s ON s.id = p.site_id "
            "WHERE s.domain = ? ORDER BY p.id", (a.site,)).fetchall()
    else:
        ap.error("pass --site or --url")

    if not rows:
        print("no matching pages in the catalog", file=sys.stderr)
        return 2

    from playwright.sync_api import sync_playwright
    import time

    with sync_playwright() as pw:
        for i, row in enumerate(rows):
            # Space the requests out. These are live third-party sites, and a
            # burst of five instant page loads is exactly what gets an IP
            # served a bot challenge instead of the page.
            if i:
                time.sleep(a.pace)

            r = annotate_page(pw, con, row, a.style, a.wait, a.locale)

            # One backoff retry, then give up. Never loop on a wall.
            attempt = 0
            while r.get("blocked") and attempt < a.retry_blocked:
                attempt += 1
                backoff = 60 * attempt
                print(f"  ...   blocked, waiting {backoff}s before one retry")
                time.sleep(backoff)
                r = annotate_page(pw, con, row, a.style, a.wait, a.locale)

            if r.get("navigated_to"):
                print(f"  DRIFTED  {r['url']}")
                print(f"           ended up on {r['navigated_to']} - something "
                      f"on the page navigated; not saving a wrong screenshot")
            elif r.get("blocked"):
                print(f"  BLOCKED  bot challenge served instead of {r['url']}"
                      f"  ({r['total']} features left unpinned - retry later,"
                      f" and slow down)")
            elif r["total"] == 0:
                print(f"  --   no features linked to {r['url']}")
            else:
                print(f"  OK   {r['found']}/{r['total']} circled  {r['shot']}"
                      f"  (+{r['crops']} crops)")
    con.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
