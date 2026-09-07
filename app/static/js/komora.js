document.addEventListener('DOMContentLoaded', function () {

  /* ---------- toast (driven by a PHP flash message rendered into body[data-flash]) ---------- */
  var toast = document.getElementById('vToast');
  var toastMsg = document.getElementById('vToastMsg');
  var flash = document.body.getAttribute('data-flash');
  if (toast && flash) {
    toastMsg.textContent = flash;
    toast.classList.add('show');
    setTimeout(function () { toast.classList.remove('show'); }, 2600);
  }
  window.showVoltToast = function (msg) {
    if (!toast) return;
    toastMsg.textContent = msg;
    toast.classList.add('show');
    clearTimeout(window._komoraToastTimer);
    window._komoraToastTimer = setTimeout(function () { toast.classList.remove('show'); }, 2200);
  };

  /* ---------- wishlist ----------
     Server-driven now (DB-backed, tied to the account) — the heart buttons
     are plain links to wishlist.php?add_to_wishlist=/remove_from_wishlist=,
     rendered with the correct state by PHP. Nothing to do here anymore. */

  /* ---------- bag icon ----------
     Plain link now (gates on login, shows cart.php) — no dropdown JS needed. */

  /* ---------- profile dropdown ---------- */
  var profileToggle = document.getElementById('vProfileToggle');
  var profileMenu = document.getElementById('vProfileMenu');
  if (profileToggle && profileMenu) {
    profileToggle.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      profileMenu.classList.toggle('open');
    });
    document.addEventListener('click', function (e) {
      if (!profileMenu.contains(e.target) && e.target !== profileToggle) {
        profileMenu.classList.remove('open');
      }
    });
  }

  /* ---------- search bar toggle ---------- */
  var searchToggle = document.getElementById('vSearchToggle');
  var searchBar = document.getElementById('vSearchBar');
  if (searchToggle && searchBar) {
    searchToggle.addEventListener('click', function () {
      searchBar.classList.toggle('open');
      if (searchBar.classList.contains('open')) {
        var input = searchBar.querySelector('input');
        if (input) input.focus();
      }
    });
  }

  /* ---------- mobile category menu ---------- */
  var menuToggle = document.getElementById('vMenuToggle');
  var catsList = document.getElementById('vCatsList');
  if (menuToggle && catsList) {
    menuToggle.addEventListener('click', function () {
      catsList.style.display = catsList.style.display === 'flex' ? 'none' : 'flex';
    });
  }

  /* ---------- cart page quantity steppers ---------- */
  document.querySelectorAll('.v-qty-stepper').forEach(function (group) {
    var input = group.querySelector('input[type="number"]');
    var minus = group.querySelector('[data-step="-1"]');
    var plus = group.querySelector('[data-step="1"]');
    if (!input) return;
    function clamp(v) { return Math.max(1, v); }
    if (minus) minus.addEventListener('click', function () {
      input.value = clamp((parseInt(input.value, 10) || 1) - 1);
    });
    if (plus) plus.addEventListener('click', function () {
      input.value = clamp((parseInt(input.value, 10) || 1) + 1);
    });
  });

  /* ---------- drop countdown (decorative, resets each visit) ---------- */
  var cdH = document.getElementById('vCdH'), cdM = document.getElementById('vCdM'), cdS = document.getElementById('vCdS');
  if (cdH && cdM && cdS) {
    var total = 18 * 3600 + 42 * 60 + 9;
    setInterval(function () {
      if (total <= 0) return;
      total--;
      var h = Math.floor(total / 3600), m = Math.floor((total % 3600) / 60), s = total % 60;
      cdH.textContent = String(h).padStart(2, '0');
      cdM.textContent = String(m).padStart(2, '0');
      cdS.textContent = String(s).padStart(2, '0');
    }, 1000);
  }
});
