document.addEventListener("DOMContentLoaded", function () {
    if (window.lucide) {
        lucide.createIcons();
    }

    var layout = document.getElementById("layout");
    var toggle = document.getElementById("menuToggle");
    var backdrop = document.getElementById("backdrop");

    function closeMenu() { layout.classList.remove("menu-open"); }

    toggle.addEventListener("click", function () {
        layout.classList.toggle("menu-open");
    });
    backdrop.addEventListener("click", closeMenu);
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") closeMenu();
    });
});