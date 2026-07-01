/*
 * M0 Mode-B fidelity surface.
 *
 * Verbatim JavaScript port of the extension's PRODUCTION content scripts:
 *   extension/src/content/extractor_v2.ts  -> window.__m0Extract__()
 *   extension/src/content/executor_v2.ts   -> window.__m0Execute__(action)
 *
 * Both source functions are pure DOM code with NO chrome.* dependencies, so this is a
 * type-stripped copy of the exact logic users run today — not a re-implementation.
 *
 * IMPORTANT: this file MUST stay in sync with the two .ts sources. The drift-guard test
 * `backend/tests/benchmark/test_injection_fidelity.py` fails if the action cases or the
 * fill() event-dispatch sequence diverge. When you change the .ts, change this too.
 *
 * __m0Extract__ returns the same shape as PageContext (minus screenshot_base64); the
 * benchmark PageCapture adds the screenshot. __m0Execute__ returns {success,message,action_id}.
 */
(function () {
  // ───────────────────────── extractor_v2.ts (verbatim) ─────────────────────
  function extractPageContextV2() {
    var INTERACTIVE_SELECTOR = [
      'button',
      'a[href]',
      'input:not([type="hidden"])',
      'select',
      'textarea',
      '[contenteditable="true"]',
      '[role="textbox"]',
      '[role="searchbox"]',
      '[role="button"]:not(button)',
      '[role="listitem"]',
      '[role="option"]',
      '[role="menuitem"]',
      '[role="row"]',
      '[role="tab"]',
      'span[title]:not([title=""])',
    ].join(', ');

    var MAX_ELEMENTS = 150;
    var MAX_TEXT_LENGTH = 1000;

    function sanitizeText(text) {
      return text
        .replace(/\b\d{3}-\d{2}-\d{4}\b/g, '[redacted-ssn]')
        .replace(/\b(?:\d{4}[\s-]?){3}\d{4}\b/g, '[redacted-card]');
    }

    function isVisible(el) {
      if (!(el instanceof HTMLElement)) return false;
      var style = window.getComputedStyle(el);
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
      var rect = el.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    }

    function buildSelector(el) {
      if (el.id) return '#' + CSS.escape(el.id);
      var testId = el.getAttribute('data-testid');
      if (testId) return '[data-testid="' + testId + '"]';

      var ariaLabel = el.getAttribute('aria-label');
      if (ariaLabel) return el.tagName.toLowerCase() + '[aria-label="' + ariaLabel + '"]';

      var title = el.getAttribute('title');
      if (title) return el.tagName.toLowerCase() + '[title="' + title + '"]';

      var placeholder = el.getAttribute('placeholder');
      if (placeholder) return el.tagName.toLowerCase() + '[placeholder="' + placeholder + '"]';

      var parts = [];
      var current = el;
      var depth = 0;
      while (current && current.tagName !== 'BODY' && depth < 5) {
        var part = current.tagName.toLowerCase();
        var role = current.getAttribute('role');
        if (role) part += '[role="' + CSS.escape(role) + '"]';

        var parent = current.parentElement;
        if (parent) {
          var cur = current;
          var siblings = Array.prototype.slice.call(parent.children).filter(function (child) {
            return child.tagName === cur.tagName;
          });
          if (siblings.length > 1) part += ':nth-of-type(' + (siblings.indexOf(current) + 1) + ')';
        }
        parts.unshift(part);
        current = current.parentElement;
        depth++;
      }
      return parts.join(' > ') || el.tagName.toLowerCase();
    }

    function getAccessibilityRole(el) {
      var roleAttr = el.getAttribute('role');
      if (roleAttr) return roleAttr;
      var tag = el.tagName.toLowerCase();
      if (tag === 'button') return 'button';
      if (tag === 'a') return 'link';
      if (tag === 'input') {
        var type = el.type;
        if (type === 'checkbox') return 'checkbox';
        if (type === 'radio') return 'radio';
        return 'textbox';
      }
      if (tag === 'select') return 'combobox';
      if (tag === 'textarea') return 'textbox';
      return 'generic';
    }

    function getAccessibilityName(el) {
      var ariaLabel = el.getAttribute('aria-label');
      if (ariaLabel) return ariaLabel;
      var title = el.getAttribute('title');
      if (title) return title;
      var placeholder = el.getAttribute('placeholder');
      if (placeholder) return placeholder;
      return (el.textContent || '').trim();
    }

    function getAccessibilityState(el) {
      var state = {};
      if (el.getAttribute('aria-expanded')) state['expanded'] = el.getAttribute('aria-expanded') === 'true';
      if (el.getAttribute('aria-checked')) state['checked'] = el.getAttribute('aria-checked') === 'true';
      if (el instanceof HTMLInputElement) {
        if (el.disabled) state['disabled'] = true;
        if (el.readOnly) state['readonly'] = true;
      }
      return state;
    }

    function collectContentBlocks() {
      var candidates = Array.prototype.slice.call(document.querySelectorAll([
        'article', 'li', '[role="listitem"]', '[role="row"]', '[data-testid]', 'section', 'a[href]', 'div',
      ].join(', ')));

      var seen = new Set();
      return candidates
        .filter(isVisible)
        .map(function (el) {
          return { el: el, text: sanitizeText((el.textContent || '').replace(/\s+/g, ' ').trim()).slice(0, 500) };
        })
        .filter(function (o) { return o.text.length >= 40; })
        .filter(function (o) {
          var key = o.text.slice(0, 120);
          if (seen.has(key)) return false;
          seen.add(key);
          return true;
        })
        .slice(0, 36)
        .map(function (o) { return { text: o.text, selector: buildSelector(o.el) }; });
    }

    function collectImages() {
      var seen = new Set();
      return Array.prototype.slice.call(document.querySelectorAll('img'))
        .map(function (img) { return img.currentSrc || img.src || img.getAttribute('data-src') || ''; })
        .filter(function (src) { return src && src.toLowerCase().indexOf('.svg') < 0; })
        .map(function (src) { try { return new URL(src, window.location.href).href; } catch (e) { return ''; } })
        .filter(function (src) {
          if (!src || seen.has(src)) return false;
          seen.add(src);
          return true;
        })
        .slice(0, 25);
    }

    function collectMetadata() {
      var metadata = {};
      var metaSelectors = {
        canonical_url: 'link[rel="canonical"]',
        og_url: 'meta[property="og:url"]',
        og_title: 'meta[property="og:title"]',
        site_name: 'meta[property="og:site_name"]',
        description: 'meta[name="description"]',
      };
      Object.keys(metaSelectors).forEach(function (key) {
        var el = document.querySelector(metaSelectors[key]);
        var value = el instanceof HTMLMetaElement ? el.content
          : el instanceof HTMLLinkElement ? el.href : '';
        if (value) metadata[key] = sanitizeText(value).slice(0, 300);
      });
      return metadata;
    }

    var elements = Array.prototype.slice.call(document.querySelectorAll(INTERACTIVE_SELECTOR))
      .filter(isVisible)
      .slice(0, MAX_ELEMENTS)
      .map(function (el, index) {
        var rect = el.getBoundingClientRect();
        var groundedId = 'el_' + String(index).padStart(3, '0');
        var item = {
          element_id: groundedId,
          type: el.tagName.toLowerCase(),
          text: sanitizeText((el.textContent || '').trim().slice(0, 100)),
          selector: buildSelector(el),
          visible: true,
          role: getAccessibilityRole(el),
          aria_label: el.getAttribute('aria-label') || undefined,
          accessibility_name: getAccessibilityName(el),
          state: getAccessibilityState(el),
          bounding_box: {
            x: Math.round(rect.x), y: Math.round(rect.y),
            width: Math.round(rect.width), height: Math.round(rect.height),
          },
        };
        if (el instanceof HTMLInputElement) {
          item.input_type = el.type;
          item.placeholder = el.placeholder || undefined;
        }
        return item;
      });

    var headings = Array.prototype.slice.call(document.querySelectorAll('h1, h2, h3'))
      .slice(0, 5)
      .map(function (h) { return sanitizeText((h.textContent || '').trim()); })
      .filter(function (text) { return text.length > 0; });

    return {
      url: window.location.href,
      title: document.title,
      metadata: collectMetadata(),
      interactive_elements: elements,
      content_blocks: collectContentBlocks(),
      headings: headings,
      selected_text: '',
      visible_text: sanitizeText((document.body.innerText || '').slice(0, MAX_TEXT_LENGTH)),
      images: collectImages(),
    };
  }

  // ───────────────────────── executor_v2.ts (verbatim) ──────────────────────
  function executeActionV2(action) {
    var action_id = action.action_id;
    var action_type = action.action_type;
    var value = action.value;
    var selector = action.target_selector;

    function safeQuery(sel) {
      try { return document.querySelector(sel); } catch (e) { return null; }
    }

    function waitForElement(sel, timeoutMs) {
      if (timeoutMs === undefined) timeoutMs = 5000;
      return new Promise(function (resolve) {
        var immediate = safeQuery(sel);
        if (immediate) { resolve(immediate); return; }
        var deadline = Date.now() + timeoutMs;
        var interval = setInterval(function () {
          var el = safeQuery(sel);
          if (el) { clearInterval(interval); resolve(el); }
          else if (Date.now() >= deadline) { clearInterval(interval); resolve(null); }
        }, 100);
      });
    }

    function isVisibleElement(candidate) {
      if (!(candidate instanceof HTMLElement)) return false;
      var rect = candidate.getBoundingClientRect();
      var style = window.getComputedStyle(candidate);
      return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
    }

    function findVisibleByText(selectors, text) {
      var needle = (text || '').replace(/\s+/g, ' ').trim().toLowerCase();
      if (!needle) return null;
      var candidates = Array.prototype.slice.call(document.querySelectorAll(selectors.join(', '))).filter(isVisibleElement);
      return candidates.find(function (candidate) {
        return (candidate.textContent || '').replace(/\s+/g, ' ').trim().toLowerCase().indexOf(needle) >= 0;
      }) || null;
    }

    return (async function () {
      var targetEl = null;
      if (selector) targetEl = await waitForElement(selector);

      try {
        switch (action_type) {
          case 'click': {
            if (!targetEl) return { success: false, message: 'Click target not found: ' + selector, action_id: action_id };
            if (targetEl instanceof HTMLElement) {
              targetEl.scrollIntoView({ block: 'center', inline: 'center' });
              targetEl.click();
              return { success: true, message: 'Clicked: ' + selector, action_id: action_id };
            }
            return { success: false, message: 'Target not clickable html element: ' + selector, action_id: action_id };
          }
          case 'fill': {
            if (!targetEl) return { success: false, message: 'Fill target not found: ' + selector, action_id: action_id };
            if (targetEl instanceof HTMLInputElement || targetEl instanceof HTMLTextAreaElement) {
              targetEl.focus();
              targetEl.value = value || '';
              targetEl.dispatchEvent(new Event('input', { bubbles: true }));
              targetEl.dispatchEvent(new Event('change', { bubbles: true }));
              if (targetEl.value !== (value || '')) {
                return { success: false, message: 'Field value was not retained after fill: ' + selector, action_id: action_id };
              }
              return { success: true, message: 'Filled field: ' + selector, action_id: action_id };
            }
            return { success: false, message: 'Target is not a fillable input: ' + selector, action_id: action_id };
          }
          case 'select_option': {
            if (!targetEl) return { success: false, message: 'Select target not found: ' + selector, action_id: action_id };
            if (targetEl instanceof HTMLSelectElement) {
              targetEl.value = value || '';
              targetEl.dispatchEvent(new Event('change', { bubbles: true }));
              return { success: true, message: 'Selected option: ' + value + ' on select: ' + selector, action_id: action_id };
            }
            if (targetEl instanceof HTMLElement) {
              targetEl.scrollIntoView({ block: 'center', inline: 'center' });
              targetEl.click();
              await new Promise(function (resolve) { setTimeout(resolve, 500); });
              var option = findVisibleByText(
                ['[role="option"]', '[role="listitem"]', 'li', 'button', '[data-testid]', 'div', 'span'], value);
              if (option) {
                option.scrollIntoView({ block: 'center', inline: 'center' });
                option.click();
                return { success: true, message: 'Selected visible option: ' + value, action_id: action_id };
              }
            }
            return { success: false, message: 'No visible option found for: ' + value, action_id: action_id };
          }
          case 'choose_date': {
            if (!targetEl) {
              targetEl = findVisibleByText(['[role="gridcell"]', '[role="button"]', 'button', 'td', 'div', 'span'], value);
            }
            if (!targetEl) return { success: false, message: 'Date picker target not found: ' + (selector || value), action_id: action_id };
            if (targetEl instanceof HTMLElement) {
              targetEl.scrollIntoView({ block: 'center', inline: 'center' });
              targetEl.click();
              return { success: true, message: 'Chose date: ' + value + ' via: ' + selector, action_id: action_id };
            }
            return { success: false, message: 'Target not html element for date picker', action_id: action_id };
          }
          case 'hover': {
            if (!targetEl) return { success: false, message: 'Hover target not found: ' + selector, action_id: action_id };
            if (targetEl instanceof HTMLElement) {
              targetEl.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
              targetEl.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
              return { success: true, message: 'Hovered over: ' + selector, action_id: action_id };
            }
            return { success: false, message: 'Target not hoverable html element', action_id: action_id };
          }
          case 'keyboard_shortcut': {
            var active = document.activeElement;
            if (active instanceof HTMLElement && value) {
              var keyEvent = new KeyboardEvent('keydown', { key: value, code: value, bubbles: true });
              active.dispatchEvent(keyEvent);
              return { success: true, message: 'Dispatched keyboard shortcut ' + value + ' to active element.', action_id: action_id };
            }
            return { success: false, message: 'No active element or key specified.', action_id: action_id };
          }
          case 'scroll': {
            var direction = (value == null ? 'down' : value).toLowerCase();
            var delta = direction === 'up' ? -400 : 400;
            if (!selector || selector === 'window') {
              window.scrollBy({ top: delta, behavior: 'smooth' });
              return { success: true, message: 'Scrolled ' + direction + ' window.', action_id: action_id };
            }
            if (targetEl) {
              targetEl.scrollBy({ top: delta, behavior: 'smooth' });
              return { success: true, message: 'Scrolled ' + direction + ' on: ' + selector, action_id: action_id };
            }
            return { success: false, message: 'Scroll target not found: ' + selector, action_id: action_id };
          }
          case 'navigate': {
            if (!value) return { success: false, message: 'No URL provided.', action_id: action_id };
            window.location.href = value;
            return { success: true, message: 'Navigating to: ' + value, action_id: action_id };
          }
          case 'wait': {
            var waitMs = Number(value == null ? 2000 : value);
            await new Promise(function (resolve) { setTimeout(resolve, waitMs); });
            return { success: true, message: 'Waited ' + waitMs + 'ms', action_id: action_id };
          }
          default:
            return { success: false, message: 'Action type not supported in V2: ' + action_type, action_id: action_id };
        }
      } catch (err) {
        return { success: false, message: 'Runtime execution error: ' + String(err), action_id: action_id };
      }
    })();
  }

  window.__m0Extract__ = extractPageContextV2;
  window.__m0Execute__ = executeActionV2;
})();
