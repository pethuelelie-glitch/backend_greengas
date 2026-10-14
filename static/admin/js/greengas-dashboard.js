/**
 * GREENGAS Dashboard — Micro-interactions & UX enhancements
 * (c) DEDSEC · Hackathon SIREXE 2026
 */
(function () {
  'use strict';

  // ── 1. Animated counter for KPI numbers ─────────────────────────────────
  function animateCounters() {
    const counters = document.querySelectorAll('.small-box h3, .info-box-number');
    counters.forEach(function (el) {
      const text = el.textContent.trim();
      const num = parseInt(text.replace(/[^\d]/g, ''), 10);
      if (isNaN(num) || num === 0) return;

      const suffix = text.replace(/[\d,.\s]/g, '');
      const duration = 800;
      const start = performance.now();

      el.textContent = '0' + suffix;
      function step(now) {
        const progress = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
        el.textContent = Math.floor(num * eased).toLocaleString('fr-FR') + suffix;
        if (progress < 1) requestAnimationFrame(step);
      }
      requestAnimationFrame(step);
    });
  }

  // ── 2. Smooth card entrance ─────────────────────────────────────────────
  function animateCards() {
    const cards = document.querySelectorAll('.card, .small-box, .info-box');
    cards.forEach(function (card, i) {
      card.style.opacity = '0';
      card.style.transform = 'translateY(12px)';
      setTimeout(function () {
        card.style.transition = 'opacity 0.4s ease, transform 0.4s ease';
        card.style.opacity = '1';
        card.style.transform = 'translateY(0)';
      }, 60 + i * 50);
    });
  }

  // ── 3. Quick search keyboard shortcut (Ctrl+K) ─────────────────────────
  function setupSearchShortcut() {
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        var searchInput = document.querySelector(
          '.form-control-navbar, #searchbar, input[name="q"]'
        );
        if (searchInput) {
          searchInput.focus();
          searchInput.select();
        }
      }
    });
  }

  // ── 4. Sidebar active indicator pulse ──────────────────────────────────
  function highlightActiveSidebar() {
    var active = document.querySelector('.sidebar .nav-link.active');
    if (active) {
      active.style.position = 'relative';
      var dot = document.createElement('span');
      dot.style.cssText =
        'position:absolute;right:12px;top:50%;transform:translateY(-50%);' +
        'width:6px;height:6px;background:#22c55e;border-radius:50%;' +
        'box-shadow:0 0 8px rgba(34,197,94,0.6);';
      active.appendChild(dot);
    }
  }

  // ── 5. Table row click-to-detail ────────────────────────────────────────
  function setupTableRowClick() {
    var rows = document.querySelectorAll('#result_list tbody tr');
    rows.forEach(function (row) {
      var link = row.querySelector('th a, td a');
      if (link) {
        row.style.cursor = 'pointer';
        row.addEventListener('click', function (e) {
          if (e.target.tagName === 'A' || e.target.tagName === 'INPUT') return;
          link.click();
        });
      }
    });
  }

  // ── 6. Tooltip on truncated cells ──────────────────────────────────────
  function setupTruncationTooltips() {
    var cells = document.querySelectorAll('#result_list td');
    cells.forEach(function (td) {
      if (td.scrollWidth > td.clientWidth) {
        td.title = td.textContent.trim();
        td.style.cursor = 'help';
      }
    });
  }

  // ── Boot ────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', function () {
    // Respect reduced-motion preference
    var prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    
    if (!prefersReducedMotion) {
      animateCounters();
      animateCards();
    }
    
    setupSearchShortcut();
    highlightActiveSidebar();
    setupTableRowClick();
    setupTruncationTooltips();
  });
})();
