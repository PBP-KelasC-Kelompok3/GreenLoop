document.addEventListener("DOMContentLoaded", function () {

    /* ===== Akordeon (panah berputar ketika membuka/menutup panel) ===== */
    document.querySelectorAll("[data-accordion-toggle]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            var panel = document.getElementById(btn.getAttribute("aria-controls"));
            var isOpen = btn.getAttribute("aria-expanded") === "true";

            btn.setAttribute("aria-expanded", String(!isOpen));
            panel.hidden = isOpen;
        });
    });

    /* ===== Helper tampilan ===== */
    function showMessage(form, text, type) {
        var box = form.querySelector("[data-form-message]");
        if (!box) return;

        box.className = "form-message " + (type === "ok" ? "is-ok" : "is-error");
        box.textContent = text;
        box.hidden = false;
    }

    function clearFeedback(form) {
        var box = form.querySelector("[data-form-message]");
        if (box) box.hidden = true;

        form.querySelectorAll("[data-error-for]").forEach(function (el) {
            el.textContent = "";
            el.hidden = true;
        });
        form.querySelectorAll(".is-invalid").forEach(function (el) {
            el.classList.remove("is-invalid");
            el.removeAttribute("aria-invalid");
        });
    }

    function showErrors(form, errors) {
        var general = [];

        Object.keys(errors).forEach(function (field) {
            var text = errors[field].join(" ");
            var slot = form.querySelector('[data-error-for="' + field + '"]');
            var input = form.querySelector('[name="' + field + '"]');

            if (slot) {
                slot.textContent = text;
                slot.hidden = false;
                if (input) {
                    input.classList.add("is-invalid");
                    input.setAttribute("aria-invalid", "true");
                }
            } else {
                general.push(text);
            }
        });

        showMessage(
            form,
            general.length ? general.join(" ") : "Periksa kembali isian yang bertanda merah.",
            "error"
        );
    }

    // Isi ulang teks di halaman (nama, plat, dll.) setelah profil berubah
    function applyBindings(data) {
        Object.keys(data).forEach(function (key) {
            document.querySelectorAll('[data-bind="' + key + '"]').forEach(function (el) {
                el.textContent = data[key];
            });
        });
    }

    /* ===== Kirim form lewat AJAX ===== */
    document.querySelectorAll("form[data-ajax-form]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            event.preventDefault();
            clearFeedback(form);

            var submitBtn = form.querySelector('button[type="submit"]');
            submitBtn.disabled = true;

            fetch(form.action, {
                method: "POST",
                body: new FormData(form),
                credentials: "same-origin",
                headers: { "X-Requested-With": "XMLHttpRequest" }
            })
                .then(function (response) {
                    // Sesi habis -> Django mengarahkan ke halaman login
                    if (response.redirected) {
                        window.location.href = response.url;
                        return null;
                    }
                    return response.json().then(function (payload) {
                        return { status: response.status, payload: payload };
                    });
                })
                .then(function (result) {
                    if (!result) return;

                    if (result.payload.ok) {
                        showMessage(form, result.payload.message, "ok");
                        if (result.payload.data) applyBindings(result.payload.data);
                        if (form.hasAttribute("data-reset-on-success")) form.reset();
                    } else {
                        showErrors(form, result.payload.errors || {});
                    }
                })
                .catch(function () {
                    showMessage(form, "Terjadi gangguan. Periksa koneksi lalu coba lagi.", "error");
                })
                .finally(function () {
                    submitBtn.disabled = false;
                });
        });
    });
});