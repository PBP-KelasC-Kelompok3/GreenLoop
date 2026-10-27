(function () {
    const body = document.body;
    const currentPage = body.dataset.page;
    const transitionKey = 'greenloop-transition-from';

    try {
        const previousPage = sessionStorage.getItem(transitionKey);
        sessionStorage.removeItem(transitionKey);

        if (currentPage === 'mitra-dashboard' && previousPage === 'home') {
            body.classList.add('page-transition-in-from-home');
        } else if (currentPage === 'home' && previousPage === 'mitra-dashboard') {
            body.classList.add('page-transition-in-from-dashboard');
        }

        window.setTimeout(function () {
            body.classList.remove(
                'page-transition-in-from-home',
                'page-transition-in-from-dashboard'
            );
        }, 500);
    } catch (error) {
        // Navigation still works if session storage is unavailable.
    }

    document.addEventListener('click', function (event) {
        const link = event.target.closest('a[data-transition-target]');
        if (!link || event.defaultPrevented || event.button !== 0) return;
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        if (link.target && link.target !== '_self') return;

        const targetPage = link.dataset.transitionTarget;
        const isHomeDashboardTransition =
            (currentPage === 'home' && targetPage === 'mitra-dashboard') ||
            (currentPage === 'mitra-dashboard' && targetPage === 'home');
        if (!isHomeDashboardTransition) return;

        event.preventDefault();
        try {
            sessionStorage.setItem(transitionKey, currentPage);
        } catch (error) {
            // The link remains navigable without the entrance animation.
        }

        const exitClass = targetPage === 'home'
            ? 'page-transition-out-to-home'
            : 'page-transition-out-to-dashboard';
        body.classList.add(exitClass);
        window.setTimeout(function () {
            window.location.assign(link.href);
        }, 170);
    });

    const nav = document.querySelector('.nav-links');
    if (!nav) return;

    const navItems = Array.from(nav.querySelectorAll('a[data-nav-section]'));
    const indicator = nav.querySelector('.nav-indicator');

    function setActiveSection(section) {
        let activeItem = null;
        navItems.forEach(function (item) {
            const isActive = item.dataset.navSection === section;
            item.classList.toggle('nav-current', isActive);
            if (isActive) {
                item.setAttribute('aria-current', 'page');
                activeItem = item;
            } else {
                item.removeAttribute('aria-current');
            }
        });

        if (!indicator || !activeItem || window.matchMedia('(max-width: 900px)').matches) {
            if (indicator) indicator.style.width = '0px';
            return;
        }

        const navRect = nav.getBoundingClientRect();
        const itemRect = activeItem.getBoundingClientRect();
        indicator.style.width = itemRect.width + 'px';
        indicator.style.transform = 'translateX(' + (itemRect.left - navRect.left) + 'px)';
    }

    if (currentPage === 'home') {
        const validSections = ['impact', 'cara-kerja'];
        const syncFromHash = function () {
            const section = window.location.hash.slice(1);
            setActiveSection(validSections.includes(section) ? section : 'home');
        };

        syncFromHash();
        window.addEventListener('hashchange', syncFromHash);
        window.addEventListener('resize', function () {
            const active = nav.querySelector('a.nav-current');
            if (active) setActiveSection(active.dataset.navSection);
        });

        navItems.forEach(function (item) {
            item.addEventListener('click', function () {
                if (item.dataset.navSection !== 'mitra-dashboard') {
                    setActiveSection(item.dataset.navSection);
                }
            });
        });

        const observedSections = validSections
            .map(function (id) { return document.getElementById(id); })
            .filter(Boolean);

        if ('IntersectionObserver' in window && observedSections.length) {
            const observer = new IntersectionObserver(function (entries) {
                const visible = entries
                    .filter(function (entry) { return entry.isIntersecting; })
                    .sort(function (a, b) { return a.boundingClientRect.top - b.boundingClientRect.top; });
                if (visible.length) setActiveSection(visible[0].target.id);
            }, { rootMargin: '-18% 0px -68% 0px', threshold: 0 });

            observedSections.forEach(function (section) { observer.observe(section); });
        }

        window.addEventListener('scroll', function () {
            if (window.scrollY < 80 && !window.location.hash) setActiveSection('home');
        }, { passive: true });
    }
})();
