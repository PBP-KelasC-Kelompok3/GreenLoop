document.addEventListener("DOMContentLoaded", function () {

    /* ================== ELEMEN & STATUS ================== */
    var filterForm = document.getElementById("recap-filter");
    var results = document.getElementById("recap-results");
    var weightDialog = document.getElementById("weight-dialog");
    var weightForm = document.getElementById("weight-form");
    var deleteDialog = document.getElementById("delete-dialog");
    var deleteForm = document.getElementById("delete-form");
    var toast = document.getElementById("toast");
    var chips = filterForm.querySelectorAll("[data-period]");

    var listUrl = results.dataset.listUrl;
    // Nomor halaman yang sedang dibuka (diambil dari URL kalau ada)
    var currentPage = parseInt(new URLSearchParams(window.location.search).get("page"), 10) || 1;
    var toastTimer = null;
    var searchTimer = null;
    // Nomor permintaan terakhir; jawaban dari permintaan yang lebih lama diabaikan
    var latestRequest = 0;

    /* ================== HELPER ================== */
    // Menampilkan notifikasi singkat di pojok layar selama 3,5 detik
    function showToast(text, type) {
        toast.textContent = text;
        toast.className = "toast is-visible" + (type === "error" ? " is-error" : "");

        clearTimeout(toastTimer);
        toastTimer = setTimeout(function () {
            toast.classList.remove("is-visible");
        }, 3500);
    }

    // Menggambar ulang ikon pada isi yang baru dimuat
    function refreshIcons() {
        if (window.lucide) lucide.createIcons();
    }

    // Membaca jawaban JSON; sesi habis -> Django mengarahkan ke login (response.redirected)
    function readJson(response) {
        if (response.redirected) {
            window.location.href = response.url;
            return null;
        }
        return response.json();
    }

    /* ================== MUAT ULANG TABEL (AJAX) ================== */
    function queryString(page) {
        var params = new URLSearchParams(new FormData(filterForm));

        Array.from(params.keys()).forEach(function (key) {
            if (!params.get(key)) params.delete(key);
        });
        if (page > 1) params.set("page", page);

        return params.toString();
    }

    // Mengambil tabel dan ringkasan sesuai filter lalu menggantinya tanpa reload halaman
    function load(page) {
        currentPage = page || 1;
        var qs = queryString(currentPage);
        var requestId = ++latestRequest;

        results.classList.add("is-loading");

        return fetch(listUrl + (qs ? "?" + qs : ""), {
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" }
        })
            .then(readJson)
            .then(function (payload) {
                // Mengabaikan jawaban lama yang tiba terlambat setelah ada permintaan yang lebih baru
                if (!payload || requestId !== latestRequest) return;
                results.innerHTML = payload.html;
                refreshIcons();
                // Memperbarui alamat di browser agar filter tetap ada saat halaman di-refresh
                history.replaceState(null, "", window.location.pathname + (qs ? "?" + qs : ""));
            })
            .catch(function () {
                if (requestId === latestRequest) showToast("Gagal memuat data. Coba lagi.", "error");
            })
            .finally(function () {
                if (requestId === latestRequest) results.classList.remove("is-loading");
            });
    }

    /* ================== FILTER ================== */
    // Mengganti periode terpilih dan menandai tombolnya
    function setPeriod(period) {
        filterForm.elements.period.value = period;
        chips.forEach(function (chip) {
            chip.classList.toggle("is-active", chip.dataset.period === period);
        });
    }

    // Klik tombol periode: pilih periode, kosongkan tanggal, muat ulang
    chips.forEach(function (chip) {
        chip.addEventListener("click", function () {
            setPeriod(chip.dataset.period);
            filterForm.elements.start.value = "";
            filterForm.elements.end.value = "";
            load(1);
        });
    });

    // Mengisi tanggal otomatis beralih ke rentang kustom; mengosongkannya kembali ke 'bulan ini'
    ["start", "end"].forEach(function (name) {
        filterForm.elements[name].addEventListener("change", function () {
            var hasDate = filterForm.elements.start.value || filterForm.elements.end.value;
            setPeriod(hasDate ? "custom" : "month");
            load(1);
        });
    });

    // Pencarian mitra: menunggu 350 ms setelah berhenti mengetik agar tidak memuat di setiap huruf
    filterForm.elements.q.addEventListener("input", function () {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(function () { load(1); }, 350);
    });

    // Menekan Enter di kolom cari tidak me-reload halaman
    filterForm.addEventListener("submit", function (event) {
        event.preventDefault();
        load(1);
    });

    /* ================== KLIK DI DALAM TABEL ================== */
    results.addEventListener("click", function (event) {
        // Tombol nomor halaman
        var pageBtn = event.target.closest("[data-page]");
        if (pageBtn) {
            if (!pageBtn.disabled) load(parseInt(pageBtn.dataset.page, 10));
            return;
        }

        // Tombol ubah (ikon pensil)
        var editBtn = event.target.closest('[data-action="edit"]');
        if (editBtn) {
            openWeightForm(editBtn);
            return;
        }

        // Tombol hapus (ikon tempat sampah)
        var deleteBtn = event.target.closest('[data-action="delete"]');
        if (deleteBtn) openDeleteDialog(deleteBtn);
    });

    // Tombol "Tambah Timbangan" membuka form kosong
    document.querySelector('[data-action="add"]').addEventListener("click", function () {
        openWeightForm(null);
    });

    /* ================== DIALOG ================== */
    document.querySelectorAll("dialog").forEach(function (dialog) {
        // Klik area gelap di luar kotak dialog = tutup
        dialog.addEventListener("click", function (event) {
            if (event.target === dialog) dialog.close();
        });
        // Tombol Batal dan X menutup dialog
        dialog.querySelectorAll("[data-dialog-close]").forEach(function (btn) {
            btn.addEventListener("click", function () { dialog.close(); });
        });
    });

    // Membersihkan pesan dan tanda merah dari pengiriman sebelumnya
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

    // Menampilkan pesan kesalahan umum di atas form
    function showFormMessage(form, text) {
        var box = form.querySelector("[data-form-message]");
        if (!box) return;
        box.className = "form-message is-error";
        box.textContent = text;
        box.hidden = false;
    }

    // Menampilkan pesan kesalahan di bawah isian yang bermasalah
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

        if (general.length) showFormMessage(form, general.join(" "));
    }

    /* ================== TAMBAH / UBAH ================== */
    // Membuka dialog: dengan tombol ubah = form terisi data lama, tanpa tombol = form kosong
    function openWeightForm(button) {
        var title = document.getElementById("weight-dialog-title");
        clearFeedback(weightForm);
        weightForm.reset();

        if (button) {
            // Mode ubah: isi form dari atribut data-* pada tombol, kirim ke alamat update
            title.textContent = "Ubah Timbangan";
            weightForm.action = button.dataset.updateUrl;
            weightForm.elements.partner_name.value = button.dataset.partner;
            weightForm.elements.collected_at.value = button.dataset.date;
            weightForm.elements.weight_kg.value = button.dataset.weight.replace(".", ",");
            weightForm.elements.notes.value = button.dataset.notes;
        } else {
            // Mode tambah: tanggal otomatis hari ini, kirim ke alamat create
            title.textContent = "Tambah Timbangan";
            weightForm.action = weightForm.dataset.createUrl;
            weightForm.elements.collected_at.value = weightForm.dataset.today;
        }

        weightDialog.showModal();
        weightForm.elements.partner_name.focus();
    }

    // Mengirim form tambah/ubah lewat AJAX
    weightForm.addEventListener("submit", function (event) {
        event.preventDefault();
        clearFeedback(weightForm);

        // Menonaktifkan tombol selama proses agar tidak terkirim dua kali
        var submitBtn = weightForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;

        fetch(weightForm.action, {
            method: "POST",
            body: new FormData(weightForm),
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" }
        })
            .then(readJson)
            .then(function (payload) {
                if (!payload) return;

                if (payload.ok) {
                    // Berhasil: tutup dialog, beri notifikasi, segarkan tabel di halaman yang sama
                    weightDialog.close();
                    showToast(payload.message);
                    load(currentPage);
                } else {
                    showErrors(weightForm, payload.errors || {});
                }
            })
            .catch(function () {
                showFormMessage(weightForm, "Terjadi gangguan. Periksa koneksi lalu coba lagi.");
            })
            .finally(function () {
                submitBtn.disabled = false;
            });
    });

    /* ================== HAPUS ================== */
    // Membuka dialog konfirmasi dengan ringkasan data yang akan dihapus
    function openDeleteDialog(button) {
        clearFeedback(deleteForm);
        deleteForm.action = button.dataset.deleteUrl;
        document.getElementById("delete-summary").textContent = button.dataset.summary;
        deleteDialog.showModal();
    }

    // Mengirim permintaan hapus lewat AJAX
    deleteForm.addEventListener("submit", function (event) {
        event.preventDefault();
        clearFeedback(deleteForm);

        var submitBtn = deleteForm.querySelector('button[type="submit"]');
        submitBtn.disabled = true;

        fetch(deleteForm.action, {
            method: "POST",
            body: new FormData(deleteForm),
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" }
        })
            .then(readJson)
            .then(function (payload) {
                if (!payload) return;

                if (payload.ok) {
                    deleteDialog.close();
                    showToast(payload.message);
                    load(currentPage);
                } else {
                    showFormMessage(deleteForm, "Data tidak bisa dihapus.");
                }
            })
            .catch(function () {
                showFormMessage(deleteForm, "Terjadi gangguan. Periksa koneksi lalu coba lagi.");
            })
            .finally(function () {
                submitBtn.disabled = false;
            });
    });
});