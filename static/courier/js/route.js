// Halaman Rute Hari Ini: peta (Leaflet + OpenStreetMap), daftar titik, kartu detail,
// tombol Mulai Perjalanan / Selesai Pikap, dan saklar Sedang Bertugas.
// Rute jalan, jarak, dan petunjuk belok dihitung server (OSRM); di sini hanya digambar.
(function () {
    "use strict";

    var dataEl = document.getElementById("route-data");
    if (!dataEl) return;

    var plan = JSON.parse(dataEl.textContent);   // data awal; diganti jawaban server setelah aksi
    var selectedId = plan.targetId;               // titik yang sedang dilihat di kartu detail
    var stepIndex = 1;                            // langkah petunjuk yang tampil di kartu hijau (0 = mulai jalan)
    var userPos = null;                           // posisi kurir dari GPS peramban
    var geoNote = "";                             // pesan bila lokasi belum bisa dipakai
    var busy = false;                             // mencegah klik ganda saat menunggu server

    var els = {
        list: document.getElementById("route-list"),
        detail: document.getElementById("route-detail"),
        summary: document.getElementById("route-summary"),
        turn: document.getElementById("route-turn"),
        top: document.querySelector(".route-top"),
        dirs: document.getElementById("route-directions"),
        dirsTitle: document.getElementById("route-dir-title"),
        mapMsg: document.getElementById("route-map-msg"),
        toast: document.getElementById("route-toast"),
        dutyToggle: document.getElementById("duty-toggle"),
        dutyLabel: document.getElementById("duty-label")
    };

    /* ===== Fungsi kecil ===== */

    // Membuat elemen: el("div", "kelas", "teks") atau el("div", {class: "...", ...}, [anak])
    function el(tag, attrs, children) {
        var node = document.createElement(tag);
        if (typeof attrs === "string") attrs = { class: attrs };
        Object.keys(attrs || {}).forEach(function (key) {
            if (key === "text") node.textContent = attrs[key];
            else node.setAttribute(key, attrs[key]);
        });
        (children || []).forEach(function (child) {
            if (child) node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
        });
        return node;
    }

    function icon(name) {
        return el("i", { "data-lucide": name });
    }

    function refreshIcons() {
        if (window.lucide) window.lucide.createIcons();
    }

    function csrfToken() {
        var input = document.querySelector("[name=csrfmiddlewaretoken]");
        return input ? input.value : "";
    }

    function formatKg(tenths) {
        // 586 -> "58,6"
        return (tenths / 10).toFixed(1).replace(".", ",");
    }

    // Waste Points: berat x tarif, dibulatkan (setengah ke atas) seperti points_for di server
    function pointsFor(tenths) {
        return Math.floor((tenths * plan.pointsPerKg + 5) / 10);
    }

    // "58,6" / "58.6" -> 586 (persepuluhan); null bila bukan angka dengan maksimal satu desimal
    function parseTenths(text) {
        var clean = (text || "").trim();
        if (!/^\d{1,4}([.,]\d)?$/.test(clean)) return null;
        return Math.round(parseFloat(clean.replace(",", ".")) * 10);
    }

    function stopById(id) {
        return plan.stops.filter(function (s) { return s.id === id; })[0] || null;
    }

    // Menambahkan posisi kurir (bila diketahui) ke permintaan, supaya rute dihitung dari sana
    function withPos(body) {
        if (userPos) {
            body.append("lat", userPos.lat);
            body.append("lng", userPos.lng);
        }
        return body;
    }

    function showToast(message, isError) {
        els.toast.textContent = message;
        els.toast.className = "route-toast" + (isError ? " is-error" : "");
        els.toast.hidden = false;
        clearTimeout(showToast.timer);
        showToast.timer = setTimeout(function () { els.toast.hidden = true; }, 4000);
    }

    /* ===== Daftar titik ===== */

    function renderList() {
        els.list.innerHTML = "";
        if (!plan.stops.length) {
            els.list.appendChild(el("li", "route-empty", ["Belum ada titik jemput. Jalankan: python manage.py seed_points"]));
        }
        plan.stops.forEach(function (s) {
            var badge = el("span", "route-badge");
            if (s.status === "done") badge.appendChild(icon("check"));
            else badge.textContent = s.order;

            var item = el("button", {
                type: "button",
                class: "route-item is-" + s.status + (s.id === selectedId ? " is-selected" : ""),
                "data-stop": s.id,
                "aria-current": s.id === selectedId ? "true" : "false"
            }, [
                badge,
                el("span", "route-item-text", [
                    el("strong", { text: s.name }),
                    el("small", { text: s.slot + " · " + (s.actualKg ? s.actualKg : "est. " + s.estKg) + " kg" })
                ]),
                el("span", { class: "route-pill route-pill--" + s.status, text: s.statusLabel })
            ]);
            item.addEventListener("click", function () { selectStop(s.id); });
            els.list.appendChild(el("li", "", [item]));
        });
    }

    function selectStop(id) {
        selectedId = id;
        renderList();
        renderDetail();
        drawMap(false);
        var s = stopById(id);
        if (map && s) map.panTo([s.lat, s.lng]);
        refreshIcons();
    }

    /* ===== Kartu detail titik ===== */

    function renderDetail() {
        var s = stopById(selectedId) || plan.stops[plan.stops.length - 1];
        els.detail.innerHTML = "";
        if (!s) return;

        var fact = function (label, value) {
            return el("div", "route-fact", [el("span", { text: label }), el("strong", { text: value })]);
        };

        els.detail.appendChild(el("span", { class: "route-step-pill", text: "Titik " + s.order + " dari " + plan.total }));
        els.detail.appendChild(el("h2", { class: "route-detail-name", text: s.name }));
        els.detail.appendChild(el("p", { class: "route-detail-address", text: s.address }));
        els.detail.appendChild(el("div", "route-facts", [
            fact("Slot", s.slot),
            fact("Estimasi", s.estKg + " kg"),
            fact("Armada", s.vehicle)
        ]));
        els.detail.appendChild(el("div", "route-photo", [
            el("span", "route-photo-thumb"),
            el("span", "", [
                el("strong", { text: "Foto terverifikasi admin" }),
                el("small", { text: s.photoNote })
            ])
        ]));

        if (s.status === "done") {
            els.detail.appendChild(el("p", "route-done-note", [
                icon("circle-check"),
                el("span", { text: "Selesai: " + s.actualKg + " kg · +" + s.points + " Waste Points" })
            ]));
            return;
        }

        var input = el("input", {
            id: "route-weight", class: "field-input", name: "weight_kg", type: "text", inputmode: "decimal",
            autocomplete: "off", placeholder: "mis. " + formatKg(s.estKg * 10), "aria-describedby": "route-points route-weight-error"
        });
        var points = el("p", { id: "route-points", class: "route-points", text: "Isi berat untuk melihat Waste Points." });
        var error = el("p", { id: "route-weight-error", class: "field-error", hidden: "" });
        var startBtn = el("button", { type: "button", class: "route-btn-outline", id: "route-start" }, [icon("navigation"), "Mulai Perjalanan"]);
        var finishBtn = el("button", { type: "button", class: "btn-submit", id: "route-finish" }, [icon("check"), "Selesai Pikap"]);

        if (s.status === "active") startBtn.disabled = true;

        els.detail.appendChild(el("label", { class: "field-label", for: "route-weight", text: "Berat bersih aktual (kg)" }));
        els.detail.appendChild(el("div", "route-weight", [input, el("span", { class: "route-unit", text: "kg" })]));
        els.detail.appendChild(points);
        els.detail.appendChild(error);
        els.detail.appendChild(el("div", "route-actions", [startBtn, finishBtn]));

        input.addEventListener("input", function () {
            input.classList.remove("is-invalid");
            input.removeAttribute("aria-invalid");
            error.hidden = true;
            var tenths = parseTenths(input.value);
            points.textContent = tenths && tenths > 0
                ? "= " + pointsFor(tenths) + " Waste Points untuk mitra (" + formatKg(tenths) + " × " + plan.pointsPerKg + ")"
                : "Isi berat untuk melihat Waste Points.";
        });

        startBtn.addEventListener("click", function () { startPickup(s); });
        finishBtn.addEventListener("click", function () { finishPickup(s, input, error); });
    }

    /* ===== Aksi ke server ===== */

    function post(url, body) {
        return fetch(url, {
            method: "POST",
            body: body,
            credentials: "same-origin",
            headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" }
        }).then(function (response) {
            if (response.redirected) { window.location.href = response.url; return null; }   // sesi habis
            return response.json().then(function (payload) { return { status: response.status, payload: payload }; });
        });
    }

    function applyPlan(newPlan, keepSelected, fit) {
        if (newPlan.targetId !== plan.targetId) stepIndex = 1;   // tujuan baru: petunjuk dari belokan pertama
        var followTarget = selectedId === plan.targetId;          // kartu detail mengikuti tujuan, kecuali kurir memilih titik lain
        plan = newPlan;
        if (!keepSelected || followTarget || !stopById(selectedId)) selectedId = plan.targetId || (plan.stops[plan.stops.length - 1] || {}).id;
        renderAll(fit !== false);
    }

    function run(url, body, onOk, onFail) {
        if (busy) return;
        busy = true;
        document.querySelectorAll(".route-actions button").forEach(function (b) { b.disabled = true; });
        post(url, body)
            .then(function (result) {
                if (!result) return;
                if (result.payload.ok) onOk(result.payload);
                else onFail(result.payload.errors || {});
            })
            .catch(function () { showToast("Terjadi gangguan. Periksa koneksi lalu coba lagi.", true); })
            .finally(function () { busy = false; renderDetail(); refreshIcons(); });
    }

    function startPickup(s) {
        run(plan.startUrl.replace("{id}", s.id), withPos(new FormData()), function (payload) {
            applyPlan(payload.plan, true);
            showToast(payload.message, false);
        }, function (errors) {
            showToast((errors.__all__ || ["Gagal memulai perjalanan."]).join(" "), true);
        });
    }

    function finishPickup(s, input, errorEl) {
        var tenths = parseTenths(input.value);
        if (!tenths || tenths < 1) {
            showFieldError(input, errorEl, "Masukkan berat dalam kg dengan maksimal satu angka desimal, contoh 58,6.");
            return;
        }
        var body = withPos(new FormData());
        body.append("weight_kg", input.value.trim());

        run(plan.finishUrl.replace("{id}", s.id), body, function (payload) {
            applyPlan(payload.plan, false);       // otomatis pindah ke titik berikutnya
            showToast(payload.message, false);
        }, function (errors) {
            var text = (errors.weight_kg || errors.__all__ || ["Gagal menyimpan."]).join(" ");
            showFieldError(document.getElementById("route-weight") || input, document.getElementById("route-weight-error") || errorEl, text);
        });
    }

    function showFieldError(input, errorEl, text) {
        input.classList.add("is-invalid");
        input.setAttribute("aria-invalid", "true");
        errorEl.textContent = text;
        errorEl.hidden = false;
        input.focus();
    }

    /* ===== Kartu di atas peta ===== */

    function renderOverlays() {
        // Ringkasan rute (kiri atas)
        els.summary.innerHTML = "";
        var r = plan.route;
        els.summary.hidden = !r;
        if (r) {
            var chips = r.chips.map(function (c) {
                return el("span", { class: "route-chip route-chip--" + c.tone, text: c.text });
            });
            var w = plan.weather;
            if (w) {
                chips.push(el("span", { class: "route-chip route-chip--" + (w.rain ? "amber" : "gray"),
                                        title: w.rain ? "Sedang hujan, berkendara hati-hati" : "Cuaca Depok (Open-Meteo)" },
                    [icon(w.icon), w.temperature + "° " + w.text]));
            }
            els.summary.appendChild(el("span", { class: "route-summary-label", text: r.label }));
            els.summary.appendChild(el("strong", { text: r.summary }));
            els.summary.appendChild(el("span", "route-chips", chips));
        }

        // Petunjuk belok (kiri bawah): bisa dibuka belokan demi belokan dengan tombol panah
        els.turn.innerHTML = "";
        var steps = plan.directions || [];
        var n = plan.navigation;
        els.turn.hidden = !(steps.length || n || plan.targetId || (r && !plan.targetId));

        if (steps.length >= 2) {
            // Langkah k: jarak sampai belokan itu (dari langkah sebelumnya) + kalimat belokannya
            var k = Math.min(Math.max(stepIndex, 1), steps.length - 1);
            var cur = steps[k];
            var prevBtn = el("button", { type: "button", class: "route-turn-btn", "aria-label": "Belokan sebelumnya" }, [icon("chevron-left")]);
            var nextBtn = el("button", { type: "button", class: "route-turn-btn", "aria-label": "Belokan berikutnya" }, [icon("chevron-right")]);
            prevBtn.disabled = k <= 1;
            nextBtn.disabled = k >= steps.length - 1;
            prevBtn.addEventListener("click", function () { setStep(k - 1); });
            nextBtn.addEventListener("click", function () { setStep(k + 1); });

            els.turn.appendChild(el("span", "route-turn-icon", [icon(cur.icon)]));
            els.turn.appendChild(el("span", "route-turn-text", [
                el("strong", { text: steps[k - 1].distance || "Segera" }),
                el("small", { text: cur.text }),
                el("small", { class: "route-turn-count", text: "Langkah " + k + " dari " + (steps.length - 1) })
            ]));
            els.turn.appendChild(el("span", "route-turn-nav", [prevBtn, nextBtn]));
        } else if (n) {
            els.turn.appendChild(el("span", "route-turn-icon", [icon("navigation")]));
            els.turn.appendChild(el("span", "", [
                el("strong", { text: n.distance_text }),
                el("small", { text: n.instruction })
            ]));
        } else if (plan.targetId) {
            // Belum ada petunjuk belok (lokasi belum aktif atau layanan rute mati): kartu tetap menunjukkan tujuan
            var tname = plan.targetName || "titik berikutnya";
            els.turn.appendChild(el("span", "route-turn-icon", [icon("navigation")]));
            els.turn.appendChild(el("span", "route-turn-text", [
                el("strong", { text: "Menuju " + tname }),
                el("small", { text: plan.origin
                    ? "Petunjuk belok belum tersedia untuk rute ini."
                    : "Aktifkan lokasi untuk petunjuk belok dari posisimu." })
            ]));
        } else if (r && !plan.targetId) {
            els.turn.appendChild(el("span", "route-turn-icon", [icon("circle-check")]));
            els.turn.appendChild(el("span", "", [el("strong", { text: "Semua titik selesai" }), el("small", { text: "Kerja bagus hari ini!" })]));
        }

        // Pesan bila layanan peta bermasalah
        var message = [
            !window.L ? "Peta tidak dapat dimuat. Periksa koneksi internet." : "",
            plan.notice,
            plan.locationNote || geoNote
        ].filter(Boolean).join(" ");
        els.mapMsg.textContent = message;
        els.mapMsg.hidden = !message;
    }

    /* ===== Daftar petunjuk arah (di bawah peta) ===== */

    // Pindah ke belokan tertentu: kartu hijau di peta dan sorotan di daftar ikut berubah
    function setStep(k) {
        stepIndex = k;
        renderOverlays();
        renderDirections();
        refreshIcons();
    }

    function renderDirections() {
        els.dirs.innerHTML = "";
        els.dirsTitle.textContent = plan.targetName ? "Petunjuk Arah ke " + plan.targetName : "Petunjuk Arah";
        var steps = plan.directions || [];

        if (!steps.length) {
            var note = !plan.targetId
                ? "Semua titik sudah selesai."
                : "Petunjuk belok muncul setelah lokasimu aktif dan layanan rute (OSRM) tersedia.";
            els.dirs.appendChild(el("li", "route-steps-empty", [note]));
            return;
        }

        var current = Math.min(Math.max(stepIndex, 1), steps.length - 1);
        steps.forEach(function (d, i) {
            var item = el("button", {
                type: "button",
                class: "route-step" + (i === current ? " is-current" : ""),
                "aria-current": i === current ? "step" : "false"
            }, [
                el("span", "route-step-icon", [icon(d.icon)]),
                el("span", "route-step-text", [
                    el("strong", { text: d.text }),
                    d.distance ? el("small", { text: d.distance }) : null
                ])
            ]);
            item.addEventListener("click", function () { setStep(Math.max(i, 1)); });
            els.dirs.appendChild(el("li", "", [item]));
        });
    }

    /* ===== Peta (Leaflet) ===== */

    var map = null, layer = null;

    function initMap() {
        if (!window.L) return;
        // Peta dikunci ke wilayah Kota Depok (area pilot): tidak bisa digeser atau di-zoom keluar dari sana
        var b = plan.bounds;
        var depok = [[b.south, b.west], [b.north, b.east]];
        map = L.map("route-map", {
            zoomControl: false,
            maxBounds: depok,
            maxBoundsViscosity: 1.0,
            minZoom: 10
        }).setView([(b.south + b.north) / 2, (b.west + b.east) / 2], 12);
        L.control.zoom({ position: "bottomright" }).addTo(map);
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            // OpenStreetMap menolak tile bila tidak ada Referer (kebijakan bawaan Django: same-origin)
            referrerPolicy: "strict-origin-when-cross-origin",
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        }).addTo(map);
        layer = L.layerGroup().addTo(map);

        // Hitung ulang ukuran peta bila kotaknya berubah (muat awal, putar layar, sidebar), supaya tile dan geser tidak macet
        var box = document.getElementById("route-map");
        if (window.ResizeObserver) new ResizeObserver(function () { map.invalidateSize(); }).observe(box);
        window.addEventListener("load", function () { map.invalidateSize(); });
    }

    function pin(label, cls) {
        return L.divIcon({
            className: "route-pin-wrap",
            html: '<span class="route-pin ' + cls + '">' + label + "</span>",
            iconSize: [32, 32],
            iconAnchor: [16, 16]
        });
    }

    function drawMap(fit) {
        if (!map) return;
        layer.clearLayers();

        var bounds = [];
        if (plan.route) {
            L.polyline(plan.route.geometry, {
                color: "#2563eb", weight: 5, opacity: 0.9,
                dashArray: plan.route.dashed ? "8 8" : null
            }).addTo(layer);
            bounds = bounds.concat(plan.route.geometry);
        }

        // Posisi kurir (titik biru); gudang sengaja tidak digambar
        if (plan.origin) {
            L.marker([plan.origin.lat, plan.origin.lng], {
                icon: L.divIcon({ className: "route-pin-wrap", html: '<span class="route-me"></span>', iconSize: [22, 22], iconAnchor: [11, 11] }),
                title: "Posisimu", zIndexOffset: 1000
            }).addTo(layer);
            var b = plan.bounds;
            var inDepok = plan.origin.lat >= b.south && plan.origin.lat <= b.north &&
                          plan.origin.lng >= b.west && plan.origin.lng <= b.east;
            if (inDepok) bounds.push([plan.origin.lat, plan.origin.lng]);   // di luar Depok tidak ikut mengatur zoom
        }

        plan.stops.forEach(function (s) {
            var cls = "is-" + s.status + (s.id === selectedId ? " is-selected" : "");
            L.marker([s.lat, s.lng], { icon: pin(s.status === "done" ? "✓" : s.order, cls), title: s.name })
                .on("click", function () { selectStop(s.id); })
                .addTo(layer);
            bounds.push([s.lat, s.lng]);
        });

        // Batas geser = wilayah Depok + seluruh rute dan pin (bila posisimu di luar Depok, rutenya tetap bisa dijelajahi)
        var b0 = plan.bounds;
        var area = L.latLngBounds([[b0.south, b0.west], [b0.north, b0.east]]);
        bounds.forEach(function (point) { area.extend(point); });
        map.setMaxBounds(area.pad(0.15));

        if (fit && bounds.length) {
            // Sisakan ruang untuk kartu di atas peta (ringkasan, pesan, petunjuk belok) agar pin dan garis tidak tertutup
            var topH = els.top ? els.top.offsetHeight : 0;
            var bottomH = els.turn.hidden ? 0 : els.turn.offsetHeight;
            map.fitBounds(L.latLngBounds(bounds), {
                paddingTopLeft: [32, topH + 32],
                paddingBottomRight: [32, bottomH + 40]
            });
        }
    }

    /* ===== Saklar Sedang Bertugas ===== */

    function initDuty() {
        if (!els.dutyToggle) return;
        els.dutyToggle.addEventListener("change", function () {
            var wanted = els.dutyToggle.checked;
            var body = new FormData();
            body.append("on_duty", wanted ? "true" : "false");

            els.dutyToggle.disabled = true;
            post(plan.dutyUrl, body)
                .then(function (result) {
                    if (!result) return;
                    if (!result.payload.ok) throw new Error("gagal");
                    els.dutyToggle.checked = result.payload.is_on_duty;
                    els.dutyLabel.textContent = result.payload.label;
                })
                .catch(function () {
                    els.dutyToggle.checked = !wanted;           // kembalikan bila gagal
                    showToast("Status tugas gagal diubah. Coba lagi.", true);
                })
                .finally(function () { els.dutyToggle.disabled = false; });
        });
    }

    /* ===== Lokasi kurir (GPS peramban) ===== */

    var lastFetch = { time: 0, pos: null };

    // Jarak garis lurus dua posisi dalam meter
    function meters(a, b) {
        var rad = Math.PI / 180, dLat = (b.lat - a.lat) * rad, dLng = (b.lng - a.lng) * rad;
        var h = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
                Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
        return 12742000 * Math.asin(Math.sqrt(h));
    }

    // Minta server menghitung ulang rute dari posisi terbaru
    function refreshFromPosition() {
        if (busy || !userPos) return;
        lastFetch = { time: Date.now(), pos: userPos };
        var first = !plan.origin;
        fetch(plan.dataUrl + "?lat=" + userPos.lat + "&lng=" + userPos.lng, {
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" }
        })
            .then(function (response) { return response.json(); })
            .then(function (payload) { if (payload.ok && !busy) applyPlan(payload.plan, true, first); })
            .catch(function () { /* gangguan sesaat: rute lama tetap tampil */ });
    }

    function onPosition(position) {
        userPos = { lat: position.coords.latitude, lng: position.coords.longitude };
        geoNote = "";
        // Hitung ulang rute saat pertama kali, atau setelah bergeser >150 m dan lewat 20 detik
        var moved = lastFetch.pos ? meters(lastFetch.pos, userPos) : Infinity;
        if (!lastFetch.pos || (moved > 150 && Date.now() - lastFetch.time > 20000)) refreshFromPosition();
    }

    function onPositionError(error) {
        geoNote = error && error.code === 1
            ? "Izinkan akses lokasi di peramban agar petunjuk arah dihitung dari posisimu."
            : "Lokasimu belum bisa ditemukan. Rute dihitung antar titik jemput.";
        renderOverlays();
        drawMap(true);                // pesan menambah tinggi kartu di atas peta, jadi atur ulang ruang kosongnya
        refreshIcons();
    }

    function initLocation() {
        if (!navigator.geolocation) {
            geoNote = "Peramban ini tidak mendukung lokasi. Rute dihitung antar titik jemput.";
            renderOverlays();
            drawMap(true);
            return;
        }
        navigator.geolocation.watchPosition(onPosition, onPositionError, {
            enableHighAccuracy: true, maximumAge: 10000, timeout: 20000
        });
    }

    /* ===== Mulai ===== */

    function renderAll(fit) {
        renderList();
        renderDetail();
        renderOverlays();
        renderDirections();
        drawMap(fit !== false);
        refreshIcons();
    }

    initMap();
    initDuty();
    /* Di layar kecil, ringkasan dan pesan posisi diketuk untuk dibuka atau ditutup */
    function initOverlayToggles() {
        [els.summary, els.mapMsg].forEach(function (node) {
            if (!node) return;
            node.addEventListener("click", function () {
                node.classList.toggle("is-open");
            });
        });
    }

    initOverlayToggles();
    initLocation();
    if (!selectedId) selectedId = (plan.stops[plan.stops.length - 1] || {}).id;
    renderAll();
})();