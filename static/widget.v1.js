/**
 * FlyRank Embeddable Lead-Capture Widget Client (v1.0.0)
 * Ultra-lightweight, zero-dependency embed script.
 * Handles configuration fetching, responsive rendering, honeypot spam protection,
 * and resilient cross-origin submissions.
 */

(function () {
  'use strict';

  // 1. Locate current script element and extract configuration params
  const currentScript =
    document.currentScript ||
    (function () {
      const scripts = document.getElementsByTagName('script');
      return scripts[scripts.length - 1];
    })();

  if (!currentScript) {
    console.error('[FlyRank Widget] Could not determine embed script tag.');
    return;
  }

  const scriptUrl = new URL(currentScript.src, window.location.href);
  const widgetId = scriptUrl.searchParams.get('id');
  const baseUrl = scriptUrl.origin;

  if (!widgetId) {
    console.error('[FlyRank Widget] Missing required "?id=<widget_id>" parameter in script src.');
    return;
  }

  // 2. Fetch Widget Configuration
  const configEndpoint = `${baseUrl}/widgets/${encodeURIComponent(widgetId)}/config`;

  fetch(configEndpoint, {
    method: 'GET',
    headers: { 'Accept': 'application/json' },
  })
    .then((res) => {
      if (!res.ok) {
        throw new Error(`Widget config failed with status ${res.status}`);
      }
      return res.json();
    })
    .then((config) => {
      renderWidget(config, baseUrl);
    })
    .catch((err) => {
      console.error('[FlyRank Widget] Failed to initialize widget:', err);
    });

  // 3. Render Widget Form & Setup Interactivity
  function renderWidget(config, apiBase) {
    const isDark = config.display_options && config.display_options.theme === 'dark';
    const accentColor = (config.display_options && config.display_options.accent_color) || '#2563eb';
    const isPopover = config.type === 'cta_popover' || (config.display_options && config.display_options.position === 'bottom-right');

    const container = document.createElement('div');
    container.id = `flyrank-widget-${config.id}`;
    container.className = `flyrank-container ${isPopover ? 'flyrank-popover' : 'flyrank-inline'}`;

    // Scoped CSS styles
    const style = document.createElement('style');
    style.textContent = `
      #flyrank-widget-${config.id} {
        --fr-bg: ${isDark ? '#0f172a' : '#ffffff'};
        --fr-text: ${isDark ? '#f8fafc' : '#0f172a'};
        --fr-subtext: ${isDark ? '#94a3b8' : '#64748b'};
        --fr-border: ${isDark ? '#334155' : '#e2e8f0'};
        --fr-input-bg: ${isDark ? '#1e293b' : '#f8fafc'};
        --fr-accent: ${accentColor};
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        box-sizing: border-box;
      }
      #flyrank-widget-${config.id} * {
        box-sizing: border-box;
      }
      .flyrank-container.flyrank-inline {
        width: 100%;
        max-width: 440px;
        margin: 20px auto;
        padding: 24px;
        background: var(--fr-bg);
        border: 1px solid var(--fr-border);
        border-radius: 12px;
        box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
      }
      .flyrank-container.flyrank-popover {
        position: fixed;
        bottom: 24px;
        right: 24px;
        width: 360px;
        padding: 20px;
        background: var(--fr-bg);
        border: 1px solid var(--fr-border);
        border-radius: 12px;
        box-shadow: 0 20px 30px -10px rgba(0, 0, 0, 0.25);
        z-index: 999999;
      }
      .flyrank-header h3 {
        margin: 0 0 8px 0;
        font-size: 1.15rem;
        font-weight: 700;
        color: var(--fr-text);
      }
      .flyrank-header p {
        margin: 0 0 16px 0;
        font-size: 0.9rem;
        color: var(--fr-subtext);
        line-height: 1.4;
      }
      .flyrank-field {
        margin-bottom: 14px;
      }
      .flyrank-field label {
        display: block;
        margin-bottom: 6px;
        font-size: 0.82rem;
        font-weight: 600;
        color: var(--fr-text);
      }
      .flyrank-field input, .flyrank-field textarea {
        width: 100%;
        padding: 10px 12px;
        border: 1px solid var(--fr-border);
        border-radius: 6px;
        background: var(--fr-input-bg);
        color: var(--fr-text);
        font-size: 0.9rem;
        outline: none;
        transition: border-color 0.15s ease;
      }
      .flyrank-field input:focus, .flyrank-field textarea:focus {
        border-color: var(--fr-accent);
      }
      .flyrank-btn {
        width: 100%;
        padding: 11px 16px;
        background: var(--fr-accent);
        color: #ffffff;
        font-size: 0.92rem;
        font-weight: 600;
        border: none;
        border-radius: 6px;
        cursor: pointer;
        transition: opacity 0.15s ease;
      }
      .flyrank-btn:hover {
        opacity: 0.9;
      }
      .flyrank-btn:disabled {
        opacity: 0.6;
        cursor: not-allowed;
      }
      .flyrank-status {
        margin-top: 12px;
        font-size: 0.85rem;
        text-align: center;
        display: none;
      }
      .flyrank-status.success {
        display: block;
        color: #10b981;
        font-weight: 600;
      }
      .flyrank-status.error {
        display: block;
        color: #ef4444;
        font-weight: 600;
      }
      .flyrank-hp {
        display: none !important;
        position: absolute !important;
        left: -9999px !important;
      }
    `;

    document.head.appendChild(style);

    // Build fields HTML
    const fieldsHtml = (config.fields || [])
      .map((f) => {
        const requiredAttr = f.required ? 'required' : '';
        const placeholder = f.placeholder || '';
        const label = f.label || (f.name.charAt(0).toUpperCase() + f.name.slice(1));
        if (f.type === 'textarea') {
          return `
            <div class="flyrank-field">
              <label>${label}</label>
              <textarea name="${f.name}" placeholder="${placeholder}" rows="3" ${requiredAttr}></textarea>
            </div>
          `;
        }
        return `
          <div class="flyrank-field">
            <label>${label}</label>
            <input type="${f.type || 'text'}" name="${f.name}" placeholder="${placeholder}" ${requiredAttr} />
          </div>
        `;
      })
      .join('');

    container.innerHTML = `
      <div class="flyrank-header">
        <h3>${escapeHtml(config.title)}</h3>
        ${config.description ? `<p>${escapeHtml(config.description)}</p>` : ''}
      </div>
      <form class="flyrank-form">
        <!-- Honeypot anti-spam trap field -->
        <input type="text" name="website_url_hp" class="flyrank-hp" tabindex="-1" autocomplete="off" />
        ${fieldsHtml}
        <button type="submit" class="flyrank-btn">${escapeHtml(config.button_text || 'Submit')}</button>
        <div class="flyrank-status"></div>
      </form>
    `;

    // Insert container directly after script element or inside body
    if (currentScript.parentNode) {
      currentScript.parentNode.insertBefore(container, currentScript.nextSibling);
    } else {
      document.body.appendChild(container);
    }

    // Attach submit listener
    const form = container.querySelector('.flyrank-form');
    const statusDiv = container.querySelector('.flyrank-status');
    const submitBtn = container.querySelector('.flyrank-btn');

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      submitBtn.disabled = true;
      statusDiv.className = 'flyrank-status';
      statusDiv.textContent = 'Submitting...';
      statusDiv.style.display = 'block';

      const formData = new FormData(form);
      const payloadData = {};
      let honeypotVal = null;

      for (const [key, value] of formData.entries()) {
        if (key === 'website_url_hp') {
          honeypotVal = value;
        } else {
          payloadData[key] = value;
        }
      }

      const postBody = {
        widget_id: config.id,
        data: payloadData,
        website_url_hp: honeypotVal || null,
      };

      const submitEndpoint = `${apiBase}${config.submit_url || '/submissions'}`;

      fetch(submitEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        body: JSON.stringify(postBody),
      })
        .then(async (res) => {
          submitBtn.disabled = false;
          if (res.status === 201) {
            statusDiv.className = 'flyrank-status success';
            statusDiv.textContent = '✓ Response received! Thank you.';
            form.reset();
          } else if (res.status === 429) {
            statusDiv.className = 'flyrank-status error';
            statusDiv.textContent = 'Too many requests. Please wait a few seconds before trying again.';
          } else {
            const errJson = await res.json().catch(() => ({}));
            statusDiv.className = 'flyrank-status error';
            statusDiv.textContent = errJson.detail || 'Submission failed. Please try again.';
          }
        })
        .catch((err) => {
          submitBtn.disabled = false;
          statusDiv.className = 'flyrank-status error';
          statusDiv.textContent = 'Network error. Please check your connection.';
          console.error('[FlyRank Widget] Submission error:', err);
        });
    });
  }

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
})();
